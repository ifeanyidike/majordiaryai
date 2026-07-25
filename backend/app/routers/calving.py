from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.core.timeutils import local_today
from app.models.models import CalvingRecord, CalfSex, Cow, CowStatus, VaccinationRecord
from app.schemas.calving import CalvingCreate, CalvingOut
from app.services import status_engine
from app.services.access import get_cow_scoped
from datetime import timedelta
from typing import List
import uuid

router = APIRouter()

# Spec: ONE post-calving vaccination task, scheduled at day 30 (due window 30-50).
VACCINATION_DAY = 30


async def _generate_calf_ear_tag(db: AsyncSession, farm_id: uuid.UUID) -> str:
    """Farm-scoped sequential ear tag for a female calf (e.g. C-0042), unique per farm."""
    count = await db.scalar(select(func.count(Cow.id)).where(Cow.farm_id == farm_id)) or 0
    seq = count + 1
    while True:
        candidate = "C-{:04d}".format(seq)
        exists = await db.scalar(
            select(func.count(Cow.id)).where(Cow.farm_id == farm_id, Cow.ear_tag == candidate)
        )
        if not exists:
            return candidate
        seq += 1


@router.get("/cow/{cow_id}", response_model=List[CalvingOut])
async def list_calvings(
    cow_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_cow_scoped(db, current_user, cow_id)
    result = await db.execute(
        select(CalvingRecord)
        .where(CalvingRecord.cow_id == cow_id)
        .order_by(CalvingRecord.calving_date.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=CalvingOut, status_code=status.HTTP_201_CREATED)
async def record_calving(
    body: CalvingCreate,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    cow = await get_cow_scoped(db, current_user, body.cow_id, for_update=True)

    if cow.status not in (CowStatus.pregnant, CowStatus.dry):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot record calving for a cow with status '{cow.status.value}'",
        )
    if body.calving_date > local_today():
        raise HTTPException(status_code=422, detail="calving_date cannot be in the future")
    if body.live_birth and body.calf_sex is None:
        raise HTTPException(status_code=422, detail="calf_sex is required for a live birth")

    # Female live calf → herd record (ear tag auto-generated if not supplied).
    # Male calf → no herd Cow record; sex/sale info stay on the calving record.
    calf_id = None
    calf_ear_tag = body.calf_ear_tag
    if body.live_birth and body.calf_sex == CalfSex.female:
        if not calf_ear_tag:
            calf_ear_tag = await _generate_calf_ear_tag(db, cow.farm_id)
        calf = Cow(
            ear_tag=calf_ear_tag,
            farm_id=cow.farm_id,
            sex=CalfSex.female,
            date_of_birth=body.calving_date,
            status=CowStatus.calf,
        )
        db.add(calf)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Ear tag '{calf_ear_tag}' already exists on this farm",
            )
        calf_id = calf.id

    calving = CalvingRecord(
        cow_id=cow.id,
        calving_date=body.calving_date,
        live_birth=body.live_birth,
        still_birth=body.still_birth,
        calf_sex=body.calf_sex,
        calf_ear_tag=calf_ear_tag,
        calf_sale_info=body.calf_sale_info,
        notes=body.notes,
        calf_id=calf_id,
        technician_id=current_user["id"],
    )
    db.add(calving)
    await db.flush()

    # Auto-schedule the single post-calving vaccination at day 30.
    db.add(VaccinationRecord(
        cow_id=cow.id,
        calving_record_id=calving.id,
        scheduled_date=body.calving_date + timedelta(days=VACCINATION_DAY),
    ))

    await status_engine.on_calving(cow, body.calving_date, db)
    await db.commit()
    await db.refresh(calving)
    return calving
