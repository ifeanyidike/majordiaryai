from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.core.timeutils import local_today
from app.models.models import HeatCheck, PregnancyCheck, CowStatus, Insemination, PregnancyResult
from app.schemas.checks import HeatCheckCreate, HeatCheckOut, PregnancyCheckCreate, PregnancyCheckOut
from app.services import status_engine
from app.services.access import get_cow_scoped
from typing import List
import uuid

router = APIRouter()

HEAT_WINDOW_START = 20  # days post-insemination
HEAT_WINDOW_END = 25


# ── Heat checks ──────────────────────────────────────────────

@router.get("/heat/cow/{cow_id}", response_model=List[HeatCheckOut])
async def list_heat_checks(
    cow_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_cow_scoped(db, current_user, cow_id)
    result = await db.execute(
        select(HeatCheck)
        .where(HeatCheck.cow_id == cow_id)
        .order_by(HeatCheck.check_date.desc())
    )
    return result.scalars().all()


@router.post("/heat", response_model=HeatCheckOut, status_code=status.HTTP_201_CREATED)
async def record_heat_check(
    body: HeatCheckCreate,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    cow = await get_cow_scoped(db, current_user, body.cow_id, for_update=True)

    if body.check_date > local_today():
        raise HTTPException(status_code=422, detail="check_date cannot be in the future")

    insemination = await db.get(Insemination, body.insemination_id)
    if not insemination or insemination.cow_id != cow.id:
        raise HTTPException(status_code=422, detail="insemination_id does not belong to this cow")

    if not cow.last_insemination_date:
        raise HTTPException(status_code=409, detail="Cow has no recorded insemination")

    # Heat window is 20-25 days post-insemination — computed server-side.
    days_since = (body.check_date - cow.last_insemination_date).days
    if days_since < HEAT_WINDOW_START or days_since > HEAT_WINDOW_END:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Heat checks are only accepted {HEAT_WINDOW_START}-{HEAT_WINDOW_END} days "
                f"post-insemination (this check is at day {days_since})"
            ),
        )

    check = HeatCheck(
        cow_id=cow.id,
        insemination_id=body.insemination_id,
        check_date=body.check_date,
        days_since_insemination=days_since,
        heat_detected=body.heat_detected,
        bleeding_event=body.bleeding_event,
        notes=body.notes,
        technician_id=current_user["id"],
    )
    db.add(check)

    # Blood on the tail during a heat check means the cow was in heat.
    if body.heat_detected or body.bleeding_event:
        await status_engine.on_heat_detected(cow, db)

    await db.commit()
    await db.refresh(check)
    return check


# ── Pregnancy checks ─────────────────────────────────────────

@router.get("/pregnancy/cow/{cow_id}", response_model=List[PregnancyCheckOut])
async def list_pregnancy_checks(
    cow_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_cow_scoped(db, current_user, cow_id)
    result = await db.execute(
        select(PregnancyCheck)
        .where(PregnancyCheck.cow_id == cow_id)
        .order_by(PregnancyCheck.check_date.desc())
    )
    return result.scalars().all()


@router.post("/pregnancy", response_model=PregnancyCheckOut, status_code=status.HTTP_201_CREATED)
async def record_pregnancy_check(
    body: PregnancyCheckCreate,
    current_user: dict = Depends(require_roles("admin", "technician", "vet")),
    db: AsyncSession = Depends(get_db),
):
    cow = await get_cow_scoped(db, current_user, body.cow_id, for_update=True)

    if body.check_date > local_today():
        raise HTTPException(status_code=422, detail="check_date cannot be in the future")

    if cow.status != CowStatus.inseminated:
        raise HTTPException(
            status_code=409,
            detail=f"Pregnancy checks require an inseminated cow (status is '{cow.status.value}')",
        )

    insemination = await db.get(Insemination, body.insemination_id)
    if not insemination or insemination.cow_id != cow.id:
        raise HTTPException(status_code=422, detail="insemination_id does not belong to this cow")

    if not cow.last_insemination_date or \
            (body.check_date - cow.last_insemination_date).days < 30:
        raise HTTPException(
            status_code=409,
            detail="Pregnancy checks are only accepted 30+ days post-insemination",
        )

    check = PregnancyCheck(
        cow_id=cow.id,
        insemination_id=body.insemination_id,
        check_date=body.check_date,
        result=body.result,
        has_infection=body.has_infection,
        has_cysts=body.has_cysts,
        notes=body.notes,
        # vet_id only when the caller is actually a vet; acting user always recorded.
        vet_id=current_user["id"] if current_user["role"] == "vet" else None,
        performed_by_id=current_user["id"],
    )
    db.add(check)

    if body.has_cysts:
        # Cysts → open / back to needling selection regardless of result.
        await status_engine.on_pregnancy_negative(cow, db)
    elif body.result == PregnancyResult.pregnant:
        # Infection + pregnant → proceed as pregnant normally.
        await status_engine.on_pregnancy_confirmed(cow, insemination.date, db)
    elif body.result == PregnancyResult.not_pregnant:
        # Covers infection + not pregnant as well.
        await status_engine.on_pregnancy_negative(cow, db)

    await db.commit()
    await db.refresh(check)
    return check
