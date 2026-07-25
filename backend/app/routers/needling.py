from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, NeedlingEnrollment, NeedlingRecord, EnrollmentStatus
)
from app.schemas.needling import NeedlingEnrollmentCreate, NeedlingEnrollmentOut, CompleteRecordBody
from app.services import status_engine
from app.services.access import get_cow_scoped, scope_to_farms
from app.services.protocols import get_scheduled_records, UnknownProtocolError
from typing import List, Optional
import uuid

router = APIRouter()

TERMINAL_STATUSES = (CowStatus.cull, CowStatus.sold, CowStatus.dead)


@router.get("/cow/{cow_id}", response_model=List[NeedlingEnrollmentOut])
async def list_enrollments(
    cow_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_cow_scoped(db, current_user, cow_id)
    result = await db.execute(
        select(NeedlingEnrollment)
        .where(NeedlingEnrollment.cow_id == cow_id)
        .options(selectinload(NeedlingEnrollment.records))
        .order_by(NeedlingEnrollment.start_date.desc())
    )
    return result.scalars().all()


@router.post("/enroll", response_model=NeedlingEnrollmentOut, status_code=status.HTTP_201_CREATED)
async def enroll_cow(
    body: NeedlingEnrollmentCreate,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    cow = await get_cow_scoped(db, current_user, body.cow_id, for_update=True)
    status_engine.ensure_transition(cow, CowStatus.needling)

    try:
        scheduled = get_scheduled_records(body.protocol.value, body.start_date)
    except UnknownProtocolError:
        raise HTTPException(status_code=422, detail=f"Unknown protocol: {body.protocol}")

    # A cow can only be in one protocol at a time — replace any active enrollment.
    await status_engine.cancel_active_enrollments(cow, db, EnrollmentStatus.cancelled)

    enrollment = NeedlingEnrollment(
        cow_id=body.cow_id,
        protocol=body.protocol,
        start_date=body.start_date,
    )
    db.add(enrollment)
    await db.flush()

    # Pre-generate all scheduled records for this protocol
    for s in scheduled:
        db.add(NeedlingRecord(
            enrollment_id=enrollment.id,
            cow_id=body.cow_id,
            protocol_day=s["protocol_day"],
            scheduled_date=s["scheduled_date"],
            treatment=s["treatment"],
            is_final=s["is_final"],
        ))

    cow.status = CowStatus.needling
    cow.current_program = body.protocol.value

    await db.commit()
    result = await db.execute(
        select(NeedlingEnrollment)
        .where(NeedlingEnrollment.id == enrollment.id)
        .options(selectinload(NeedlingEnrollment.records))
    )
    return result.scalar_one()


@router.patch("/records/{record_id}/complete", response_model=dict)
async def complete_record(
    record_id: uuid.UUID,
    body: CompleteRecordBody,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NeedlingRecord).where(NeedlingRecord.id == record_id).with_for_update()
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Object-level authorization (404 when out of scope) + row lock on the cow.
    cow = await get_cow_scoped(db, current_user, record.cow_id, for_update=True)

    result = await db.execute(
        select(NeedlingEnrollment)
        .where(NeedlingEnrollment.id == record.enrollment_id)
        .with_for_update()
    )
    enrollment = result.scalar_one()

    if record.completed:
        raise HTTPException(status_code=409, detail="Record is already completed")
    if enrollment.status == EnrollmentStatus.cancelled:
        raise HTTPException(status_code=409, detail="Enrollment has been cancelled")
    if enrollment.status == EnrollmentStatus.completed:
        raise HTTPException(status_code=409, detail="Enrollment is already completed")

    record.completed = True
    record.completed_date = local_today()
    record.bleeding_event = body.bleeding_event
    record.technician_id = current_user["id"]
    if body.notes:
        record.notes = body.notes

    # Advance the enrollment to this protocol day.
    enrollment.current_day = max(enrollment.current_day or 1, record.protocol_day)

    if body.bleeding_event:
        # Bleeding before insemination: cancel this enrollment and transfer the
        # cow into the Ovsynch needling program (spec rule).
        await status_engine.on_bleeding_before_insemination(cow, db)
    elif record.is_final:
        # Final (AI) day completed — cow moves to the Timed Breeding report
        # until the insemination is recorded.
        enrollment.status = EnrollmentStatus.completed_pending_ai

    await db.commit()
    return {"id": str(record_id), "completed": True}


@router.get("/today", response_model=List[dict])
async def todays_needling(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Needling records due today, including missed/overdue ones (scheduled on
    or before today and still incomplete). Scoped to the caller's farms."""
    today = local_today()
    stmt = (
        select(NeedlingRecord, Cow)
        .join(Cow, Cow.id == NeedlingRecord.cow_id)
        .join(NeedlingEnrollment, NeedlingEnrollment.id == NeedlingRecord.enrollment_id)
        .where(
            NeedlingRecord.scheduled_date <= today,
            NeedlingRecord.completed == False,
            NeedlingEnrollment.status == EnrollmentStatus.active,
            Cow.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(NeedlingRecord.scheduled_date)
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Cow.farm_id)
    result = await db.execute(stmt)
    return [
        {
            "id": str(r.id),
            "cow_id": str(r.cow_id),
            "ear_tag": cow.ear_tag,
            "farm_id": str(cow.farm_id),
            "treatment": r.treatment,
            "protocol_day": r.protocol_day,
            "scheduled_date": r.scheduled_date.isoformat(),
            "is_final": r.is_final,
            "overdue": r.scheduled_date < today,
            "days_overdue": (today - r.scheduled_date).days,
            "enrollment_id": str(r.enrollment_id),
        }
        for r, cow in result.all()
    ]
