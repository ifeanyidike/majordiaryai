from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.core.timeutils import local_today
from app.models.models import Farm, FarmVisitAssignment, Cow, CowStatus, User, UserRole
from app.schemas.farms import (
    FarmCreate, FarmUpdate, FarmOut, VisitAssignmentBody, VisitAssignmentOut,
)
from app.services.access import check_farm_access, scope_to_farms
from datetime import date
from typing import List, Optional
import uuid

router = APIRouter()

# Matches /cows: responses are bounded, with the true size in X-Total-Count.
DEFAULT_PAGE_SIZE = 200
MAX_PAGE_SIZE = 1000

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
    response: Response,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Farms in the caller's scope. Bounded like /cows; X-Total-Count carries
    the full size so the caller knows whether more pages exist."""
    stmt = scope_to_farms(select(Farm), current_user, col=Farm.id)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    response.headers["X-Total-Count"] = str(total or 0)

    # name is not unique, so id breaks ties and keeps paging stable.
    paged = _with_counts(stmt).order_by(Farm.name, Farm.id).limit(limit).offset(offset)
    result = await db.execute(paged)
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


# ── Visit schedule ───────────────────────────────────────────────────

@router.get("/{farm_id}/visit-assignments", response_model=List[VisitAssignmentOut])
async def list_visit_assignments(
    farm_id: uuid.UUID,
    from_date: Optional[date] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Day-level overrides of who visits this farm (upcoming by default)."""
    if not await check_farm_access(db, current_user, farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")

    stmt = (
        select(FarmVisitAssignment, User.name)
        .outerjoin(User, User.id == FarmVisitAssignment.assigned_technician_id)
        .where(FarmVisitAssignment.farm_id == farm_id)
        .order_by(FarmVisitAssignment.visit_date)
    )
    if from_date is not None:
        stmt = stmt.where(FarmVisitAssignment.visit_date >= from_date)
    return [
        {**{c.key: getattr(a, c.key) for c in a.__table__.columns},
         "assigned_technician_name": name}
        for a, name in (await db.execute(stmt)).all()
    ]


@router.put("/{farm_id}/visit-assignments", response_model=VisitAssignmentOut)
async def set_visit_assignment(
    farm_id: uuid.UUID,
    body: VisitAssignmentBody,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    """Reassign (or skip) one day's visit.

    Idempotent per (farm, date): re-sending replaces the override rather than
    stacking duplicates, which the unique constraint would reject anyway.

    Only an admin or the farm's STANDING technician may hand a day off. Scope
    alone is not enough: a relief technician's scope comes from visit
    assignments, so letting anyone in scope write them would let a one-day
    cover assign themselves future days and renew their own access forever.
    """
    if not await check_farm_access(db, current_user, farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")

    # Admin scope passes check_farm_access for ANY id — without this, a bad id
    # dies at the FK constraint and surfaces as a misleading concurrency 409.
    farm = await db.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    if current_user["role"] != "admin" and farm.assigned_technician_id != current_user["id"]:
        raise HTTPException(
            status_code=403,
            detail="Only the farm's standing technician or an admin can change visit assignments",
        )

    if body.visit_date < local_today():
        raise HTTPException(status_code=422, detail="visit_date cannot be in the past")

    if body.assigned_technician_id is not None:
        tech = await db.get(User, body.assigned_technician_id)
        if tech is None or tech.role not in (UserRole.technician, UserRole.admin):
            raise HTTPException(
                status_code=422,
                detail="assigned_technician_id must be an existing technician or admin",
            )

    assignment = await db.scalar(
        select(FarmVisitAssignment).where(
            FarmVisitAssignment.farm_id == farm_id,
            FarmVisitAssignment.visit_date == body.visit_date,
        ).with_for_update()
    )
    if assignment is None:
        assignment = FarmVisitAssignment(farm_id=farm_id, visit_date=body.visit_date)
        db.add(assignment)
    assignment.assigned_technician_id = body.assigned_technician_id
    assignment.reason = body.reason

    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent PUTs for the same (farm, date) both took the insert
        # path; the unique constraint caught the second. A retry will update.
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This visit was assigned concurrently — retry to overwrite",
        )
    await db.refresh(assignment)
    name = None
    if assignment.assigned_technician_id:
        tech = await db.get(User, assignment.assigned_technician_id)
        name = tech.name if tech else None
    return {**{c.key: getattr(assignment, c.key) for c in assignment.__table__.columns},
            "assigned_technician_name": name}


@router.delete("/{farm_id}/visit-assignments/{visit_date}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_visit_assignment(
    farm_id: uuid.UUID,
    visit_date: date,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    """Drop an override so the standing technician covers the day again."""
    if not await check_farm_access(db, current_user, farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")

    farm = await db.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    if current_user["role"] != "admin" and farm.assigned_technician_id != current_user["id"]:
        raise HTTPException(
            status_code=403,
            detail="Only the farm's standing technician or an admin can change visit assignments",
        )
    if visit_date < local_today():
        # Past overrides are history (and access-grant records) — immutable.
        raise HTTPException(status_code=422, detail="Cannot delete a past visit assignment")

    await db.execute(
        delete(FarmVisitAssignment).where(
            FarmVisitAssignment.farm_id == farm_id,
            FarmVisitAssignment.visit_date == visit_date,
        )
    )
    await db.commit()
