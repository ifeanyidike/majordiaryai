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
from app.schemas.needling import (
    BleedingEventBody, NeedlingEnrollmentCreate, NeedlingEnrollmentOut, CompleteRecordBody,
)
from app.services import status_engine
from app.services.access import get_cow_scoped, scope_to_farms
from app.services.protocols import get_scheduled_records, UnknownProtocolError
from app.services.worklists import latest_open_record_stmt, needling_due_stmt
from typing import List, Optional
import uuid

router = APIRouter()


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
    # Lock order must be cow → record → enrollment everywhere (see
    # record_insemination, which a technician often fires straight after this
    # one); acquiring them in a different order deadlocks under concurrency.
    # Read the record unlocked first, purely to learn which cow to lock.
    owner = await db.scalar(
        select(NeedlingRecord.cow_id).where(NeedlingRecord.id == record_id)
    )
    if owner is None:
        raise HTTPException(status_code=404, detail="Record not found")

    # Object-level authorization (404 when out of scope) + row lock on the cow.
    cow = await get_cow_scoped(db, current_user, owner, for_update=True)

    record = await db.scalar(
        select(NeedlingRecord)
        .where(NeedlingRecord.id == record_id)
        .with_for_update(of=NeedlingRecord)
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    enrollment = await db.scalar(
        select(NeedlingEnrollment)
        .where(NeedlingEnrollment.id == record.enrollment_id)
        .with_for_update(of=NeedlingEnrollment)
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found for this record")

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
        # cow into the Ovsynch needling program (spec rule). Same service the
        # standalone bleeding endpoint uses, so both paths behave identically.
        await status_engine.on_bleeding_before_insemination(cow, db)
    elif record.is_final:
        await status_engine.on_final_record_completed(cow, enrollment, db)

    await db.commit()
    return {"id": str(record_id), "completed": True}


@router.post("/cow/{cow_id}/bleeding", response_model=dict)
async def record_bleeding_event(
    cow_id: uuid.UUID,
    body: BleedingEventBody,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    """Record a bleeding event for a cow.

    Spec: "bleeding events can be recorded on any day". Completing a scheduled
    record is NOT a prerequisite — a cow whose final injection is already given
    (enrollment `completed_pending_ai`) has no completable record left, so
    routing bleeding through PATCH /records/{id}/complete made it unrecordable
    exactly when she is closest to insemination.

    The cow goes Open and is transferred into the Ovsynch program. The bleeding
    is also flagged on her most recent open needling record when she has one, so
    it shows up in her treatment history rather than only in a status change.
    """
    cow = await get_cow_scoped(db, current_user, cow_id, for_update=True)

    if cow.status == CowStatus.inseminated:
        # Blood on the tail after insemination means she returned to heat; that
        # is a heat check outcome, which has its own endpoint and audit trail
        # (and accepts a bleeding observation on any day post-AI).
        raise HTTPException(
            status_code=409,
            detail="Cow is inseminated — record this as a heat check (blood on tail = in heat)",
        )
    # Pre-insemination bleeding routes the cow into Ovsynch, which only makes
    # sense for breeding-eligible animals. A calf or a fresh cow before day 70
    # must not be force-enrolled in a synchronization protocol by this endpoint.
    if cow.status not in (CowStatus.open, CowStatus.needling, CowStatus.heifer):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot record a pre-insemination bleeding event for a {cow.status.value} cow",
        )

    # Best-effort audit on the enrollment she's leaving (may be None — bleeding
    # is recordable whether or not she is mid-protocol).
    record = await db.scalar(latest_open_record_stmt(cow.id))
    if record is not None:
        record.bleeding_event = True
        record.technician_id = current_user["id"]
        note = body.notes or "Bleeding event recorded"
        record.notes = f"{record.notes}\n{note}" if record.notes else note

    await status_engine.on_bleeding_before_insemination(cow, db)
    await db.commit()
    return {"cow_id": str(cow_id), "bleeding_event": True, "status": cow.status.value}


@router.get("/today", response_model=List[dict])
async def todays_needling(
    farm_id: Optional[uuid.UUID] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Needling records due today, including missed/overdue ones (scheduled on
    or before today and still incomplete). Scoped to the caller's farms.

    Same-day overlap rule: on a protocol's FINAL day the cow needs both the last
    injection and insemination. The whole COW is excluded here (not just the
    final record — an earlier missed shot must not resurface her either) and she
    is shown only on the Timed Breeding report, where the final injection is
    folded into one combined task ("Give final GnRH + Inseminate").
    """
    # Same sweep every other worklist endpoint runs — otherwise this list is
    # built from statuses that may be days stale.
    await status_engine.run_transitions_for_user(db, current_user)
    today = local_today()

    # Predicates live in app/services/worklists.py so this query and the Timed
    # Breeding query can never drift apart (that drift is what previously made
    # cows disappear from both reports).
    stmt = scope_to_farms(needling_due_stmt(today), current_user, farm_id, col=Cow.farm_id)
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
