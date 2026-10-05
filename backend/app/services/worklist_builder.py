"""Assembles the technician's three-layer work list in one payload.

    General To-Do (farms today) → Farm To-Do (reports + counts) → Report (cows)

Built server-side so the counts at layer 2 and the rows at layer 3 come from the
same evaluation — they cannot disagree, and the client owns no membership rule.
"""

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Cow, CowStatus, EnrollmentStatus, Farm, FarmVisitAssignment, HeatCheck,
    NeedlingEnrollment, NeedlingRecord, User, VaccinationRecord,
)
from app.services.access import scope_to_farms
from app.services.report_catalog import WorklistContext, build_reports
from app.services.status_engine import is_metestrous_bleeding
from app.services.visits import (
    describe_weekdays, is_visit_due, next_visit_date, resolve_visit, visit_label,
    visit_weekdays, VisitStatus,
)
from app.services.worklists import (
    injection_only, needling_due_stmt, OPEN_ENROLLMENT_STATUSES, TERMINAL_STATUSES,
    timed_breeding_stmt,
)

# The Vet Area is exclusively pregnancy diagnosis (Major_further.md). A vet's
# worklist carries the pregnancy work plus the read-only context around it —
# not the technician's needling/heat/breeding route.
VET_REPORT_TYPES = frozenset({"pregnancy-check", "pregnant", "calving-due"})


# How far ahead the technician is prompted to leave the farmer a note.
#
# The client was specific on the call: "the day before, the technician gets a
# notification ... leave a note for the farmer to do the injection." A week's
# warning was my own reading -- that he would want to be standing on the farm
# at least once before it fell due -- and it is not what he asked for.
FARMER_NOTE_LEAD_DAYS = 1


async def _farmer_injections_by_cow(db: AsyncSession, current_user: dict, today: date,
                                    farm_id: Optional[UUID]) -> dict:
    """Shots the FARMER gives, coming up, that nobody has written a note for.

    The technician does not give these, so they are not on his Injection
    report. What is his job is telling the farmer which cow needs which
    hormone -- so this is the prompt for that note, and it disappears as soon
    as the note exists.
    """
    stmt = (
        select(NeedlingRecord, Cow)
        .join(Cow, Cow.id == NeedlingRecord.cow_id)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .where(
            NeedlingRecord.self_administered == True,  # noqa: E712
            NeedlingRecord.completed == False,  # noqa: E712
            NeedlingRecord.notes.is_(None),
            NeedlingRecord.scheduled_date <= today + timedelta(days=FARMER_NOTE_LEAD_DAYS),
            NeedlingEnrollment.status == EnrollmentStatus.active,
            Cow.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(NeedlingRecord.scheduled_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Cow.farm_id)
    out = {}
    for record, cow in (await db.execute(stmt)).all():
        out.setdefault(str(cow.id), {
            "id": str(record.id),
            "treatment": record.treatment,
            "scheduled_date": record.scheduled_date,
            "days_until": (record.scheduled_date - today).days,
        })
    return out


async def _heat_events_by_cow(db: AsyncSession, current_user: dict, today: date,
                              farm_id: Optional[UUID]) -> dict:
    """Heats seen TODAY, per cow -- the raw material of Today's Breed Report.

    Today only, by design (Josh, Oct 4): a cow not inseminated by the next day
    "is removed from Today's Breed Report with no consequence ... assume
    nothing happened". A heat backdated to yesterday is history, not work.
    Blood on the tail counts as a heat, except the early spotting right after
    a breeding (status_engine.is_metestrous_bleeding), which is not one.
    Exclusions (Do Not Breed, under 60 days in milk, ...) are applied by the
    report itself, so editing a cow's lists takes effect on the next load.
    """
    stmt = (
        select(HeatCheck, Cow)
        .join(Cow, Cow.id == HeatCheck.cow_id)
        .where(
            or_(HeatCheck.heat_detected == True,  # noqa: E712
                HeatCheck.bleeding_event == True),  # noqa: E712
            HeatCheck.check_date == today,
        )
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Cow.farm_id)
    out: dict = {}
    for check, cow in (await db.execute(stmt)).all():
        if not check.heat_detected and check.days_since_insemination is not None \
                and is_metestrous_bleeding(check.days_since_insemination):
            continue
        out[str(cow.id)] = {"detected_on": check.check_date}
    return out


async def _needling_by_cow(db: AsyncSession, current_user: dict, today: date,
                           farm_id: Optional[UUID]) -> dict:
    stmt = scope_to_farms(needling_due_stmt(today), current_user, farm_id, col=Cow.farm_id)
    out = {}
    for record, cow in (await db.execute(stmt)).all():
        key = str(cow.id)
        if key in out:
            # Consecutive-day protocols (Double Ovsynch day 24/25) can leave two
            # shots pending at once; the row shows the oldest, but the extras
            # must be announced, not silently collapsed.
            out[key]["also_pending"] += 1
            continue
        # First due record wins — the query is ordered by scheduled_date, so an
        # overdue shot is what the technician is told to give.
        out[key] = {
            "id": str(record.id),
            "treatment": record.treatment,
            "protocol_day": record.protocol_day,
            "protocol": None,  # resolved below
            "days_overdue": (today - record.scheduled_date).days,
            "enrollment_id": str(record.enrollment_id),
            "also_pending": 0,
        }

    # Resolve the protocol so the instruction reads "Ovsynch, Day 7" rather than
    # the raw enum. /needling/today doesn't carry it, and falling back to
    # cow.current_program leaked "ovsynch" into the technician's line.
    enrollment_ids = {UUID(r["enrollment_id"]) for r in out.values()}
    if enrollment_ids:
        protocols = {
            e.id: e.protocol.value
            for e in (await db.execute(
                select(NeedlingEnrollment).where(NeedlingEnrollment.id.in_(enrollment_ids))
            )).scalars().all()
        }
        for row in out.values():
            row["protocol"] = protocols.get(UUID(row["enrollment_id"]))
    return out


async def _breeding_by_cow(db: AsyncSession, current_user: dict, today: date,
                           farm_id: Optional[UUID]) -> dict:
    stmt = scope_to_farms(timed_breeding_stmt(today), current_user, farm_id, col=Cow.farm_id)
    out = {}
    for record, enrollment, cow, farm in (await db.execute(stmt)).all():
        out.setdefault(str(cow.id), {
            "protocol": enrollment.protocol.value,
            "protocol_day": record.protocol_day,
            "treatment": record.treatment,
            "injection": injection_only(record.treatment),
            "needling_record_id": str(record.id),
            "needling_completed": record.completed,
            "days_overdue": (today - record.scheduled_date).days,
            "missed_shots": 0,
        })

    # The overlap rule pulls the whole cow off the Needling report on her final
    # day, which also hides any earlier shot she missed. Those must surface on
    # the Timed Breeding row rather than disappear from every report.
    if out:
        cow_ids = [UUID(k) for k in out]
        missed = dict((await db.execute(
            select(NeedlingRecord.cow_id, func.count(NeedlingRecord.id))
            .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
            .where(
                NeedlingRecord.cow_id.in_(cow_ids),
                NeedlingRecord.completed == False,  # noqa: E712
                NeedlingRecord.is_final == False,  # noqa: E712
                NeedlingRecord.scheduled_date <= today,
                NeedlingEnrollment.status.in_(OPEN_ENROLLMENT_STATUSES),
            )
            .group_by(NeedlingRecord.cow_id)
        )).all())
        for key, row in out.items():
            row["missed_shots"] = missed.get(UUID(key), 0)
    return out


async def _vaccinations_by_cow(db: AsyncSession, current_user: dict, today: date,
                             farm_id: Optional[UUID]) -> dict:
    """Scheduled vaccinations whose date has arrived — excluding the calving-
    linked day-30 shot, which is the Post Calving Report's job. One record must
    drive exactly one report, or the same shot is counted (and chased) twice.
    """
    stmt = (
        select(VaccinationRecord, Cow)
        .join(Cow, Cow.id == VaccinationRecord.cow_id)
        .where(
            VaccinationRecord.completed == False,  # noqa: E712
            VaccinationRecord.calving_record_id.is_(None),
            VaccinationRecord.scheduled_date <= today,
            Cow.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(VaccinationRecord.scheduled_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Cow.farm_id)
    out = {}
    for record, cow in (await db.execute(stmt)).all():
        out.setdefault(str(cow.id), {
            "id": str(record.id),
            "vaccine_name": record.vaccine_name,
            "scheduled_date": record.scheduled_date.isoformat(),
            "days_overdue": (today - record.scheduled_date).days,
        })
    return out


async def _post_calving_by_cow(db: AsyncSession, current_user: dict,
                               farm_id: Optional[UUID]) -> dict:
    """cow_id -> date of her most recent COMPLETED vaccination (any kind).

    The Post Calving report clears when a shot has been given this lactation —
    whether it was the auto-scheduled calving-linked record or an ad-hoc entry
    for an imported cow. Which record it was doesn't matter; that a shot was
    given since she calved does.
    """
    stmt = (
        select(VaccinationRecord, Cow)
        .join(Cow, Cow.id == VaccinationRecord.cow_id)
        .where(
            VaccinationRecord.completed == True,  # noqa: E712
            Cow.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(
            func.coalesce(VaccinationRecord.completed_date,
                          VaccinationRecord.scheduled_date).desc()
        )
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Cow.farm_id)
    out = {}
    for record, cow in (await db.execute(stmt)).all():
        out.setdefault(str(cow.id), {
            "completed_on": record.completed_date or record.scheduled_date,
        })
    return out


async def build_worklist(
    db: AsyncSession,
    current_user: dict,
    today: date,
    farm_id: Optional[UUID] = None,
) -> dict:
    """The full three-layer work list for the caller, scoped to their farms."""
    role = current_user["role"]
    viewer_id = current_user["id"]

    farms = (await db.execute(
        scope_to_farms(select(Farm), current_user, farm_id, col=Farm.id).order_by(Farm.name)
    )).scalars().all()
    farm_ids = [f.id for f in farms]
    if not farm_ids:
        return {"date": today.isoformat(), "farms": []}

    cows = (await db.execute(
        select(Cow).where(Cow.farm_id.in_(farm_ids)).order_by(Cow.ear_tag)
    )).scalars().all()

    overrides = {
        a.farm_id: a
        for a in (await db.execute(
            select(FarmVisitAssignment).where(
                FarmVisitAssignment.farm_id.in_(farm_ids),
                FarmVisitAssignment.visit_date == today,
            )
        )).scalars().all()
    }

    # Resolve covering technicians' names for the "Reassigned to X — Skip" line.
    covering_ids = {a.assigned_technician_id for a in overrides.values() if a.assigned_technician_id}
    names = {}
    if covering_ids:
        names = {
            u.id: u.name
            for u in (await db.execute(select(User).where(User.id.in_(covering_ids)))).scalars().all()
        }

    needling = await _needling_by_cow(db, current_user, today, farm_id)
    breeding = await _breeding_by_cow(db, current_user, today, farm_id)
    vaccinations = await _vaccinations_by_cow(db, current_user, today, farm_id)
    post_calving = await _post_calving_by_cow(db, current_user, farm_id)
    farmer_injections = await _farmer_injections_by_cow(db, current_user, today, farm_id)
    heat_events = await _heat_events_by_cow(db, current_user, today, farm_id)

    by_farm: dict = {}
    for cow in cows:
        by_farm.setdefault(cow.farm_id, []).append(cow)

    out = []
    for farm in farms:
        override = overrides.get(farm.id)
        due = is_visit_due(farm, today)
        # Admin/farm/vet see every farm in their scope; the rotation + relief
        # reassignment rules are about a technician's own daily route.
        is_admin_view = role in ("admin", "farm", "vet")
        status = resolve_visit(farm, override, viewer_id, is_admin=is_admin_view)
        if status is None:
            continue
        ctx = WorklistContext(
            today=today, role=role, cows=by_farm.get(farm.id, []),
            needling=needling, breeding=breeding, vaccinations=vaccinations,
            post_calving=post_calving, farmer_injections=farmer_injections,
            heat_events=heat_events, farm_self_vaccinate=farm.self_vaccinate,
        )
        reports = build_reports(ctx)
        # Off-rotation with nobody assigned: the farm stays in the payload for
        # EVERY role, flagged not_due. Route screens (a technician's General
        # To-Do) hide these; herd views (a vet's pregnancy list, farm profiles)
        # keep them — a cow's data must not blink in and out with the visit
        # schedule (Major_further: she stays on the Pregnancy Report until a
        # result is entered). Only a plain visit can be downgraded; the other
        # statuses all imply a deliberate override for this date.
        #
        # A cow in heat is bred the day she shows, whatever the rota says
        # (Josh, Sept 17 and again Oct 4) -- so a farm with one on Today's
        # Breed Report stays on the route even on a day it isn't due.
        breeding_today = any(r["type"] == "breed-today" for r in reports)
        if not due and override is None and status is VisitStatus.visit_today \
                and not breeding_today:
            status = VisitStatus.not_due
        if role == "vet":
            reports = [r for r in reports if r["type"] in VET_REPORT_TYPES]
        work = [r for r in reports if r["is_work_report"]]
        covering_name = names.get(override.assigned_technician_id) if override else None

        # An admin sees a reassigned farm as a plain visit (resolve_visit's
        # admin branch), but the label should still say who actually covers it.
        label = visit_label(status, covering_name)
        if (is_admin_view and status is VisitStatus.visit_today and covering_name
                and override.assigned_technician_id != farm.assigned_technician_id):
            label = f"Covered by {covering_name} today"

        out.append({
            "farm_id": str(farm.id),
            "farm_name": farm.name,
            "address": farm.address,
            "city": farm.city,
            "province": farm.province,
            "phone": farm.phone,
            "schedule": status.value,
            "schedule_label": label,
            "covering_technician": covering_name,
            "reassign_reason": override.reason if override else None,
            "visit_weekdays": list(visit_weekdays(farm)),
            "visit_schedule_label": describe_weekdays(farm.visit_weekdays),
            "next_visit_date": (nv.isoformat() if (nv := next_visit_date(farm, today)) else None),
            # Distinct cows: a cow on two reports is still one animal to process.
            "total_cows": len({c["cow_id"] for r in work for c in r["cows"]}),
            "reports": reports,
        })

    # Farms to actually walk into first (busiest first within each band), then
    # today's handed-off visits, then off-rotation reference farms.
    band = {
        VisitStatus.visit_today.value: 0,
        VisitStatus.covering.value: 0,
        VisitStatus.reassigned.value: 1,
        VisitStatus.skipped.value: 1,
        VisitStatus.not_due.value: 2,
    }
    out.sort(key=lambda f: (band.get(f["schedule"], 3), -f["total_cows"]))
    return {"date": today.isoformat(), "farms": out}
