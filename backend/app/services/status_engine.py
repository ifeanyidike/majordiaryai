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
from sqlalchemy.orm import aliased

from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, Insemination, NeedlingEnrollment, NeedlingRecord,
    EnrollmentStatus, ProtocolType,
)
from app.services.notifications import create_notification
from app.services.protocols import get_scheduled_records, TIMED_AI_PROTOCOLS

GESTATION_DAYS = 283
DRY_OFF_DAY = 223            # days after insemination
# Heat monitoring window, days post-AI (Major_further.md; the older docs say
# 19-25 — confirm with the client whether day 19 counts).
HEAT_WINDOW = (20, 25)
FRESH_TO_OPEN_DAY = 70       # days after calving
CALF_TO_HEIFER_DAY = 60      # days after birth
HEIFER_BREEDING_DAY = 395    # ~13 months after birth
BREEDING_WEEKDAYS = (0, 1, 5)  # Monday, Tuesday, Saturday
# Days past a protocol's final day after which an un-inseminated cow is treated
# as abandoned: the synchronisation has lapsed, so cancel and return her to Open
# rather than leaving her pinned on Timed Breeding indefinitely.
#
# Client answer (SPEC_QUESTIONS.md, Q2 "how long before we cancel the program?"
# -> "2. Goes to open status"): two days, then Open. Each answer in that file
# leads with the number the question asked for -- Q3 "7 days he can still see
# farm info", Q4 "5 days mon - Friday" -- so the leading 2 is the answer, not
# list numbering. Two days also matches the biology: a synchronised ovulation
# missed by more than a day or so is gone, and holding her on Timed Breeding
# suppresses every other injection she is due.
ABANDONED_PROTOCOL_DAYS = 2

# Statuses in which an insemination may be recorded.
INSEMINABLE_STATUSES = {
    CowStatus.heifer, CowStatus.fresh, CowStatus.open,
    CowStatus.needling, CowStatus.inseminated,
}

# Legal status transition map. dead/sold are terminal; sold only from cull.
LEGAL_TRANSITIONS = {
    CowStatus.calf:        {CowStatus.heifer, CowStatus.cull, CowStatus.dead},
    # fresh: a heifer can calve before anyone records a pregnancy check.
    CowStatus.heifer:      {CowStatus.open, CowStatus.needling, CowStatus.inseminated,
                            CowStatus.fresh, CowStatus.cull, CowStatus.dead},
    CowStatus.fresh:       {CowStatus.open, CowStatus.inseminated, CowStatus.fresh,
                            CowStatus.cull, CowStatus.dead},
    CowStatus.open:        {CowStatus.needling, CowStatus.inseminated, CowStatus.fresh,
                            CowStatus.cull, CowStatus.dead},
    CowStatus.needling:    {CowStatus.open, CowStatus.inseminated, CowStatus.fresh,
                            CowStatus.cull, CowStatus.dead},
    # fresh: she calved without the pregnancy check ever being recorded.
    CowStatus.inseminated: {CowStatus.open, CowStatus.pregnant, CowStatus.fresh,
                            CowStatus.cull, CowStatus.dead},
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


# Master Structure, "Milk Cycle": milk runs from calving to day 223, stops
# until she calves again, and a heifer never milks. Those are exactly the
# statuses below, so milking is DERIVED — storing a flag would be a second
# source of truth that drifts from status.
NON_MILKING_STATUSES = {
    CowStatus.dry, CowStatus.calf, CowStatus.heifer,
    CowStatus.cull, CowStatus.sold, CowStatus.dead,
}


def is_milking(cow: Cow) -> bool:
    """True when this cow is currently in milk."""
    if cow.status in NON_MILKING_STATUSES:
        return False
    # She only milks once she has actually calved.
    return cow.last_calving_date is not None


def is_metestrous_bleeding(days_since: int) -> bool:
    """True when blood this soon after AI is the heat she was just bred on.

    The spec says bleeding events are recordable on any day. The timing rule
    refused them before the heat window, which is right about the CONSEQUENCE
    (this is not a returned heat, and acting on it would cancel a good
    insemination) but wrong about the RECORD: the technician saw blood and had
    nowhere to put it, so the observation was simply lost.

    So these are stored as observations and change nothing.
    """
    return days_since < HEAT_WINDOW[0]


def heat_check_timing_error(days_since: int, has_signal: bool) -> Optional[str]:
    """Why a heat check at `days_since` post-AI is not accepted, or None if it is.

    Routine (no-signal) checks belong to the monitoring window only. A check
    carrying a signal (observed heat or blood on the tail) is a fact from the
    window's START onward with no upper bound — the spec's "blood on any day"
    covers late returns to heat, and rejecting them past day 25 while the
    bleeding endpoint pointed back here made them unrecordable. But the lower
    bound stays: spotting a day or two after breeding is normal metestrous
    bleeding from the heat she was JUST bred on, not evidence the AI failed —
    treating it as a returned heat would cancel a perfectly good insemination.
    """
    lo, hi = HEAT_WINDOW
    if has_signal:
        if days_since < lo:
            return (
                f"Heat/bleeding this soon after breeding (day {days_since}) is normal "
                f"post-breeding spotting, not a returned heat — heat checks start at day {lo}"
            )
        return None
    if not (lo <= days_since <= hi):
        return (
            f"Routine heat checks are only accepted {lo}-{hi} days post-insemination "
            f"(this check is at day {days_since})"
        )
    return None


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
    # Belongs to the cycle that just ended — leaving it set would keep the next
    # dry-off silently pre-confirmed and off the technician's report.
    cow.dry_off_confirmed_date = None


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
    # Keep last_insemination_id/date: the failed AI is a true fact the
    # Insemination Program report shows ("last AI <date>"); only the
    # pregnancy-cycle projections belong to the cycle that just ended.
    cow.due_date = None
    cow.dry_date = None
    cow.dry_off_confirmed_date = None
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


async def on_final_record_completed(
    cow: Cow, enrollment: NeedlingEnrollment, db: AsyncSession
) -> None:
    """The last scheduled step of a protocol was completed.

    `is_final` means "last scheduled step", NOT "insemination day" — the two
    need different handling or the cow dead-ends on no report:

      timed-AI protocol      → shot given, AI outstanding. Enrollment goes to
                               `completed_pending_ai` and she stays on the Timed
                               Breeding report until the AI is recorded.
      conditional-AI (PGF)   → the schedule is finished. If she showed heat the
                               technician records that AI separately; otherwise
                               she returns to Open for a new protocol decision.
    """
    if enrollment.protocol in TIMED_AI_PROTOCOLS:
        enrollment.status = EnrollmentStatus.completed_pending_ai
        return

    enrollment.status = EnrollmentStatus.completed
    # Guarded like every other status write — a drifted cow must not be moved
    # into an illegal state just because her protocol ran out of steps.
    ensure_transition(cow, CowStatus.open)
    cow.status = CowStatus.open
    cow.current_program = None
    create_notification(
        db, cow.farm_id, cow.id, "open",
        f"Cow {cow.ear_tag} finished {enrollment.protocol.value} — "
        "returned to Open for a breeding decision.",
    )


async def on_bleeding_before_insemination(cow: Cow, db: AsyncSession, start_date: date = None) -> None:
    """Bleeding event on a needling record before insemination: cancel the
    enrollment, set the cow Open, then auto-enroll her in Ovsynch (spec:
    "transfers into Ovsynch Needling Program")."""
    # Guarded like every other status write — routers restrict which statuses
    # may record bleeding, but this service must not be able to force an
    # illegal transition (e.g. calf/fresh → needling) if a new caller slips.
    ensure_transition(cow, CowStatus.open)
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
    ensure_transition(cow, CowStatus.needling)
    cow.status = CowStatus.needling
    cow.current_program = ProtocolType.ovsynch.value
    create_notification(
        db, cow.farm_id, cow.id, "open",
        f"Cow {cow.ear_tag} had a bleeding event and was transferred into the Ovsynch needling program.",
    )


async def on_calving(cow: Cow, calving_date: date, db: AsyncSession) -> None:
    """Called when calving is recorded.

    Calving is an observed event, so it is accepted from any live status — a
    cow can calve while the system still believes she is inseminated (nobody
    recorded the pregnancy check) or heifer (bred before she was ever
    enrolled). Any open enrollment is closed out, since she is plainly no
    longer in a breeding protocol.

    It goes through `ensure_transition` like every other status write. Setting
    the status directly meant a calving recorded against a CULLED cow silently
    un-culled her — cull -> fresh is a transition LEGAL_TRANSITIONS explicitly
    forbids, and there is no record anywhere that the cull was reversed.
    """
    ensure_transition(cow, CowStatus.fresh)
    # `cancelled`, not `completed`: she calved part-way through a protocol, so
    # the protocol was interrupted. Recording it as completed inflated
    # protocol-completion stats with rounds that never finished.
    await cancel_active_enrollments(cow, db, EnrollmentStatus.cancelled)
    cow.status = CowStatus.fresh
    cow.lactation_number = (cow.lactation_number or 0) + 1
    cow.last_calving_date = calving_date
    cow.current_program = None
    _clear_reproductive_fields(cow)


async def on_cull(cow: Cow, db: AsyncSession) -> None:
    cow.status = CowStatus.cull
    cow.current_program = None
    await cancel_active_enrollments(cow, db, EnrollmentStatus.cancelled)


async def run_transitions_for_user(db: AsyncSession, current_user: dict) -> int:
    """Apply timed transitions for the caller's farms before building a report.

    Every endpoint that feeds the technician's work list must call this, or the
    list is assembled from statuses that are a day (or a month) stale — a fresh
    cow past day 70 still counted as fresh, a heifer that never became open.
    Lives here so `reports.py` and `needling.py` share one implementation.
    """
    from app.services.access import get_allowed_farm_ids  # local: avoids a cycle

    farm_ids = await get_allowed_farm_ids(db, current_user)
    return await run_lifecycle_transitions(db, farm_ids=farm_ids)


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
        # Deterministic lock order — two concurrent sweeps over overlapping
        # farm scopes must acquire row locks in the same sequence or they
        # deadlock (FOR UPDATE without ORDER BY locks in scan order).
        .order_by(Cow.id)
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
            # Master Structure: month-13 heifers go straight to the Insemination
            # Program (bred directly), not to the Open report's protocol choice.
            cow.current_program = "Insemination"
            create_notification(
                db, cow.farm_id, cow.id, "open",
                f"Heifer {cow.ear_tag} reached breeding age — ready for the Insemination Program.",
            )
            changed += 1

    changed += await _expire_stale_enrollments(db, farm_ids, today)

    if changed:
        await db.commit()
    return changed


async def _expire_stale_enrollments(
    db: AsyncSession,
    farm_ids: Optional[Iterable[uuid.UUID]],
    today: date,
) -> int:
    """Close out protocols whose final day came and went unactioned.

    Without this an un-actioned final record pins the cow on Timed Breeding
    forever AND (via the same-day overlap rule) suppresses every other injection
    she is due — a silently growing hole in the work list. After
    ABANDONED_PROTOCOL_DAYS past the final day with no insemination, the
    synchronisation has lapsed biologically anyway: cancel it and put her back
    on the Open report so somebody makes a fresh decision.
    """
    cutoff = today - timedelta(days=ABANDONED_PROTOCOL_DAYS)

    # "Abandoned" means nobody is working the protocol — a technician catching
    # up on late shots is not abandonment. Any record completed since the
    # cutoff keeps the enrollment alive.
    rec = aliased(NeedlingRecord)
    recently_worked = (
        select(rec.id)
        .where(
            rec.enrollment_id == NeedlingEnrollment.id,
            rec.completed == True,  # noqa: E712
            rec.completed_date >= cutoff,
        )
        .exists()
    )

    stmt = (
        select(NeedlingEnrollment, Cow, NeedlingRecord.scheduled_date)
        .join(Cow, Cow.id == NeedlingEnrollment.cow_id)
        .join(NeedlingRecord, NeedlingRecord.enrollment_id == NeedlingEnrollment.id)
        .where(
            NeedlingEnrollment.status.in_(
                [EnrollmentStatus.active, EnrollmentStatus.completed_pending_ai]
            ),
            NeedlingRecord.is_final == True,  # noqa: E712
            NeedlingRecord.scheduled_date < cutoff,
            Cow.status == CowStatus.needling,
            ~recently_worked,
        )
        .order_by(Cow.id)
        .with_for_update(of=(NeedlingEnrollment, Cow))
    )
    if farm_ids is not None:
        farm_ids = list(farm_ids)
        if not farm_ids:
            return 0
        stmt = stmt.where(Cow.farm_id.in_(farm_ids))

    changed = 0
    for enrollment, cow, final_date in (await db.execute(stmt)).all():
        enrollment.status = EnrollmentStatus.cancelled
        ensure_transition(cow, CowStatus.open)
        cow.status = CowStatus.open
        cow.current_program = None
        days_late = (today - final_date).days
        create_notification(
            db, cow.farm_id, cow.id, "open",
            f"Cow {cow.ear_tag} was not inseminated {days_late} days after her "
            f"{enrollment.protocol.value} final day — protocol cancelled, she is "
            "Open and needs a new breeding decision.",
        )
        changed += 1
    return changed
