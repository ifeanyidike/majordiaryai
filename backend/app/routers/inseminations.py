from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.core.timeutils import ensure_aware, local_today, to_local_date
from app.models.models import Bull, Insemination, NeedlingEnrollment
from app.services.protocols import TIMED_AI_PROTOCOLS
from app.services.worklists import pending_final_record_stmt
from app.schemas.inseminations import InseminationCreate, InseminationOut
from app.services import status_engine
from app.services.access import get_cow_scoped
from typing import List
import uuid

router = APIRouter()


@router.get("/cow/{cow_id}", response_model=List[InseminationOut])
async def list_cow_inseminations(
    cow_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_cow_scoped(db, current_user, cow_id)
    result = await db.execute(
        select(Insemination)
        .where(Insemination.cow_id == cow_id)
        .order_by(Insemination.date.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=InseminationOut, status_code=status.HTTP_201_CREATED)
async def record_insemination(
    body: InseminationCreate,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    cow = await get_cow_scoped(db, current_user, body.cow_id, for_update=True)

    if cow.status not in status_engine.INSEMINABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot inseminate a cow with status '{cow.status.value}'",
        )

    # A bull from another farm's list would silently corrupt per-bull analytics.
    if body.bull_id is not None:
        bull = await db.get(Bull, body.bull_id)
        if bull is None or bull.farm_id != cow.farm_id:
            raise HTTPException(
                status_code=422, detail="bull_id is not on this cow's farm bull list"
            )

    insemination_date = to_local_date(body.date)
    if insemination_date > local_today():
        raise HTTPException(status_code=422, detail="Insemination date cannot be in the future")

    # attempt_number is always computed server-side
    prior_attempts = await db.scalar(
        select(func.count(Insemination.id)).where(Insemination.cow_id == cow.id)
    )

    insemination = Insemination(
        cow_id=cow.id,
        date=insemination_date,
        inseminated_at=ensure_aware(body.date),
        bull_name=body.bull_name,
        bull_id=body.bull_id,
        dose_id=body.dose_id,
        insemination_code=body.insemination_code,
        semen_type=body.semen_type,
        notes=body.notes,
        attempt_number=(prior_attempts or 0) + 1,
        technician_id=current_user["id"],
    )
    db.add(insemination)
    await db.flush()  # get the id before status update

    # Same-day overlap rule: on a protocol's final day the injection and the AI
    # are one action. Complete the pending final needling record in THIS
    # transaction so the treatment is recorded no matter which client (app,
    # script, integration) records the insemination — and so it can never be
    # orphaned by on_insemination() closing the enrollment.
    # Lock order is cow → record (matching complete_record) to avoid an ABBA
    # deadlock when a technician fires both endpoints back-to-back.
    final_record = await db.scalar(pending_final_record_stmt(cow.id, local_today()))
    if final_record is not None:
        enrollment = await db.get(NeedlingEnrollment, final_record.enrollment_id)
        # Timed-AI protocols pair a real injection with the AI; Prostaglandin
        # Heat's last day is observation with conditional AI, so don't claim an
        # injection was given that the protocol never scheduled.
        note = (
            "Final injection given with insemination"
            if enrollment is not None and enrollment.protocol in TIMED_AI_PROTOCOLS
            else "Insemination recorded on this protocol day"
        )
        final_record.completed = True
        final_record.completed_date = insemination_date
        final_record.technician_id = current_user["id"]
        final_record.notes = (final_record.notes or "") + (
            "\n" if final_record.notes else ""
        ) + note

    await status_engine.on_insemination(cow, insemination, db)
    await db.commit()
    await db.refresh(insemination)
    return insemination
