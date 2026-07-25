from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.models.models import Farm, Cow, CowStatus, User
from app.schemas.farms import FarmCreate, FarmUpdate, FarmOut
from app.services.access import check_farm_access, scope_to_farms
from typing import List
import uuid

router = APIRouter()

ACTIVE_STATUSES = (CowStatus.calf, CowStatus.heifer, CowStatus.fresh, CowStatus.open,
                   CowStatus.needling, CowStatus.inseminated, CowStatus.pregnant, CowStatus.dry)

# Non-nullable columns that a PATCH must never null out.
_NON_NULLABLE_FIELDS = {"name", "owner_name", "herd_size"}


def _with_counts(stmt):
    return (
        stmt
        .add_columns(
            func.count(Cow.id).filter(Cow.status.in_(ACTIVE_STATUSES)).label("cow_count"),
            func.count(Cow.id).filter(Cow.status == CowStatus.pregnant).label("pregnant_count"),
            func.count(Cow.id).filter(Cow.status == CowStatus.open).label("open_count"),
            # Resolve the assigned technician's name so clients show a name,
            # not a raw user id. max() avoids adding it to GROUP BY (one tech/farm).
            func.max(User.name).label("assigned_technician_name"),
        )
        .outerjoin(Cow, Cow.farm_id == Farm.id)
        .outerjoin(User, User.id == Farm.assigned_technician_id)
        .group_by(Farm.id)
        .order_by(Farm.name)
    )


def _row_to_dict(row):
    farm = row[0]
    d = {c.key: getattr(farm, c.key) for c in farm.__table__.columns}
    d["cow_count"] = row.cow_count
    d["pregnant_count"] = row.pregnant_count
    d["open_count"] = row.open_count
    d["assigned_technician_name"] = row.assigned_technician_name
    return d


@router.get("/", response_model=List[FarmOut])
async def list_farms(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = scope_to_farms(select(Farm), current_user, col=Farm.id)
    result = await db.execute(_with_counts(stmt))
    return [_row_to_dict(r) for r in result.all()]


@router.get("/{farm_id}", response_model=FarmOut)
async def get_farm(
    farm_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await check_farm_access(db, current_user, farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")
    stmt = _with_counts(select(Farm).where(Farm.id == farm_id))
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Farm not found")
    return _row_to_dict(row)


@router.post("/", response_model=FarmOut, status_code=status.HTTP_201_CREATED)
async def create_farm(
    body: FarmCreate,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    farm = Farm(**body.model_dump())
    db.add(farm)
    await db.commit()
    await db.refresh(farm)

    result = await db.execute(_with_counts(select(Farm).where(Farm.id == farm.id)))
    return _row_to_dict(result.first())


@router.patch("/{farm_id}", response_model=FarmOut)
async def update_farm(
    farm_id: uuid.UUID,
    body: FarmUpdate,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    farm = await db.get(Farm, farm_id)
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    # exclude_unset: explicit nulls clear nullable fields
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field in _NON_NULLABLE_FIELDS:
            continue
        setattr(farm, field, value)

    await db.commit()
    result = await db.execute(_with_counts(select(Farm).where(Farm.id == farm_id)))
    return _row_to_dict(result.first())


@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_farm(
    farm_id: uuid.UUID,
    force: bool = False,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    farm = await db.get(Farm, farm_id)
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    cow_count = await db.scalar(select(func.count(Cow.id)).where(Cow.farm_id == farm_id))
    user_count = await db.scalar(select(func.count(User.id)).where(User.farm_id == farm_id))
    if (cow_count or user_count) and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Farm has {cow_count or 0} cow(s) and {user_count or 0} user(s); "
                "pass ?force=true to delete anyway"
            ),
        )

    if force and user_count:
        await db.execute(
            update(User).where(User.farm_id == farm_id).values(farm_id=None)
        )
    try:
        # Core delete so the DB-level ON DELETE CASCADE handles cows/records.
        await db.execute(delete(Farm).where(Farm.id == farm_id))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Farm still has dependent records")
