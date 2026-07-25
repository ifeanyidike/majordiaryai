"""
Cow status transition engine.

Rules (from planning docs):
  insemination recorded   → status = inseminated
  heat check positive     → cow returns to the Insemination Program (status = open,
                            current_program = "Insemination", surfaces on /reports/breeding-due)
  heat check at day 20-25 → if no heat, stays inseminated
  pregnancy check +ve     → status = pregnant, compute dry_date (day 223) & due_date (day 283)
  pregnancy check -ve     → status = open (protocol selection via Open report)
  bleeding pre-AI         → enrollment cancelled, cow open, auto-enrolled in Ovsynch
  calving recorded        → status = fresh, lactation_number++, clear reproductive fields
  dry date reached        → status = dry (day 223 post-insemination; farmer notified to change pen)
  fresh day 70            → status = open (entry date pushed to next Mon/Tue/Sat)
  calf day 60             → status = heifer
  heifer day ~395 (13 mo) → status = open (appears on breeding list)
  cull recorded           → status = cull
Timed transitions run via run_lifecycle_transitions(), invoked by the report
endpoints and POST /admin/run-transitions — never as a GET side effect.
"""

import uuid
from datetime import date, timedelta
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, Insemination, NeedlingEnrollment, NeedlingRecord,
    EnrollmentStatus, ProtocolType,
)
from app.services.notifications import create_notification
from app.services.protocols import get_scheduled_records

GESTATION_DAYS = 283
DRY_OFF_DAY = 223            # days after insemination
FRESH_TO_OPEN_DAY = 70       # days after calving
CALF_TO_HEIFER_DAY = 60      # days after birth
HEIFER_BREEDING_DAY = 395    # ~13 months after birth
BREEDING_WEEKDAYS = (0, 1, 5)  # Monday, Tuesday, Saturday

# Statuses in which an insemination may be recorded.
INSEMINABLE_STATUSES = {
    CowStatus.heifer, CowStatus.fresh, CowStatus.open,
    CowStatus.needling, CowStatus.inseminated,
}

# Legal status transition map. dead/sold are terminal; sold only from cull.
LEGAL_TRANSITIONS = {
    CowStatus.calf:        {CowStatus.heifer, CowStatus.cull, CowStatus.dead},
    CowStatus.heifer:      {CowStatus.open, CowStatus.needling, CowStatus.inseminated,
                            CowStatus.cull, CowStatus.dead},
    CowStatus.fresh:       {CowStatus.open, CowStatus.inseminated, CowStatus.cull, CowStatus.dead},
    CowStatus.open:        {CowStatus.needling, CowStatus.inseminated, CowStatus.cull, CowStatus.dead},
    CowStatus.needling:    {CowStatus.open, CowStatus.inseminated, CowStatus.cull, CowStatus.dead},
    CowStatus.inseminated: {CowStatus.open, CowStatus.pregnant, CowStatus.cull, CowStatus.dead},
    CowStatus.pregnant:    {CowStatus.open, CowStatus.dry, CowStatus.fresh, CowStatus.cull, CowStatus.dead},
    CowStatus.dry:         {CowStatus.fresh, CowStatus.cull, CowStatus.dead},
    CowStatus.cull:        {CowStatus.sold, CowStatus.dead},
    CowStatus.sold:        set(),
    CowStatus.dead:        set(),
}


def ensure_transition(cow: Cow, new_status: CowStatus) -> None:
    """Raise 409 if moving the cow to new_status is illegal. Same-status is a no-op."""
    if new_status == cow.status:
        return
    if new_status not in LEGAL_TRANSITIONS.get(cow.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Illegal status transition: {cow.status.value} -> {new_status.value}",
        )


def compute_due_date(insemination_date: date) -> date:
    return insemination_date + timedelta(days=GESTATION_DAYS)


def compute_dry_date(insemination_date: date) -> date:
    return insemination_date + timedelta(days=DRY_OFF_DAY)


def adjust_to_breeding_day(d: date) -> date:
    """Push a date forward to the next Monday, Tuesday or Saturday (spec rule)."""
    while d.weekday() not in BREEDING_WEEKDAYS:
        d += timedelta(days=1)
    return d


def _clear_reproductive_fields(cow: Cow) -> None:
    cow.last_insemination_id = None
    cow.last_insemination_date = None
    cow.due_date = None
    cow.dry_date = None


async def cancel_active_enrollments(
    cow: Cow, db: AsyncSession, new_status: EnrollmentStatus = EnrollmentStatus.completed
) -> None:
    result = await db.execute(
        select(NeedlingEnrollment)
        .where(
            NeedlingEnrollment.cow_id == cow.id,
            NeedlingEnrollment.status.in_(
                [EnrollmentStatus.active, EnrollmentStatus.completed_pending_ai]
            ),
        )
        .with_for_update()
    )
    for enrollment in result.scalars().all():
        enrollment.status = new_status


async def on_insemination(cow: Cow, insemination: Insemination, db: AsyncSession) -> None:
    """Called immediately after an insemination is recorded."""
    cow.status = CowStatus.inseminated
    cow.current_program = None
    cow.last_insemination_date = insemination.date
    cow.last_insemination_id = insemination.id
    await cancel_active_enrollments(cow, db, EnrollmentStatus.completed)


async def on_heat_detected(cow: Cow, db: AsyncSession) -> None:
    """Heat detected (incl. blood on tail) — cow returns to the Insemination Program."""
    cow.status = CowStatus.open
    cow.current_program = "Insemination"
    _clear_reproductive_fields(cow)
    create_notification(
        db, cow.farm_id, cow.id, "breeding_due",
        f"Cow {cow.ear_tag} was detected in heat and returned to the Insemination Program.",
    )


async def on_pregnancy_confirmed(cow: Cow, insemination_date: date, db: AsyncSession) -> None:
    """Called when vet confirms pregnancy."""
    cow.status = CowStatus.pregnant
    cow.due_date = compute_due_date(insemination_date)
    cow.dry_date = compute_dry_date(insemination_date)


async def on_pregnancy_negative(cow: Cow, db: AsyncSession) -> None:
    """Not pregnant (or cysts found) — back to Open for protocol selection."""
    cow.status = CowStatus.open
    cow.current_program = None
    _clear_reproductive_fields(cow)
    create_notification(
        db, cow.farm_id, cow.id, "open",
        f"Cow {cow.ear_tag} is Open — select a needling protocol.",
    )


async def on_bleeding_before_insemination(cow: Cow, db: AsyncSession, start_date: date = None) -> None:
    """Bleeding event on a needling record before insemination: cancel the
    enrollment, set the cow Open, then auto-enroll her in Ovsynch (spec:
    "transfers into Ovsynch Needling Program")."""
    await cancel_active_enrollments(cow, db, EnrollmentStatus.cancelled)
    cow.status = CowStatus.open
    cow.current_program = None
    _clear_reproductive_fields(cow)

    if start_date is None:
        start_date = local_today()
    enrollment = NeedlingEnrollment(
        cow_id=cow.id, protocol=ProtocolType.ovsynch, start_date=start_date,
    )
    db.add(enrollment)
    await db.flush()
    for s in get_scheduled_records(ProtocolType.ovsynch.value, start_date):
        db.add(NeedlingRecord(
            enrollment_id=enrollment.id,
            cow_id=cow.id,
            protocol_day=s["protocol_day"],
            scheduled_date=s["scheduled_date"],
            treatment=s["treatment"],
            is_final=s["is_final"],
        ))
    cow.status = CowStatus.needling
    cow.current_program = ProtocolType.ovsynch.value
    create_notification(
        db, cow.farm_id, cow.id, "open",
        f"Cow {cow.ear_tag} had a bleeding event and was transferred into the Ovsynch needling program.",
    )


async def on_calving(cow: Cow, calving_date: date, db: AsyncSession) -> None:
    """Called when calving is recorded."""
    cow.status = CowStatus.fresh
    cow.lactation_number = (cow.lactation_number or 0) + 1
    cow.last_calving_date = calving_date
    cow.current_program = None
    _clear_reproductive_fields(cow)


async def on_cull(cow: Cow, db: AsyncSession) -> None:
    cow.status = CowStatus.cull
    cow.current_program = None
    await cancel_active_enrollments(cow, db, EnrollmentStatus.cancelled)


async def run_lifecycle_transitions(
    db: AsyncSession,
    farm_ids: Optional[Iterable[uuid.UUID]] = None,
    today: Optional[date] = None,
) -> int:
    """Apply all timed status transitions. Invoked by report endpoints and
    POST /admin/run-transitions; commits once if anything changed.

      pregnant + dry_date reached      → dry (+ "change pen" notification)
      fresh + day 70 (next Mon/Tue/Sat)→ open (+ notification)
      calf + day 60                    → heifer
      heifer + day 395 (~13 months)    → open (breeding-eligible, + notification)

    farm_ids: restrict the sweep to these farms (None = all farms).
    """
    if today is None:
        today = local_today()

    stmt = (
        select(Cow)
        .where(Cow.status.in_([CowStatus.pregnant, CowStatus.fresh, CowStatus.calf, CowStatus.heifer]))
        .with_for_update()
    )
    if farm_ids is not None:
        farm_ids = list(farm_ids)
        if not farm_ids:
            return 0
        stmt = stmt.where(Cow.farm_id.in_(farm_ids))

    result = await db.execute(stmt)
    cows = result.scalars().all()

    changed = 0
    for cow in cows:  # evaluate every cow — no short-circuiting
        if cow.status == CowStatus.pregnant and cow.dry_date and cow.dry_date <= today:
            cow.status = CowStatus.dry
            create_notification(
                db, cow.farm_id, cow.id, "dry_off",
                f"Cow {cow.ear_tag} is now Dry — change pen.",
            )
            changed += 1
            continue

        if cow.status == CowStatus.fresh and cow.last_calving_date:
            entry_date = adjust_to_breeding_day(
                cow.last_calving_date + timedelta(days=FRESH_TO_OPEN_DAY)
            )
            if entry_date <= today:
                cow.status = CowStatus.open
                cow.current_program = None
                create_notification(
                    db, cow.farm_id, cow.id, "open",
                    f"Cow {cow.ear_tag} entered the Open Program — select a needling protocol.",
                )
                changed += 1
            continue

        if cow.status == CowStatus.calf and cow.date_of_birth and \
                (today - cow.date_of_birth).days >= CALF_TO_HEIFER_DAY:
            cow.status = CowStatus.heifer
            changed += 1
            # fall through: a very old calf may become breeding-eligible immediately

        if cow.status == CowStatus.heifer and cow.date_of_birth and \
                (today - cow.date_of_birth).days >= HEIFER_BREEDING_DAY:
            cow.status = CowStatus.open
            cow.current_program = None
            create_notification(
                db, cow.farm_id, cow.id, "open",
                f"Heifer {cow.ear_tag} reached breeding age — ready for the Insemination Program.",
            )
            changed += 1

    if changed:
        await db.commit()
    return changed
