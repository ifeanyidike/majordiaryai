from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, HealthStatus, CullRecord, Insemination, HeatCheck, PregnancyCheck,
    CalvingRecord, NeedlingRecord, VaccinationRecord,
)
from app.schemas.cows import (
    CowCreate, CowUpdate, CowOut, CowHealthBody, CullBody, ExitBody, CowHistory,
)
from app.services import status_engine
from app.services.access import scope_to_farms, check_farm_access, get_cow_scoped
from datetime import timedelta
from typing import List, Optional
import uuid

router = APIRouter()

# Response sizes are bounded so one caller cannot pull an entire multi-farm
# herd in a single request. Callers page with limit/offset and read the true
# size from the X-Total-Count header.
DEFAULT_PAGE_SIZE = 200
MAX_PAGE_SIZE = 1000

# Non-nullable columns that a PATCH must never null out.
_NON_NULLABLE_FIELDS = {"lactation_number", "status"}


def _cow_dict(cow: Cow, farm_name=None) -> dict:
    return {**{c.key: getattr(cow, c.key) for c in cow.__table__.columns},
            "farm_name": farm_name,
            # Derived from status + calving (see status_engine.is_milking).
            "is_milking": status_engine.is_milking(cow)}


@router.get("/", response_model=List[CowOut])
async def list_cows(
    response: Response,
    farm_id: Optional[uuid.UUID] = None,
    status: Optional[CowStatus] = None,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cows in the caller's scope, newest page first.

    Bounded on purpose: an admin over 50 farms of 500 cows would otherwise get
    25,000 rows in one response. `X-Total-Count` carries the full size so a
    caller can page without a second round trip, and so herd counts stay right
    even when only a page is loaded.
    """
    stmt = select(Cow).options(selectinload(Cow.farm))
    stmt = scope_to_farms(stmt, current_user, farm_id)

    if status:
        stmt = stmt.where(Cow.status == status)

    total = await db.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    response.headers["X-Total-Count"] = str(total or 0)

    # ear_tag is not unique across farms, so add id as a tiebreaker — without
    # it a row can repeat or be skipped between pages.
    stmt = stmt.order_by(Cow.ear_tag, Cow.id).limit(limit).offset(offset)
    result = await db.execute(stmt)
    cows = result.scalars().all()
    return [_cow_dict(cow, cow.farm.name if cow.farm else None) for cow in cows]


@router.get("/{cow_id}", response_model=CowOut)
async def get_cow(
    cow_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cow = await get_cow_scoped(db, current_user, cow_id)
    result = await db.execute(
        select(Cow).where(Cow.id == cow_id).options(selectinload(Cow.farm))
    )
    cow = result.scalar_one()
    return _cow_dict(cow, cow.farm.name if cow.farm else None)


@router.get("/{cow_id}/history", response_model=CowHistory)
async def cow_history(
    cow_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full event history for a cow, each list sorted newest-first."""
    await get_cow_scoped(db, current_user, cow_id)

    inseminations = (await db.execute(
        select(Insemination).where(Insemination.cow_id == cow_id)
        .order_by(Insemination.date.desc(), Insemination.created_at.desc())
    )).scalars().all()
    heat_checks = (await db.execute(
        select(HeatCheck).where(HeatCheck.cow_id == cow_id)
        .order_by(HeatCheck.check_date.desc(), HeatCheck.created_at.desc())
    )).scalars().all()
    pregnancy_checks = (await db.execute(
        select(PregnancyCheck).where(PregnancyCheck.cow_id == cow_id)
        .order_by(PregnancyCheck.check_date.desc(), PregnancyCheck.created_at.desc())
    )).scalars().all()
    calvings = (await db.execute(
        select(CalvingRecord).where(CalvingRecord.cow_id == cow_id)
        .order_by(CalvingRecord.calving_date.desc(), CalvingRecord.created_at.desc())
    )).scalars().all()
    needling_records = (await db.execute(
        select(NeedlingRecord).where(NeedlingRecord.cow_id == cow_id)
        .order_by(NeedlingRecord.scheduled_date.desc(), NeedlingRecord.created_at.desc())
    )).scalars().all()
    vaccinations = (await db.execute(
        select(VaccinationRecord).where(VaccinationRecord.cow_id == cow_id)
        .order_by(VaccinationRecord.scheduled_date.desc(), VaccinationRecord.created_at.desc())
    )).scalars().all()

    return {
        "inseminations": inseminations,
        "heat_checks": heat_checks,
        "pregnancy_checks": pregnancy_checks,
        "calvings": calvings,
        "needling_records": needling_records,
        "vaccinations": vaccinations,
    }


@router.post("/", response_model=CowOut, status_code=status.HTTP_201_CREATED)
async def create_cow(
    body: CowCreate,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    if not await check_farm_access(db, current_user, body.farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")

    cow = Cow(**body.model_dump())
    db.add(cow)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Ear tag '{body.ear_tag}' already exists on this farm",
        )
    await db.refresh(cow)

    result = await db.execute(
        select(Cow).where(Cow.id == cow.id).options(selectinload(Cow.farm))
    )
    cow = result.scalar_one()
    return _cow_dict(cow, cow.farm.name if cow.farm else None)


@router.patch("/{cow_id}", response_model=CowOut)
async def update_cow(
    cow_id: uuid.UUID,
    body: CowUpdate,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    cow = await get_cow_scoped(db, current_user, cow_id, for_update=True)

    data = body.model_dump(exclude_unset=True)
    new_status = data.get("status")
    if new_status is not None and new_status != cow.status:
        # A legal transition is not the same as a complete one. Setting
        # inseminated -> pregnant here left due_date/dry_date NULL so she never
        # dried off; -> needling with no enrollment stranded her on no report.
        # Those side effects live in the event endpoints (record a pregnancy
        # check, enroll in a protocol), which is where a status change belongs.
        raise HTTPException(
            status_code=409,
            detail=(
                f"Status cannot be changed here ({cow.status.value} -> "
                f"{new_status.value}). Record the event instead — a pregnancy "
                "check, insemination, calving, enrolment or cull — so the "
                "dates and records that go with it are written too."
            ),
        )
    data.pop("status", None)

    for field, value in data.items():
        if value is None and field in _NON_NULLABLE_FIELDS:
            continue  # never null out non-nullable columns
        setattr(cow, field, value)

    await db.commit()
    result = await db.execute(
        select(Cow).where(Cow.id == cow_id).options(selectinload(Cow.farm))
    )
    cow = result.scalar_one()
    return _cow_dict(cow, cow.farm.name if cow.farm else None)


@router.post("/{cow_id}/health", response_model=CowOut)
async def set_cow_health(
    cow_id: uuid.UUID,
    body: CowHealthBody,
    current_user: dict = Depends(require_roles("admin", "technician", "vet")),
    db: AsyncSession = Depends(get_db),
):
    """Mark a cow healthy or sick. A sick cow gets a recheck due 7 days out
    (spec: "if sick — check every 7 days if healthy"); marking her healthy
    clears the recheck."""
    cow = await get_cow_scoped(db, current_user, cow_id, for_update=True)
    if cow.status in (CowStatus.sold, CowStatus.dead):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot set health on a {cow.status.value} cow",
        )

    cow.health_status = body.health_status
    if body.health_status == HealthStatus.sick:
        cow.recheck_due_date = local_today() + timedelta(days=7)
    else:
        cow.recheck_due_date = None

    if body.notes:
        cow.notes = f"{cow.notes}\n{body.notes}" if cow.notes else body.notes

    await db.commit()
    result = await db.execute(
        select(Cow).where(Cow.id == cow_id).options(selectinload(Cow.farm))
    )
    cow = result.scalar_one()
    return _cow_dict(cow, cow.farm.name if cow.farm else None)


@router.post("/{cow_id}/cull", status_code=status.HTTP_200_OK)
async def cull_cow(
    cow_id: uuid.UUID,
    body: CullBody = None,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    cow = await get_cow_scoped(db, current_user, cow_id, for_update=True)
    # ensure_transition treats same-status as a no-op, so culling an already
    # culled cow slipped through and inserted a SECOND CullRecord.
    if cow.status == CowStatus.cull:
        raise HTTPException(status_code=409, detail="Cow is already culled")
    status_engine.ensure_transition(cow, CowStatus.cull)

    body = body or CullBody()
    cull_date = body.cull_date or local_today()
    if cull_date > local_today():
        raise HTTPException(status_code=422, detail="cull_date cannot be in the future")

    db.add(CullRecord(
        cow_id=cow.id,
        cull_date=cull_date,
        reason=body.reason,
        technician_id=current_user["id"],
        notes=body.notes,
    ))
    await status_engine.on_cull(cow, db)
    await db.commit()
    return {"id": str(cow_id), "status": "cull"}


@router.post("/{cow_id}/mark-sold", status_code=status.HTTP_200_OK)
async def mark_sold(
    cow_id: uuid.UUID,
    body: ExitBody = None,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    """Mark a culled cow as sold (only legal from cull status)."""
    cow = await get_cow_scoped(db, current_user, cow_id, for_update=True)
    # Same-status is a no-op in ensure_transition, so a second call silently
    # overwrote the recorded exit date and reason.
    if cow.status == CowStatus.sold:
        raise HTTPException(status_code=409, detail="Cow is already marked sold")
    status_engine.ensure_transition(cow, CowStatus.sold)

    body = body or ExitBody()
    exit_date = body.date or local_today()
    if exit_date > local_today():
        raise HTTPException(status_code=422, detail="date cannot be in the future")

    cow.status = CowStatus.sold
    cow.current_program = None
    cow.exit_date = exit_date
    cow.exit_reason = body.reason
    await db.commit()
    return {"id": str(cow_id), "status": "sold"}


@router.post("/{cow_id}/mark-dead", status_code=status.HTTP_200_OK)
async def mark_dead(
    cow_id: uuid.UUID,
    body: ExitBody = None,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    """Mark a cow as dead (legal from any non-terminal status)."""
    cow = await get_cow_scoped(db, current_user, cow_id, for_update=True)
    if cow.status == CowStatus.dead:
        raise HTTPException(status_code=409, detail="Cow is already marked dead")
    status_engine.ensure_transition(cow, CowStatus.dead)

    body = body or ExitBody()
    exit_date = body.date or local_today()
    if exit_date > local_today():
        raise HTTPException(status_code=422, detail="date cannot be in the future")

    await status_engine.cancel_active_enrollments(cow, db, new_status=status_engine.EnrollmentStatus.cancelled)
    cow.status = CowStatus.dead
    cow.current_program = None
    cow.exit_date = exit_date
    cow.exit_reason = body.reason
    await db.commit()
    return {"id": str(cow_id), "status": "dead"}


@router.post("/{cow_id}/dry-off-confirm", response_model=CowOut)
async def confirm_dry_off(
    cow_id: uuid.UUID,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a dried-off cow was moved to the dry pen.

    Without this the Dry Report had no completable action: the cow sat on the
    technician's daily list for the whole window with no way to clear her, so
    the count never reflected work actually done.
    """
    cow = await get_cow_scoped(db, current_user, cow_id, for_update=True)

    if cow.status == CowStatus.pregnant and cow.dry_date and cow.dry_date <= local_today():
        # She hit day 223 but the sweep hasn't run for her farm yet — confirming
        # the pen change implies the dry-off happened.
        status_engine.ensure_transition(cow, CowStatus.dry)
        cow.status = CowStatus.dry
    if cow.status != CowStatus.dry:
        raise HTTPException(
            status_code=409,
            detail=f"Only a dry cow can be confirmed dried off (status is '{cow.status.value}')",
        )

    cow.dry_off_confirmed_date = local_today()
    # The "change pen" email already went out when the day-223 sweep flipped her
    # to Dry (status_engine.run_lifecycle_transitions). Confirming the move is
    # the technician closing the loop — emailing the farmer "please move her"
    # at that moment would be a second email asking for the action it confirms.
    await db.commit()

    result = await db.execute(
        select(Cow).where(Cow.id == cow_id).options(selectinload(Cow.farm))
    )
    cow = result.scalar_one()
    return _cow_dict(cow, cow.farm.name if cow.farm else None)
