"""
Cow status transition engine.

Rules (from planning docs):
  insemination recorded   → status = inseminated
  heat seen (any time)    → on Today's Breed Report that day unless excluded
                            (breeding_exclusion); an inseminated cow goes open
  heat, not bred that day → open the next day, whatever she was doing
  heat check at day 19-25 → if no heat, stays inseminated
  pregnancy check +ve     → status = pregnant, compute dry_date (day 223) & due_date (day 283)
  pregnancy check -ve     → status = open (protocol selection via Open report)
  bleeding pre-AI         → enrollment cancelled, cow open, auto-enrolled in Ovsynch
  calving recorded        → status = fresh, lactation_number++, clear reproductive fields
                            (only ever recorded by a person; nothing makes her Fresh on a date)
  dry date reached        → status = dry (day 223 post-insemination; farmer notified to change pen)
  fresh day 70            → status = open (entry date pushed to next Mon/Tue/Sat)
  calf day 60             → status = heifer
  heifer day ~395 (13 mo) → status = open (appears on breeding list)
  cull recorded           → status = cull
  marked Do Not Breed     → status = dnb wherever she would be open (open_or_dnb)
Timed transitions run via run_lifecycle_transitions(), invoked by the report
endpoints and POST /admin/run-transitions — never as a GET side effect.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from sqlalchemy.orm import aliased

from app.core.timeutils import farm_tz, local_today
from app.models.models import (
    Cow, CowStatus, Farm, HeatCheck, Insemination, NeedlingEnrollment, NeedlingRecord,
    EnrollmentStatus, ProtocolType,
)
from app.services.notifications import create_notification
from app.services import questions
from app.services.protocols import (
    FIRST_HEAT_CHECK_DAY, final_step_without_hormone, get_scheduled_records, protocol_label,
    self_inject_step, TIMED_AI_PROTOCOLS,
)

GESTATION_DAYS = 283
DRY_OFF_DAY = 223            # days after insemination
# Heat monitoring window, days post-AI. Josh, Oct 4: "every time a cow is
# inseminated she must appear on the Heat Report 19 days later" -- which
# settles the old 19-vs-20 question the docs disagreed on.
HEAT_WINDOW = (19, 25)
# Josh, Oct 2/4: a cow seen in heat is bred that day, unless one of these
# holds. A heat on an excluded cow is still recorded; it just isn't bred.
MIN_DAYS_POST_CALVING_TO_BREED = 60
MIN_AGE_DAYS_TO_BREED = 395  # 13 months -- the same day heifers become breedable
FRESH_TO_OPEN_DAY = 70       # days after calving
CALF_TO_HEIFER_DAY = 60      # days after birth
HEIFER_BREEDING_DAY = 395    # ~13 months after birth
BREEDING_WEEKDAYS = (0, 1, 5)  # Monday, Tuesday, Saturday
# Day a cow comes due for her pregnancy check. Lives here rather than in
# report_catalog because report_catalog imports this module, and the sweep's
# reminder needs the same number the report uses -- one definition, or the
# farm is told on a different day from the one the technician sees.
PREGNANCY_REPORT_DAY = 30
# How many days late a timed reminder may still be raised, so a missed sweep
# does not silently drop it. Bounded because the "already sent" guards cannot
# tell "missed" from "pre-dates the feature".
REMINDER_CATCHUP_DAYS = 3
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
    CowStatus.heifer:      {CowStatus.open, CowStatus.dnb, CowStatus.needling, CowStatus.inseminated,
                            CowStatus.fresh, CowStatus.cull, CowStatus.dead},
    # needling: started by hand before day 70 (test results, Nov 5).
    CowStatus.fresh:       {CowStatus.open, CowStatus.dnb, CowStatus.needling, CowStatus.inseminated,
                            CowStatus.fresh, CowStatus.cull, CowStatus.dead},
    CowStatus.open:        {CowStatus.dnb, CowStatus.needling, CowStatus.inseminated, CowStatus.fresh,
                            CowStatus.cull, CowStatus.dead},
    CowStatus.needling:    {CowStatus.open, CowStatus.dnb, CowStatus.inseminated, CowStatus.fresh,
                            CowStatus.cull, CowStatus.dead},
    # fresh: she calved without the pregnancy check ever being recorded.
    CowStatus.inseminated: {CowStatus.open, CowStatus.dnb, CowStatus.pregnant, CowStatus.fresh,
                            CowStatus.cull, CowStatus.dead},
    CowStatus.pregnant:    {CowStatus.open, CowStatus.dnb, CowStatus.dry, CowStatus.fresh,
                            CowStatus.cull, CowStatus.dead},
    CowStatus.dry:         {CowStatus.fresh, CowStatus.cull, CowStatus.dead},
    # open: taken off the list. fresh: a calving is accepted from any live status.
    CowStatus.dnb:         {CowStatus.open, CowStatus.fresh, CowStatus.cull, CowStatus.dead},
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
    CowStatus.dry, CowStatus.calf, CowStatus.heifer, CowStatus.sold, CowStatus.dead,
}


def is_milking(cow: Cow) -> bool:
    """True when this cow is currently in milk."""
    if cow.status in NON_MILKING_STATUSES:
        return False
    # Cull is a decision, not the day she leaves: she is milked until she goes
    # (test results, Nov 5: "continue telling days in milk") -- unless she was
    # dried off first, which her dry date still says.
    if cow.status == CowStatus.cull and cow.dry_date and cow.dry_date <= local_today():
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


def heat_check_timing_error(days_since: int, has_signal: bool,
                            heat_seen: bool = False) -> Optional[str]:
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
    # Josh's change requests (Nov 20): an Inseminated cow can be marked Seen in
    # heat on any day, and goes on today's breed report. Only blood with no
    # heat seen keeps the lower bound below.
    if heat_seen:
        return None
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


def has_calved(cow: Cow) -> bool:
    """False for a heifer. Josh: a heifer is an animal that has not given
    birth, however old she is -- so she is not in milk and is never dried
    off. A pregnant heifer has no dry date and stays Pregnant until she
    calves (migration 0022)."""
    return (cow.lactation_number or 0) > 0 or cow.last_calving_date is not None


def dry_date_for(cow: Cow, insemination_date: date) -> Optional[date]:
    """Her day-223 dry-off, or None for a heifer (see has_calved)."""
    return compute_dry_date(insemination_date) if has_calved(cow) else None


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


def open_or_dnb(cow: Cow) -> CowStatus:
    """The status she takes when she would go Open.

    Test results, Nov 5: Do Not Breed is a status of its own. It takes over
    from Open, not from the statuses before it: a Fresh cow still owes her
    vaccine and a Pregnant or Dry one has a calf coming, so a cow marked at
    those points keeps that status until she would otherwise be Open.
    """
    return CowStatus.dnb if cow.do_not_breed else CowStatus.open


async def settle_do_not_breed(cow: Cow, db: AsyncSession) -> bool:
    """Bring her status into line with the mark on her record. True if it moved."""
    if cow.do_not_breed and cow.status in (CowStatus.open, CowStatus.needling):
        # A protocol only leads to a breeding she may not have, and one status
        # cannot say both things.
        await cancel_active_enrollments(cow, db, EnrollmentStatus.cancelled)
        cow.status = CowStatus.dnb
        cow.current_program = None
        return True
    if not cow.do_not_breed and cow.status == CowStatus.dnb:
        cow.status = CowStatus.open
        # Never calved: a breeding-age heifer, who is bred directly.
        cow.current_program = None if has_calved(cow) else "Insemination"
        return True
    return False


async def add_protocol_records(
    cow: Cow, enrollment_id, protocol: str, start_date: date, db: AsyncSession,
) -> Optional[NeedlingRecord]:
    """Lay out a protocol's injections, and the farmer's own if the farm does that.

    Both enrollment paths (the endpoint and the bleeding-event transfer) went
    through their own copy of this loop, so a self-injecting farm would have
    been honoured on one route and silently ignored on the other.

    Returns the farmer-administered record when one was created. Nobody is
    told here: the sweep announces it the day before it is due
    (_announce_self_injections).
    """
    farm = await db.get(Farm, cow.farm_id)
    self_inject = bool(farm and farm.self_inject_needling)
    farmer_spec = self_inject_step(protocol, start_date) if self_inject else None
    # The hormone MOVES to the farmer's day; it is not copied there. Adding the
    # day-9 shot while leaving day 10 as "2cc GnRH + Insemination" gave the cow
    # two doses of GnRH.
    ai_only = final_step_without_hormone(protocol) if farmer_spec else None

    for spec in get_scheduled_records(protocol, start_date):
        treatment = spec["treatment"]
        if spec["is_final"] and ai_only:
            treatment = ai_only
        db.add(NeedlingRecord(
            enrollment_id=enrollment_id,
            cow_id=cow.id,
            protocol_day=spec["protocol_day"],
            scheduled_date=spec["scheduled_date"],
            treatment=treatment,
            is_final=spec["is_final"],
        ))

    if farmer_spec is None:
        return None
    spec = farmer_spec

    record = NeedlingRecord(
        enrollment_id=enrollment_id,
        cow_id=cow.id,
        protocol_day=spec["protocol_day"],
        scheduled_date=spec["scheduled_date"],
        treatment=spec["treatment"],
        is_final=False,
        self_administered=True,
    )
    db.add(record)
    # Nobody is told here. The client was specific: "the day before, the
    # technician gets a notification". Telling the farm at enrollment -- nine
    # days early on Ovsynch -- is how a shot gets filed and forgotten. The
    # sweep's _announce_self_injections raises it at the right time.
    return record


async def on_insemination(cow: Cow, insemination: Insemination, db: AsyncSession) -> None:
    """Called immediately after an insemination is recorded."""
    cow.status = CowStatus.inseminated
    cow.current_program = None
    cow.last_insemination_date = insemination.date
    cow.last_insemination_id = insemination.id
    await cancel_active_enrollments(cow, db, EnrollmentStatus.completed)


# A heat can be recorded on these. Josh, Oct 2: "Anytime a cow is in heat,
# no matter conditions, must be inseminated", with four exceptions -- and
# being pregnant is not one of them. The specs read a heat as proof she is
# not carrying ("Fail Heat Report ... sent to Insemination"), so a pregnant or
# dry cow in heat is treated as one whose pregnancy failed. Calves are not
# breedable at all; cull/sold/dead have left the breeding herd. A DNB cow's
# heat is still worth writing down; the app says she is not to be bred.
HEAT_RECORDABLE_STATUSES = {
    CowStatus.heifer, CowStatus.fresh, CowStatus.open, CowStatus.needling,
    CowStatus.inseminated, CowStatus.pregnant, CowStatus.dry, CowStatus.dnb,
}
# A heat on one of these means the breeding she was carrying failed.
_CARRYING_STATUSES = {CowStatus.inseminated, CowStatus.pregnant, CowStatus.dry}


def breeding_list(cow: Cow) -> Optional[str]:
    """The breeding list she is on, by name, or None (Josh, Oct 2/4)."""
    return "Do Not Breed" if cow.do_not_breed else None


def open_message(cow: Cow, how: str) -> str:
    """"<cow> is Open -- select a needling protocol", unless she is marked Do
    Not Breed: then she is DNB, not Open, and that instruction is the one
    thing not to do."""
    if breeding_list(cow):
        return f"{cow.label} is DNB. She is on the Do Not Breed list, so no protocol is needed."
    return f"{cow.label} {how} — select a needling protocol."


def breeding_exclusion(cow: Cow, today: date, overruled: bool = False) -> Optional[str]:
    """Why a cow seen in heat must NOT be bred, or None if she must be.

    Josh, Oct 4 -- she does not go on Today's Breed Report if she is: under 60
    days post calving, on the Do Not Breed list, Cull, or under 13 months of
    age. An unknown birth date or calving date does not exclude her: most
    milking cows are entered without one, and "we don't know" is not a reason
    to waste a heat.

    overruled: the farmer wants her bred anyway. That sets aside the 60-day
    rule and only that one (test results, Nov 5; see can_overrule).
    """
    if cow.status in (CowStatus.cull, CowStatus.sold, CowStatus.dead):
        return "she is a cull" if cow.status == CowStatus.cull else f"she is {cow.status.value}"
    listed = breeding_list(cow)
    if listed:
        return f"she is on the {listed} list"
    if cow.status == CowStatus.calf:
        return "she is a calf"
    if cow.date_of_birth and (today - cow.date_of_birth).days < MIN_AGE_DAYS_TO_BREED:
        return "she is under 13 months old"
    if not overruled and cow.last_calving_date and \
            (today - cow.last_calving_date).days < MIN_DAYS_POST_CALVING_TO_BREED:
        return f"she is under {MIN_DAYS_POST_CALVING_TO_BREED} days post calving"
    return None


def can_overrule(cow: Cow, today: date) -> bool:
    """Is the 60-day rule the one thing keeping her off Today's Breed Report?

    Test results, Nov 5: the farmer may overrule it, after an "Are you sure?".
    Cull, Do Not Breed and the age limit are not his to overrule here.
    """
    return breeding_exclusion(cow, today) is not None \
        and breeding_exclusion(cow, today, overruled=True) is None


def announce_breed_today(cow: Cow, db: AsyncSession) -> None:
    create_notification(
        db, cow.farm_id, cow.id, "breeding_due",
        f"{cow.label} was seen in heat — she is on Today's Breed Report "
        "and must be bred today. If she isn't, she goes to Open tomorrow.",
    )


async def _answer_heat_check(cow: Cow, detected_on: date, db: AsyncSession) -> None:
    """A heat answers the Prostaglandin check she was due, however it was seen.

    Marked done without ending the protocol: if this is her last day, the AI
    that follows closes it, and if nobody breeds her the sweep makes her Open
    (_open_after_unbred_heat). on_final_record_completed would send her to
    Open now, while she is in heat and waiting to be bred.
    """
    record = await db.scalar(
        select(NeedlingRecord)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .where(
            NeedlingRecord.cow_id == cow.id,
            NeedlingEnrollment.protocol == ProtocolType.prostaglandin_heat,
            NeedlingEnrollment.status == EnrollmentStatus.active,
            NeedlingRecord.protocol_day >= FIRST_HEAT_CHECK_DAY,
            NeedlingRecord.scheduled_date <= detected_on,
        )
        .order_by(NeedlingRecord.scheduled_date.desc())
        .limit(1)
    )
    if record is not None and not record.completed:
        record.completed = True
        record.completed_date = detected_on
        record.notes = f"{record.notes}\nIn heat" if record.notes else "In heat"


async def on_heat_detected(cow: Cow, db: AsyncSession, detected_on: date) -> Optional[str]:
    """A heat was seen (incl. blood on tail). Returns why she is not to be
    bred, or None when she goes on Today's Breed Report.

    Josh, Oct 4: she goes on Today's Breed Report at once. Whether she is bred
    is only known at the end of the day, so nothing about her is changed here
    except for a cow that was carrying a breeding (inseminated, pregnant,
    dry): a heat means it failed, so she is open again whatever happens next,
    and the pregnancy-cycle dates belong to the cycle that just ended. Not bred
    that day, the next day's sweep makes her Open (_open_after_unbred_heat).
    """
    was_inseminated = cow.status in _CARRYING_STATUSES
    if was_inseminated:
        cow.status = open_or_dnb(cow)
        cow.current_program = None
        # last_insemination_id/date stay: the failed AI is a true fact.
        cow.due_date = None
        cow.dry_date = None
        cow.dry_off_confirmed_date = None
    elif cow.status == CowStatus.needling:
        await _answer_heat_check(cow, detected_on, db)

    reason = breeding_exclusion(cow, detected_on)
    if reason is None and detected_on == local_today():
        announce_breed_today(cow, db)
    elif reason is None and was_inseminated:
        # Written up after the day: the heat is already gone, so there is no
        # breeding to ask for -- only the failed insemination to report.
        create_notification(
            db, cow.farm_id, cow.id, "open",
            f"{cow.label} was seen in heat on {detected_on}, so she is not "
            "pregnant. She is back on the Open Cow Report.",
        )
    elif was_inseminated:
        # A listed cow is kept off the Open Cow Report too, so only say she is
        # back on it when she is.
        create_notification(
            db, cow.farm_id, cow.id, "open",
            f"{cow.label} was seen in heat, so she is not pregnant. She is not to "
            f"be bred ({reason})"
            + ("." if breeding_list(cow) else " and is back on the Open Cow Report."),
        )
    return reason


async def on_pregnancy_confirmed(cow: Cow, insemination_date: date, db: AsyncSession) -> None:
    """Called when vet confirms pregnancy."""
    cow.status = CowStatus.pregnant
    cow.due_date = compute_due_date(insemination_date)
    cow.dry_date = dry_date_for(cow, insemination_date)


async def on_pregnancy_negative(cow: Cow, db: AsyncSession) -> None:
    """Not pregnant (or cysts found) — back to Open for protocol selection."""
    cow.status = open_or_dnb(cow)
    cow.current_program = None
    _clear_reproductive_fields(cow)
    create_notification(
        db, cow.farm_id, cow.id, "open",
        open_message(cow, "is Open"),
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
    target = open_or_dnb(cow)
    ensure_transition(cow, target)
    cow.status = target
    cow.current_program = None
    create_notification(
        db, cow.farm_id, cow.id, "open",
        open_message(cow, f"finished {protocol_label(enrollment.protocol)} and is Open"),
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
        # A protocol only starts on a Monday, Tuesday or Saturday (Josh) --
        # today if it is one, else the next.
        start_date = adjust_to_breeding_day(local_today())
    enrollment = NeedlingEnrollment(
        cow_id=cow.id, protocol=ProtocolType.ovsynch, start_date=start_date,
    )
    db.add(enrollment)
    await db.flush()
    await add_protocol_records(
        cow, enrollment.id, ProtocolType.ovsynch.value, start_date, db)
    ensure_transition(cow, CowStatus.needling)
    cow.status = CowStatus.needling
    cow.current_program = ProtocolType.ovsynch.value
    create_notification(
        db, cow.farm_id, cow.id, "open",
        f"{cow.label} had a bleeding event and was transferred into the Ovsynch needling program.",
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
    # Counted here and only here. The old day-283 rule deliberately did not, so
    # a cow it made Fresh is counted exactly once when her calving is recorded.
    cow.lactation_number = (cow.lactation_number or 0) + 1
    cow.last_calving_date = calving_date
    cow.current_program = None
    cow.calving_assumed = False
    _clear_reproductive_fields(cow)
    # Dry-off has always notified the farm; calving -- the other end of the
    # same pen change, and the moment she goes back into the milking string --
    # silently did not.
    create_notification(
        db, cow.farm_id, cow.id, "calving",
        f"{cow.label} has calved and is now Fresh — she goes back into the "
        "milking herd.",
    )


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

      pregnant + dry_date reached      → dry (+ "stop milking" notification)
      fresh + day 70 (next Mon/Tue/Sat)→ open (+ notification)
      calf + day 60                    → heifer
      heifer + day 395 (~13 months)    → open (breeding-eligible, + notification)

    A marked cow goes to DNB wherever these say open (open_or_dnb). Nothing
    here makes a Dry cow Fresh: that is a calving, and a person records it.

    farm_ids: restrict the sweep to these farms (None = all farms).
    """
    if today is None:
        today = local_today()

    stmt = (
        select(Cow)
        .where(Cow.status.in_([
            CowStatus.pregnant, CowStatus.fresh, CowStatus.calf, CowStatus.heifer,
        ]))
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
        # has_calved: a heifer has no dry date, but one written before that
        # rule (or by an import) must still not be told to stop milking.
        if cow.status == CowStatus.pregnant and cow.dry_date and cow.dry_date <= today \
                and has_calved(cow):
            cow.status = CowStatus.dry
            # Josh's change requests (Nov 20): the farm is asked, Yes / No.
            questions.ask_dry_pen(db, cow)
            changed += 1
            continue

        if cow.status == CowStatus.fresh and cow.last_calving_date:
            if cow.calving_assumed:
                # Made Fresh on her due date by the old day-283 rule (test
                # results, Nov 5, ended it), so her calving date is a guess,
                # not a record. Moving her to Open would take "Record Calving"
                # away for good, and recording it once she is bred again would
                # be worse: a calving resets her pregnancy. The voluntary
                # waiting period is measured from the REAL calving anyway, so
                # she waits here, on the Fresh report, until someone records it.
                continue
            entry_date = adjust_to_breeding_day(
                cow.last_calving_date + timedelta(days=FRESH_TO_OPEN_DAY)
            )
            if entry_date <= today:
                cow.status = open_or_dnb(cow)
                cow.current_program = None
                create_notification(
                    db, cow.farm_id, cow.id, "open",
                    open_message(cow, "entered the Open Program"),
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
            cow.status = open_or_dnb(cow)
            if cow.status == CowStatus.open:
                # Master Structure: month-13 heifers go straight to the
                # Insemination Program (bred directly), not to the Open
                # report's protocol choice.
                cow.current_program = "Insemination"
                create_notification(
                    db, cow.farm_id, cow.id, "open",
                    f"Heifer {cow.label} reached breeding age — ready for the Insemination Program.",
                )
            changed += 1

    changed += await _settle_marked_cows(db, farm_ids)
    changed += await _open_after_unbred_heat(db, farm_ids, today)
    changed += await _expire_stale_enrollments(db, farm_ids, today)
    changed += await _remind_pregnancy_checks(db, farm_ids, today)
    changed += await _announce_self_injections(db, farm_ids, today)
    changed += await questions.ask_birth_checks(db, farm_ids, today)

    if changed:
        await db.commit()
    return changed


async def _settle_marked_cows(
    db: AsyncSession, farm_ids: Optional[Iterable[uuid.UUID]],
) -> int:
    """Any cow marked Do Not Breed who is still Open or on a protocol.

    Every route to Open goes through open_or_dnb, so this is for cows marked
    before DNB was a status: the migration leaves them for this sweep, because
    the build it replaces cannot read the new value (migration 0023).
    """
    stmt = (
        select(Cow)
        .where(
            Cow.do_not_breed == True,  # noqa: E712
            Cow.status.in_((CowStatus.open, CowStatus.needling)),
        )
        .order_by(Cow.id)
        .with_for_update()
    )
    if farm_ids is not None:
        farm_ids = list(farm_ids)
        if not farm_ids:
            return 0
        stmt = stmt.where(Cow.farm_id.in_(farm_ids))

    changed = 0
    for cow in (await db.execute(stmt)).scalars().all():
        changed += await settle_do_not_breed(cow, db)
    return changed


# How far back the sweep looks for a heat nobody bred. It runs whenever reports
# load, so in practice it acts the next morning; the window only covers days
# nobody opened the app, and keeps the query off the whole heat history.
UNBRED_HEAT_LOOKBACK_DAYS = 14


async def _open_after_unbred_heat(
    db: AsyncSession, farm_ids: Optional[Iterable[uuid.UUID]], today: date,
) -> int:
    """A cow seen in heat and not inseminated that day is Open the next day.

    Josh (Oct 2026): "any cow, it doesn't matter the situation, that's in heat
    that is not inseminated that day, the next day is automatically enrolled
    to open". Any cow: a protocol she was on stops, a heifer leaves the
    Insemination Program, a fresh cow does not wait for day 70 -- including
    one that was not allowed on Today's Breed Report (under 60 days, under 13
    months, on a breeding list). A listed cow goes to DNB instead of Open.

    Only two things leave her as she is:
      * she was bred that day or since -- the heat was used;
      * a protocol was started on a LATER day than the heat. The move
        happens once, the next day; a protocol chosen after it is the next
        step taken from Open, and cancelling it would repeat every day of
        this sweep's look-back window.
    """
    stmt = (
        select(HeatCheck, Cow)
        .join(Cow, Cow.id == HeatCheck.cow_id)
        .where(
            or_(HeatCheck.heat_detected == True,  # noqa: E712
                HeatCheck.bleeding_event == True),  # noqa: E712
            HeatCheck.check_date < today,
            HeatCheck.check_date >= today - timedelta(days=UNBRED_HEAT_LOOKBACK_DAYS),
            Cow.status.in_((CowStatus.needling, CowStatus.fresh, CowStatus.open,
                            CowStatus.heifer)),
        )
        .order_by(HeatCheck.check_date.desc(), HeatCheck.created_at.desc())
    )
    if farm_ids is not None:
        farm_ids = list(farm_ids)
        if not farm_ids:
            return 0
        stmt = stmt.where(Cow.farm_id.in_(farm_ids))

    changed = 0
    done: set = set()
    for check, cow in (await db.execute(stmt)).all():
        if cow.id in done:
            continue
        done.add(cow.id)  # her latest heat decides
        if not check.heat_detected and check.days_since_insemination is not None \
                and is_metestrous_bleeding(check.days_since_insemination):
            continue  # spotting after a breeding is not a heat
        if cow.last_insemination_date and cow.last_insemination_date >= check.check_date:
            continue
        if cow.status == CowStatus.open and cow.current_program is None:
            continue  # already Open
        if cow.status == CowStatus.needling:
            day_after = datetime.combine(check.check_date + timedelta(days=1), time.min,
                                         tzinfo=farm_tz())
            started_later = await db.scalar(
                select(NeedlingEnrollment.id).where(
                    NeedlingEnrollment.cow_id == cow.id,
                    NeedlingEnrollment.status.in_(
                        [EnrollmentStatus.active, EnrollmentStatus.completed_pending_ai]),
                    NeedlingEnrollment.created_at >= day_after,
                ).limit(1)
            )
            if started_later:
                continue
        await cancel_active_enrollments(cow, db, EnrollmentStatus.cancelled)
        cow.status = open_or_dnb(cow)
        cow.current_program = None
        create_notification(
            db, cow.farm_id, cow.id, "open",
            open_message(cow, f"was seen in heat on {check.check_date} and not "
                              "inseminated, so she is Open again"),
        )
        changed += 1
    return changed


async def _announce_self_injections(
    db: AsyncSession, farm_ids: Optional[Iterable[uuid.UUID]], today: date,
) -> int:
    """The day before a farmer gives his own shot, say so -- once.

    "The day before, the technician gets a notification ... leave a note for
    the farmer to do the injection." The notification is farm-addressed, which
    is what reaches both of them: the farm learns which cow needs which
    hormone tomorrow, and the technician covering that farm sees the same
    line and is prompted to leave the note (the Farmer Injection row on his
    To-Do list opens the form).

    Same shape as the pregnancy reminder: a short catch-up window so a missed
    sweep does not lose it, and a guard on an existing notification so it is
    not repeated every six hours.
    """
    from app.models.models import Notification

    lead = timedelta(days=1)
    stmt = (
        select(NeedlingRecord, Cow, NeedlingEnrollment)
        .join(Cow, Cow.id == NeedlingRecord.cow_id)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .where(
            NeedlingRecord.self_administered == True,  # noqa: E712
            NeedlingRecord.completed == False,  # noqa: E712
            NeedlingEnrollment.status == EnrollmentStatus.active,
            # Due tomorrow, or due within the catch-up window and not yet told.
            NeedlingRecord.scheduled_date <= today + lead,
            NeedlingRecord.scheduled_date >= today - timedelta(days=REMINDER_CATCHUP_DAYS),
        )
        .order_by(Cow.id)
    )
    if farm_ids is not None:
        farm_ids = list(farm_ids)
        if not farm_ids:
            return 0
        stmt = stmt.where(Cow.farm_id.in_(farm_ids))

    sent = 0
    for record, cow, enrollment in (await db.execute(stmt)).all():
        if breeding_list(cow):
            continue  # listed after her protocol began: no shot to ask for
        already = await db.execute(
            select(Notification.id).where(
                Notification.cow_id == cow.id,
                Notification.type == "self_inject",
                # "Told during THIS protocol". Keyed on the enrollment's start
                # rather than on the shot's date: the announcement is always
                # written after day 1, so its wall-clock created_at is always
                # past start_date -- whereas comparing created_at against the
                # shot's calendar date breaks the moment `today` and the wall
                # clock disagree (a sweep run for a past date, or a test).
                # A day of slack covers the farm-timezone/UTC seam.
                Notification.created_at >= datetime.combine(
                    enrollment.start_date - timedelta(days=1),
                    time.min, tzinfo=timezone.utc,
                ),
            ).limit(1)
        )
        if already.scalar() is not None:
            continue
        if record.scheduled_date < today:
            # Caught up after a missed sweep. Asking for it "on the 23rd" on
            # the 26th reads as a future instruction; say it is late instead.
            message = (
                f"{cow.label} was due {record.treatment} on "
                f"{record.scheduled_date.isoformat()} — the farm gives this one. "
                "If it has not been given, speak to your technician before "
                "insemination."
            )
        else:
            when = "tomorrow" if record.scheduled_date == today + lead else "today"
            message = (
                f"{cow.label} needs {record.treatment} {when} — the farm gives "
                "this one, the day before insemination. Technician: leave the note."
            )
        create_notification(db, cow.farm_id, cow.id, "self_inject", message)
        sent += 1
    return sent


async def _remind_pregnancy_checks(
    db: AsyncSession, farm_ids: Optional[Iterable[uuid.UUID]], today: date,
) -> int:
    """Tell the farm when a cow comes due for her pregnancy check.

    The check has always appeared on the technician's Pregnancy report on the
    day it falls due; nobody told the FARM, so booking the vet depended on
    somebody opening the app that morning.

    Sent once per insemination, not once per sweep: the sweep runs several
    times a day, and "due for a check" arriving four times before lunch is how
    a farmer learns to ignore the feed. The guard is a notification of this
    type already sitting against the cow since she was last bred -- which also
    survives a restart, unlike anything held in memory.
    """
    from app.models.models import Notification

    stmt = (
        select(Cow)
        .where(
            Cow.status == CowStatus.inseminated,
            Cow.last_insemination_date.isnot(None),
            # A short window rather than the exact day. The sweep runs every
            # six hours and on every boot, but a day-long outage -- a stalled
            # redeploy, the scheduler switched off -- would otherwise skip that
            # day's cows for good, and nothing would ever say so. The window is
            # short because the "already told" guard below only knows about
            # cows told AFTER this feature shipped: on the first deploy every
            # cow inside the window is announced at once, so it is kept to a
            # few days rather than a week.
            Cow.last_insemination_date
            <= today - timedelta(days=PREGNANCY_REPORT_DAY),
            Cow.last_insemination_date
            >= today - timedelta(days=PREGNANCY_REPORT_DAY + REMINDER_CATCHUP_DAYS),
        )
        .order_by(Cow.id)
    )
    if farm_ids is not None:
        farm_ids = list(farm_ids)
        if not farm_ids:
            return 0
        stmt = stmt.where(Cow.farm_id.in_(farm_ids))

    sent = 0
    for cow in (await db.execute(stmt)).scalars().all():
        already = await db.execute(
            select(Notification.id)
            .where(
                Notification.cow_id == cow.id,
                Notification.type == "preg_check",
                Notification.created_at
                >= datetime.combine(cow.last_insemination_date, time.min, tzinfo=timezone.utc),
            )
            .limit(1)
        )
        if already.scalar() is not None:
            continue
        # Her real day, not PREGNANCY_REPORT_DAY: a reminder sent inside the
        # catch-up window ("day 30" to a cow on day 33) states a wrong fact.
        create_notification(
            db, cow.farm_id, cow.id, "preg_check",
            f"{cow.label} is day {(today - cow.last_insemination_date).days} since "
            "insemination — she is due for her pregnancy check.",
        )
        sent += 1
    return sent


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
        target = open_or_dnb(cow)
        ensure_transition(cow, target)
        cow.status = target
        cow.current_program = None
        days_late = (today - final_date).days
        create_notification(
            db, cow.farm_id, cow.id, "open",
            f"{cow.label} was not inseminated {days_late} days after her "
            f"{protocol_label(enrollment.protocol)} final day — protocol cancelled, she is "
            "Open and needs a new breeding decision.",
        )
        changed += 1
    return changed
