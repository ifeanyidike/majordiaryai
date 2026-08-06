"""
Same-day overlap rule — executed against the REAL queries and a real database.

These call app/services/worklists.py directly (the same builders the endpoints
use), so changing the production SQL changes what is asserted here. There is no
re-implementation of the predicates anywhere in this file.

The invariant, for every cow state:
  1. she is never on both reports at once, and
  2. if she has outstanding work she is never on neither.

Run:  cd backend && .venv/bin/python -m pytest tests/ -q
"""

from datetime import date

import pytest
from sqlalchemy import and_, or_, select

from app.models.models import (
    Cow, CowStatus, EnrollmentStatus, NeedlingEnrollment, NeedlingRecord, ProtocolType,
)
from app.services.worklists import needling_due_stmt, timed_breeding_stmt

pytestmark = pytest.mark.asyncio

TODAY = date.today()

# (protocol_day, day_offset, treatment, is_final, completed)
DAY1_DONE = (1, -9, "2cc GnRH", False, True)
DAY7_DONE = (7, -3, "2cc PGF", False, True)
DAY7_PENDING = (7, -3, "2cc PGF", False, False)
FINAL_TODAY = (10, 0, "2cc GnRH + Insemination", True, False)
FINAL_TODAY_DONE = (10, 0, "2cc GnRH + Insemination", True, True)
FINAL_FUTURE = (10, 3, "2cc GnRH + Insemination", True, False)


async def on_needling(db, cow: Cow) -> list:
    rows = (await db.execute(needling_due_stmt(TODAY))).all()
    return [r for r, c in rows if c.id == cow.id]


async def on_timed_breeding(db, cow: Cow) -> list:
    rows = (await db.execute(timed_breeding_stmt(TODAY))).all()
    return [rec for rec, enr, c, farm in rows if c.id == cow.id]


async def assert_invariants(db, cow: Cow, *, label: str):
    """Disjoint, and nobody with outstanding work falls off both reports."""
    n = await on_needling(db, cow)
    t = await on_timed_breeding(db, cow)
    assert not ({r.id for r in n} & {r.id for r in t}), f"{label}: same record on both reports"

    # "Outstanding work" excludes records on a cancelled/completed enrollment:
    # those were called off and must NOT appear on a report. Defined here
    # independently of the query under test, so it can't rubber-stamp it.
    #
    # A completed final record still counts when the enrollment is
    # `completed_pending_ai` — that state means "shot given, AI still due", i.e.
    # real outstanding work. Defining it as `completed == False` alone made this
    # assertion unable to fail for exactly the state that was broken.
    outstanding = (await db.execute(
        select(NeedlingRecord)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .where(
            NeedlingRecord.cow_id == cow.id,
            NeedlingRecord.scheduled_date <= TODAY,
            NeedlingEnrollment.status.in_(
                [EnrollmentStatus.active, EnrollmentStatus.completed_pending_ai]
            ),
            or_(
                NeedlingRecord.completed == False,  # noqa: E712
                and_(
                    NeedlingRecord.is_final == True,  # noqa: E712
                    NeedlingEnrollment.status == EnrollmentStatus.completed_pending_ai,
                ),
            ),
        )
    )).scalars().all()
    if outstanding and cow.status not in (CowStatus.cull, CowStatus.sold, CowStatus.dead):
        assert n or t, f"{label}: has outstanding work but appears on NO report"
    return n, t


# ── The core rule ────────────────────────────────────────────────────

async def test_final_day_shows_only_on_timed_breeding(db, make_cow):
    cow = await make_cow(steps=[DAY1_DONE, DAY7_DONE, FINAL_TODAY])
    n, t = await assert_invariants(db, cow, label="final day")
    assert not n and len(t) == 1


async def test_non_final_day_shows_only_on_needling(db, make_cow):
    cow = await make_cow(steps=[DAY1_DONE, DAY7_PENDING, FINAL_FUTURE])
    n, t = await assert_invariants(db, cow, label="mid protocol")
    assert len(n) == 1 and not t


async def test_overdue_earlier_shot_does_not_resurface_cow_on_final_day(db, make_cow):
    """Day 7 missed AND day 10 due today → Timed Breeding only, not both."""
    cow = await make_cow(steps=[DAY1_DONE, DAY7_PENDING, FINAL_TODAY])
    n, t = await assert_invariants(db, cow, label="overdue + final")
    assert not n and len(t) == 1


# ── Regressions: cows that previously vanished from both reports ─────

async def test_completed_final_record_stays_on_timed_breeding(db, make_cow):
    """`completed_pending_ai` means the final shot IS given and only the AI is
    outstanding — she must remain on Timed Breeding, not disappear."""
    cow = await make_cow(
        enrollment_status=EnrollmentStatus.completed_pending_ai,
        steps=[DAY1_DONE, DAY7_DONE, FINAL_TODAY_DONE],
    )
    n = await on_needling(db, cow)
    t = await on_timed_breeding(db, cow)
    assert not n
    assert len(t) == 1, "cow awaiting AI fell off both reports"


async def test_cancelled_enrollment_does_not_hide_pending_injections(db, make_cow):
    """A cancelled enrollment's leftover final record must not suppress an
    active enrollment's due injection."""
    cow = await make_cow(
        enrollment_status=EnrollmentStatus.cancelled,
        steps=[FINAL_TODAY],
        extra_enrollments=[
            (ProtocolType.ovsynch, EnrollmentStatus.active, [(1, 0, "2cc GnRH", False, False)]),
        ],
    )
    n, t = await assert_invariants(db, cow, label="cancelled + re-enrolled")
    assert len(n) == 1 and not t


async def test_status_drift_does_not_hide_cow_from_both_reports(db, make_cow):
    """Timed Breeding requires status=needling; if she drifted to open the
    needling query must not defer her away."""
    cow = await make_cow(cow_status=CowStatus.open, steps=[DAY7_PENDING, FINAL_TODAY])
    n, t = await assert_invariants(db, cow, label="status drift")
    assert n, "cow with drifted status vanished from both reports"


# ── Protocol semantics ───────────────────────────────────────────────

async def test_prostaglandin_heat_final_day_stays_on_needling(db, make_cow):
    """Its last day is conditional AI on observed heat, not timed AI — it must
    never be pulled onto Timed Breeding."""
    cow = await make_cow(
        protocol=ProtocolType.prostaglandin_heat,
        steps=[(5, 0, "Heat Observation + Insemination if in heat", True, False)],
    )
    n, t = await assert_invariants(db, cow, label="pgf-heat final day")
    assert len(n) == 1 and not t


async def test_terminal_cow_is_on_no_report(db, make_cow):
    cow = await make_cow(cow_status=CowStatus.cull, steps=[DAY7_PENDING])
    assert not await on_needling(db, cow)
    assert not await on_timed_breeding(db, cow)


# ── Matrix sweep ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "label,kwargs",
    [
        ("final today", dict(steps=[DAY1_DONE, DAY7_DONE, FINAL_TODAY])),
        ("mid protocol", dict(steps=[DAY1_DONE, DAY7_PENDING, FINAL_FUTURE])),
        ("overdue final", dict(steps=[DAY1_DONE, DAY7_PENDING, (10, -5, "2cc GnRH + Insemination", True, False)])),
        ("awaiting AI", dict(enrollment_status=EnrollmentStatus.completed_pending_ai,
                             steps=[FINAL_TODAY_DONE])),
        ("status drift", dict(cow_status=CowStatus.open, steps=[DAY7_PENDING, FINAL_TODAY])),
        ("pgf heat final", dict(protocol=ProtocolType.prostaglandin_heat,
                                steps=[(5, 0, "Heat Observation", True, False)])),
        ("cancelled leftovers", dict(enrollment_status=EnrollmentStatus.cancelled,
                                     steps=[FINAL_TODAY])),
    ],
)
async def test_invariants_hold_across_states(db, make_cow, label, kwargs):
    cow = await make_cow(**kwargs)
    await assert_invariants(db, cow, label=label)
