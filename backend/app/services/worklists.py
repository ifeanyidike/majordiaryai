"""
Canonical work-list queries for the technician's daily reports.

Single source of truth for the same-day overlap rule. The Needling report defers
a cow to Timed Breeding only when she would ACTUALLY appear there, so both sides
are built from ONE predicate list (`_timed_breeding_predicates`). Duplicating
those predicates is what previously made cows vanish from both reports, so do
not inline them anywhere else — endpoints and tests must call these builders.

Invariant (see tests/test_worklists.py, executed against a real database):
  · a cow is never on both reports at once, and
  · a cow with outstanding work is never on neither.
"""

from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.models.models import (
    Cow, CowStatus, EnrollmentStatus, Farm, NeedlingEnrollment, NeedlingRecord,
)
from app.services.protocols import TIMED_AI_PROTOCOLS

# Cows that have left the herd never appear on a work list.
TERMINAL_STATUSES = (CowStatus.cull, CowStatus.sold, CowStatus.dead)

# Enrollments still "in play" for the final-day insemination. `completed_pending_ai`
# means the final shot was given and only the AI is outstanding — such a cow MUST
# stay on Timed Breeding, which is why no `completed` filter belongs below.
OPEN_ENROLLMENT_STATUSES = (
    EnrollmentStatus.active,
    EnrollmentStatus.completed_pending_ai,
)


def _timed_breeding_predicates(rec, enr, cow, today: date) -> List:
    """The definition of "this cow is on the Timed Breeding report today".

    Deliberately says nothing about `rec.completed`: the final injection may
    already be given (enrollment `completed_pending_ai`) with the AI still due.
    """
    return [
        rec.is_final == True,  # noqa: E712 — SQL expression
        rec.scheduled_date <= today,
        # Timed-AI protocols only. Prostaglandin Heat ends in *conditional* AI on
        # observed heat, so it stays on the Needling/Heat path.
        enr.protocol.in_(TIMED_AI_PROTOCOLS),
        enr.status.in_(OPEN_ENROLLMENT_STATUSES),
        cow.status == CowStatus.needling,
    ]


def timed_breeding_stmt(today: date):
    """Rows for GET /reports/timed-breeding."""
    return (
        select(NeedlingRecord, NeedlingEnrollment, Cow, Farm)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .join(Cow, Cow.id == NeedlingRecord.cow_id)
        .join(Farm, Farm.id == Cow.farm_id)
        .where(*_timed_breeding_predicates(NeedlingRecord, NeedlingEnrollment, Cow, today))
        .order_by(NeedlingRecord.scheduled_date)
    )


def defers_to_timed_breeding(today: date):
    """Correlated EXISTS on the outer `Cow` — the exact complement of
    `timed_breeding_stmt`, so the two reports can never disagree."""
    rec = aliased(NeedlingRecord)
    enr = aliased(NeedlingEnrollment)
    return (
        select(rec.id)
        .join(enr, enr.id == rec.enrollment_id)
        .where(
            rec.cow_id == Cow.id,
            *_timed_breeding_predicates(rec, enr, Cow, today),
        )
        .exists()
    )


def needling_due_stmt(today: date):
    """Rows for GET /needling/today — pending injections, minus the cows the
    overlap rule defers to Timed Breeding."""
    return (
        select(NeedlingRecord, Cow)
        .join(Cow, Cow.id == NeedlingRecord.cow_id)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .where(
            NeedlingRecord.scheduled_date <= today,
            NeedlingRecord.completed == False,  # noqa: E712
            ~defers_to_timed_breeding(today),
            NeedlingEnrollment.status == EnrollmentStatus.active,
            Cow.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(NeedlingRecord.scheduled_date)
    )


def pending_final_record_stmt(cow_id, today: date):
    """The pending final record to close out when an insemination is recorded.

    Deliberately NOT gated on TIMED_AI_PROTOCOLS. Prostaglandin Heat's last day
    is "observe heat, inseminate if in heat" — when that AI is recorded the day
    is done, and leaving the record open made the outcome depend on whether the
    technician happened to tap "complete" before or after recording the AI.

    Nor is it gated on the AI's own date: a back-dated AI must still close the
    record, otherwise it is orphaned when `on_insemination` closes the
    enrollment. `today` bounds it so a FUTURE scheduled step is never silently
    marked given.
    """
    return (
        select(NeedlingRecord)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .where(
            NeedlingRecord.cow_id == cow_id,
            NeedlingRecord.is_final == True,  # noqa: E712
            NeedlingRecord.completed == False,  # noqa: E712
            NeedlingRecord.scheduled_date <= today,
            NeedlingEnrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
        )
        .order_by(NeedlingRecord.scheduled_date.desc())
        .limit(1)
        # Lock only the record — a bare FOR UPDATE on a join would also lock the
        # enrollment row and widen the deadlock surface.
        .with_for_update(of=NeedlingRecord)
    )


def injection_only(treatment: Optional[str]) -> Optional[str]:
    """The injection component of a treatment string.

    Protocol tables encode the final step as "2cc GnRH + Insemination"; when the
    sentence already says "inseminate", repeating it reads as
    "…+ Insemination + inseminate today".
    """
    if not treatment:
        return None
    head = treatment.split("+")[0].strip()
    return head or None


def latest_open_record_stmt(cow_id):
    """The most recent incomplete record on a cow's open enrollment, if any.

    Used to attach a bleeding event to her treatment history. Returns nothing
    when she isn't mid-protocol — bleeding is recordable regardless, so callers
    must treat `None` as normal rather than an error.
    """
    return (
        select(NeedlingRecord)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .where(
            NeedlingRecord.cow_id == cow_id,
            NeedlingRecord.completed == False,  # noqa: E712
            NeedlingEnrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
        )
        .order_by(NeedlingRecord.scheduled_date)
        .limit(1)
        .with_for_update(of=NeedlingRecord)
    )
