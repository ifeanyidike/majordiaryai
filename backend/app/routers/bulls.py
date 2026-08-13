"""A farm's bull list — the "Bull Selection" the technician picks from.

Scoped to the farm (see the model's docstring for why), and gated like every
other farm-level write: admin or technician. A farm manager or vet can read the
list — knowing which semen is stocked is legitimate — but not change it.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_roles
from app.core.database import get_db
from app.models.models import Bull
from app.schemas.bulls import BullCreate, BullOut, BullUpdate
from app.services.access import check_farm_access

router = APIRouter()


@router.get("/farm/{farm_id}", response_model=List[BullOut])
async def list_bulls(
    farm_id: uuid.UUID,
    include_inactive: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulls stocked by this farm. Retired ones are hidden unless asked for —
    they stay in the table so historical inseminations keep resolving."""
    if not await check_farm_access(db, current_user, farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")

    stmt = select(Bull).where(Bull.farm_id == farm_id).order_by(Bull.name)
    if not include_inactive:
        stmt = stmt.where(Bull.active == True)  # noqa: E712
    return (await db.execute(stmt)).scalars().all()


@router.post("/farm/{farm_id}", response_model=BullOut, status_code=status.HTTP_201_CREATED)
async def create_bull(
    farm_id: uuid.UUID,
    body: BullCreate,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    if not await check_farm_access(db, current_user, farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")

    # Check first rather than relying on the unique constraint: a rollback
    # would discard anything else the caller's transaction had pending. The
    # constraint stays as the backstop for a genuine race.
    clash = await db.scalar(
        select(Bull).where(Bull.farm_id == farm_id, Bull.name == body.name)
    )
    if clash is not None:
        raise HTTPException(
            status_code=409,
            detail=f"'{body.name}' is already on this farm's bull list",
        )

    bull = Bull(farm_id=farm_id, **body.model_dump())
    db.add(bull)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"'{body.name}' is already on this farm's bull list",
        )
    await db.refresh(bull)
    return bull


@router.patch("/{bull_id}", response_model=BullOut)
async def update_bull(
    bull_id: uuid.UUID,
    body: BullUpdate,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    """Edit a bull, or retire it by setting active=false.

    There is no delete: inseminations reference bulls, and a straw used last
    season is part of the cow's breeding history.
    """
    bull = await db.get(Bull, bull_id)
    if not bull or not await check_farm_access(db, current_user, bull.farm_id):
        raise HTTPException(status_code=404, detail="Bull not found")

    new_name = body.model_dump(exclude_unset=True).get("name")
    if new_name and new_name != bull.name:
        clash = await db.scalar(
            select(Bull).where(Bull.farm_id == bull.farm_id, Bull.name == new_name)
        )
        if clash is not None:
            raise HTTPException(
                status_code=409, detail="Another bull on this farm has that name"
            )

    for field, value in body.model_dump(exclude_unset=True).items():
        if field in ("name", "active") and value is None:
            continue  # non-nullable
        setattr(bull, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Another bull on this farm has that name")
    await db.refresh(bull)
    return bull
