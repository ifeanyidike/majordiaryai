from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.timeutils import local_today
from app.models.models import (
    Cow, Farm, CowStatus, Insemination, PregnancyCheck, PregnancyResult,
    NeedlingEnrollment, NeedlingRecord, EnrollmentStatus,
    VaccinationRecord,
)
from app.schemas.reports import (
    HerdSummary, CowReportRow, DailyTaskSummary, PregnancyCheckDueReport, TimedBreedingRow,
)
from app.services.access import get_allowed_farm_ids, scope_to_farms
from app.services.status_engine import run_lifecycle_transitions
from datetime import date, timedelta
from typing import List, Optional
import uuid

router = APIRouter()

TERMINAL_STATUSES = (CowStatus.cull, CowStatus.sold, CowStatus.dead)


async def _run_transitions_scoped(db: AsyncSession, current_user: dict) -> None:
    """Apply timed lifecycle transitions for the caller's farms before reporting."""
    farm_ids = await get_allowed_farm_ids(db, current_user)
    await run_lifecycle_transitions(db, farm_ids=farm_ids)


def _next_pregnancy_check_date(today: date) -> date:
    """Default pregnancy check days are the 1st and 14th of every month."""
    if today.day in (1, 14):
        return today
    if today.day < 14:
        return today.replace(day=14)
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


def _cow_to_report_row(cow: Cow, today: date) -> dict:
    days_since = (
        (today - cow.last_insemination_date).days
        if cow.last_insemination_date else None
    )
    days_until = (
        (cow.due_date - today).days
        if cow.due_date else None
    )
    return {
        "id": cow.id,
        "ear_tag": cow.ear_tag,
        "farm_id": cow.farm_id,
        "farm_name": cow.farm.name if cow.farm else "",
        "breed": cow.breed,
        "status": cow.status,
        "health_status": cow.health_status,
        "recheck_due_date": cow.recheck_due_date,
        "lactation_number": cow.lactation_number,
        "last_calving_date": cow.last_calving_date,
        "last_insemination_date": cow.last_insemination_date,
        "due_date": cow.due_date,
        "dry_date": cow.dry_date,
        "days_since_insemination": days_since,
        "days_until_due": days_until,
    }


@router.get("/herd-summary", response_model=List[HerdSummary])
async def herd_summary(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-farm breakdown of cow counts by status, plus reproduction KPIs."""
    await _run_transitions_scoped(db, current_user)
    today = local_today()

    stmt = (
        select(
            Farm.id.label("farm_id"),
            Farm.name.label("farm_name"),
            func.count(Cow.id).label("total"),
            func.count(Cow.id).filter(Cow.status == CowStatus.calf).label("calf"),
            func.count(Cow.id).filter(Cow.status == CowStatus.heifer).label("heifer"),
            func.count(Cow.id).filter(Cow.status == CowStatus.fresh).label("fresh"),
            func.count(Cow.id).filter(Cow.status == CowStatus.open).label("open"),
            func.count(Cow.id).filter(Cow.status == CowStatus.needling).label("needling"),
            func.count(Cow.id).filter(Cow.status == CowStatus.inseminated).label("inseminated"),
            func.count(Cow.id).filter(Cow.status == CowStatus.pregnant).label("pregnant"),
            func.count(Cow.id).filter(Cow.status == CowStatus.dry).label("dry"),
            func.count(Cow.id).filter(Cow.status == CowStatus.cull).label("cull"),
            func.count(Cow.id).filter(Cow.status == CowStatus.sold).label("sold"),
            func.count(Cow.id).filter(Cow.status == CowStatus.dead).label("dead"),
        )
        .outerjoin(Cow, Cow.farm_id == Farm.id)
        .group_by(Farm.id, Farm.name)
        .order_by(Farm.name)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Farm.id)
    result = await db.execute(stmt)
    rows = {r._mapping["farm_id"]: dict(r._mapping) for r in result.all()}
    if not rows:
        return []
    farm_ids = list(rows.keys())

    # Services (total inseminations) per farm
    services_q = (
        select(Cow.farm_id, func.count(Insemination.id).label("n"))
        .join(Cow, Cow.id == Insemination.cow_id)
        .where(Cow.farm_id.in_(farm_ids))
        .group_by(Cow.farm_id)
    )
    services = {r.farm_id: r.n for r in (await db.execute(services_q)).all()}

    # Inseminations with a recorded pregnancy-check result, and conceptions
    # (conception = insemination confirmed pregnant).
    checked_q = (
        select(Cow.farm_id, func.count(func.distinct(PregnancyCheck.insemination_id)).label("n"))
        .join(Cow, Cow.id == PregnancyCheck.cow_id)
        .where(Cow.farm_id.in_(farm_ids), PregnancyCheck.result.isnot(None))
        .group_by(Cow.farm_id)
    )
    checked = {r.farm_id: r.n for r in (await db.execute(checked_q)).all()}

    conceptions_q = (
        select(Cow.farm_id, func.count(func.distinct(PregnancyCheck.insemination_id)).label("n"))
        .join(Cow, Cow.id == PregnancyCheck.cow_id)
        .where(Cow.farm_id.in_(farm_ids), PregnancyCheck.result == PregnancyResult.pregnant)
        .group_by(Cow.farm_id)
    )
    conceptions = {r.farm_id: r.n for r in (await db.execute(conceptions_q)).all()}

    # Upcoming calvings within 30 days
    calvings_q = (
        select(Cow.farm_id, func.count(Cow.id).label("n"))
        .where(
            Cow.farm_id.in_(farm_ids),
            Cow.status.in_([CowStatus.pregnant, CowStatus.dry]),
            Cow.due_date.isnot(None),
            Cow.due_date <= today + timedelta(days=30),
        )
        .group_by(Cow.farm_id)
    )
    upcoming = {r.farm_id: r.n for r in (await db.execute(calvings_q)).all()}

    out = []
    for fid, row in rows.items():
        n_services = services.get(fid, 0)
        n_checked = checked.get(fid, 0)
        n_conceived = conceptions.get(fid, 0)
        breeding_herd = (row["open"] + row["needling"] + row["inseminated"]
                         + row["pregnant"] + row["dry"] + row["fresh"])
        row["pregnancy_rate"] = (
            round((row["pregnant"] + row["dry"]) / breeding_herd, 3) if breeding_herd else None
        )
        row["conception_rate"] = round(n_conceived / n_checked, 3) if n_checked else None
        row["services_per_conception"] = (
            round(n_services / n_conceived, 2) if n_conceived else None
        )
        row["upcoming_calvings_30d"] = upcoming.get(fid, 0)
        out.append(row)
    return out


@router.get("/pregnant", response_model=List[CowReportRow])
async def pregnant_cows(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _run_transitions_scoped(db, current_user)
    stmt = (
        select(Cow).where(Cow.status == CowStatus.pregnant)
        .options(selectinload(Cow.farm))
        .order_by(Cow.due_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id)
    result = await db.execute(stmt)
    today = local_today()
    return [_cow_to_report_row(c, today) for c in result.scalars().all()]


@router.get("/open", response_model=List[CowReportRow])
async def open_cows(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _run_transitions_scoped(db, current_user)
    stmt = (
        select(Cow).where(Cow.status == CowStatus.open)
        .options(selectinload(Cow.farm))
        .order_by(Cow.last_calving_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id)
    result = await db.execute(stmt)
    today = local_today()
    return [_cow_to_report_row(c, today) for c in result.scalars().all()]


@router.get("/breeding-due", response_model=List[CowReportRow])
async def breeding_due(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cows returned to the Insemination Program (e.g. after a detected heat) —
    actionable breeding worklist."""
    stmt = (
        select(Cow)
        .where(Cow.status == CowStatus.open, Cow.current_program == "Insemination")
        .options(selectinload(Cow.farm))
        .order_by(Cow.ear_tag)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id)
    result = await db.execute(stmt)
    today = local_today()
    return [_cow_to_report_row(c, today) for c in result.scalars().all()]


@router.get("/timed-breeding", response_model=List[TimedBreedingRow])
async def timed_breeding(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cows in a needling enrollment whose final (AI) protocol day is today or
    past and that have not yet been inseminated."""
    today = local_today()
    stmt = (
        select(NeedlingRecord, NeedlingEnrollment, Cow, Farm)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .join(Cow, Cow.id == NeedlingRecord.cow_id)
        .join(Farm, Farm.id == Cow.farm_id)
        .where(
            NeedlingRecord.is_final == True,
            NeedlingRecord.scheduled_date <= today,
            NeedlingEnrollment.status.in_(
                [EnrollmentStatus.active, EnrollmentStatus.completed_pending_ai]
            ),
            Cow.status == CowStatus.needling,
        )
        .order_by(NeedlingRecord.scheduled_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Cow.farm_id)
    result = await db.execute(stmt)
    return [
        {
            "cow_id": cow.id,
            "ear_tag": cow.ear_tag,
            "farm_id": cow.farm_id,
            "farm_name": farm.name,
            "enrollment_id": enrollment.id,
            "protocol": enrollment.protocol,
            "protocol_day": record.protocol_day,
            "scheduled_date": record.scheduled_date,
            "days_overdue": (today - record.scheduled_date).days,
        }
        for record, enrollment, cow, farm in result.all()
    ]


@router.get("/heat-check", response_model=List[CowReportRow])
async def heat_check_due(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cows inseminated 20-25 days ago — due for heat check."""
    today = local_today()
    window_start = today - timedelta(days=25)
    window_end = today - timedelta(days=20)

    stmt = (
        select(Cow)
        .where(
            Cow.status == CowStatus.inseminated,
            Cow.last_insemination_date >= window_start,
            Cow.last_insemination_date <= window_end,
        )
        .options(selectinload(Cow.farm))
        .order_by(Cow.last_insemination_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id)
    result = await db.execute(stmt)
    return [_cow_to_report_row(c, today) for c in result.scalars().all()]


@router.get("/pregnancy-check-due", response_model=PregnancyCheckDueReport)
async def pregnancy_check_due(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cows inseminated 30+ days ago — due for pregnancy check by vet.
    next_check_date is the next default check day (1st or 14th of the month)."""
    today = local_today()
    cutoff = today - timedelta(days=30)

    stmt = (
        select(Cow)
        .where(
            Cow.status == CowStatus.inseminated,
            Cow.last_insemination_date <= cutoff,
        )
        .options(selectinload(Cow.farm))
        .order_by(Cow.last_insemination_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id)
    result = await db.execute(stmt)
    return {
        "next_check_date": _next_pregnancy_check_date(today),
        "cows": [_cow_to_report_row(c, today) for c in result.scalars().all()],
    }


@router.get("/dry-off-due", response_model=List[CowReportRow])
async def dry_off_due(
    farm_id: Optional[uuid.UUID] = None,
    days_ahead: int = 14,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pregnant cows whose dry date is within the next N days — including overdue."""
    await _run_transitions_scoped(db, current_user)
    today = local_today()
    cutoff = today + timedelta(days=days_ahead)

    stmt = (
        select(Cow)
        .where(
            Cow.status == CowStatus.pregnant,
            Cow.dry_date.isnot(None),
            Cow.dry_date <= cutoff,
        )
        .options(selectinload(Cow.farm))
        .order_by(Cow.dry_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id)
    result = await db.execute(stmt)
    rows = []
    for c in result.scalars().all():
        row = _cow_to_report_row(c, today)
        row["days_overdue"] = max(0, (today - c.dry_date).days) if c.dry_date else None
        rows.append(row)
    return rows


@router.get("/due-to-calve", response_model=List[CowReportRow])
async def due_to_calve(
    farm_id: Optional[uuid.UUID] = None,
    days_ahead: int = 21,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dry/pregnant cows due to calve within the next N days — including overdue."""
    await _run_transitions_scoped(db, current_user)
    today = local_today()
    cutoff = today + timedelta(days=days_ahead)

    stmt = (
        select(Cow)
        .where(
            Cow.status.in_([CowStatus.pregnant, CowStatus.dry]),
            Cow.due_date.isnot(None),
            Cow.due_date <= cutoff,
        )
        .options(selectinload(Cow.farm))
        .order_by(Cow.due_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id)
    result = await db.execute(stmt)
    rows = []
    for c in result.scalars().all():
        row = _cow_to_report_row(c, today)
        row["days_overdue"] = max(0, (today - c.due_date).days) if c.due_date else None
        rows.append(row)
    return rows


@router.get("/cull", response_model=List[CowReportRow])
async def cull_list(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Cow).where(Cow.status == CowStatus.cull)
        .options(selectinload(Cow.farm))
        .order_by(Cow.ear_tag)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id)
    result = await db.execute(stmt)
    today = local_today()
    return [_cow_to_report_row(c, today) for c in result.scalars().all()]


@router.get("/daily-tasks", response_model=DailyTaskSummary)
async def daily_task_summary(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Counts of all outstanding tasks for today — used in dashboard cards."""
    await _run_transitions_scoped(db, current_user)
    today = local_today()
    farm_ids = await get_allowed_farm_ids(db, current_user)

    needling_q = (
        select(func.count(NeedlingRecord.id))
        .join(Cow, Cow.id == NeedlingRecord.cow_id)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .where(
            NeedlingRecord.scheduled_date <= today,
            NeedlingRecord.completed == False,
            NeedlingEnrollment.status == EnrollmentStatus.active,
            Cow.status.notin_(TERMINAL_STATUSES),
        )
    )
    vaccinations_q = (
        select(func.count(VaccinationRecord.id))
        .join(Cow, Cow.id == VaccinationRecord.cow_id)
        .where(
            VaccinationRecord.scheduled_date <= today,
            VaccinationRecord.completed == False,
            Cow.status.notin_(TERMINAL_STATUSES),
        )
    )
    heat_window_start = today - timedelta(days=25)
    heat_window_end = today - timedelta(days=20)
    heat_q = select(func.count(Cow.id)).where(
        Cow.status == CowStatus.inseminated,
        Cow.last_insemination_date >= heat_window_start,
        Cow.last_insemination_date <= heat_window_end,
    )

    if farm_ids is not None:
        needling_q = needling_q.where(Cow.farm_id.in_(farm_ids))
        vaccinations_q = vaccinations_q.where(Cow.farm_id.in_(farm_ids))
        heat_q = heat_q.where(Cow.farm_id.in_(farm_ids))

    needling = await db.scalar(needling_q)
    vaccinations = await db.scalar(vaccinations_q)
    heat_checks = await db.scalar(heat_q)

    return {
        "needling_due": needling or 0,
        "heat_checks_due": heat_checks or 0,
        "vaccinations_due": vaccinations or 0,
    }
