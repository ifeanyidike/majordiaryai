from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.core.timeutils import ensure_aware, local_now, local_today, to_local_date
from app.models.models import Cow, CowStatus, Farm, VaccinationRecord
from app.schemas.vaccinations import VaccinationOut, VaccinationDueRow, VaccinationCompleteBody
from app.services.access import get_cow_scoped, scope_to_farms
from datetime import timedelta
from typing import List, Optional
import uuid

router = APIRouter()

TERMINAL_STATUSES = (CowStatus.cull, CowStatus.sold, CowStatus.dead)

# Post-calving vaccination window (days after calving)
DUE_WINDOW_START = 30
DUE_WINDOW_END = 50


@router.get("/due", response_model=List[VaccinationDueRow])
async def vaccinations_due(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cows 30-50 days post-calving with a pending vaccination record."""
    today = local_today()
    stmt = (
        select(VaccinationRecord, Cow, Farm)
        .join(Cow, Cow.id == VaccinationRecord.cow_id)
        .join(Farm, Farm.id == Cow.farm_id)
        .where(
            VaccinationRecord.completed == False,
            Cow.status.notin_(TERMINAL_STATUSES),
            Cow.last_calving_date.isnot(None),
            Cow.last_calving_date <= today - timedelta(days=DUE_WINDOW_START),
            Cow.last_calving_date >= today - timedelta(days=DUE_WINDOW_END),
        )
        .order_by(VaccinationRecord.scheduled_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Cow.farm_id)
    result = await db.execute(stmt)
    return [
        {
            "id": record.id,
            "cow_id": cow.id,
            "ear_tag": cow.ear_tag,
            "farm_id": cow.farm_id,
            "farm_name": farm.name,
            "scheduled_date": record.scheduled_date,
            "last_calving_date": cow.last_calving_date,
            "days_post_calving": (
                (today - cow.last_calving_date).days if cow.last_calving_date else None
            ),
        }
        for record, cow, farm in result.all()
    ]


@router.post("/cow/{cow_id}", response_model=VaccinationOut, status_code=201)
async def record_adhoc_vaccination(
    cow_id: uuid.UUID,
    body: VaccinationCompleteBody,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    """Record a vaccination that was never scheduled.

    An imported cow has no auto-scheduled calving-linked record, so her Post
    Calving row had nothing to complete — the report showed work with no way to
    clear it. This creates the record already completed; the Post Calving
    report clears on any completed vaccination in the current lactation.
    """
    cow = await get_cow_scoped(db, current_user, cow_id, for_update=True)
    if cow.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot record a vaccination for a {cow.status.value} cow",
        )

    administered_at = ensure_aware(body.administered_at) if body.administered_at else local_now()
    administered_on = to_local_date(administered_at)
    if administered_on > local_today():
        raise HTTPException(status_code=422, detail="administered_at cannot be in the future")

    record = VaccinationRecord(
        cow_id=cow.id,
        scheduled_date=administered_on,
        completed=True,
        completed_date=administered_on,
        administered_at=administered_at,
        vaccine_name=body.vaccine_name,
        lot_number=body.lot_number,
        technician_id=current_user["id"],
        notes=body.notes,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.get("/cow/{cow_id}", response_model=List[VaccinationOut])
async def list_cow_vaccinations(
    cow_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_cow_scoped(db, current_user, cow_id)
    result = await db.execute(
        select(VaccinationRecord)
        .where(VaccinationRecord.cow_id == cow_id)
        .order_by(VaccinationRecord.scheduled_date.desc())
    )
    return result.scalars().all()


@router.patch("/{record_id}/complete", response_model=VaccinationOut)
async def complete_vaccination(
    record_id: uuid.UUID,
    body: VaccinationCompleteBody,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VaccinationRecord).where(VaccinationRecord.id == record_id).with_for_update()
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Vaccination record not found")

    # Object-level authorization: 404 when the cow is out of the caller's scope.
    await get_cow_scoped(db, current_user, record.cow_id)

    if record.completed:
        raise HTTPException(status_code=409, detail="Vaccination is already completed")

    administered_at = ensure_aware(body.administered_at) if body.administered_at else local_now()
    if to_local_date(administered_at) > local_today():
        raise HTTPException(status_code=422, detail="administered_at cannot be in the future")

    record.completed = True
    record.administered_at = administered_at
    record.completed_date = to_local_date(administered_at)
    record.vaccine_name = body.vaccine_name
    record.lot_number = body.lot_number
    record.technician_id = current_user["id"]
    if body.notes:
        record.notes = body.notes

    await db.commit()
    await db.refresh(record)
    return record
