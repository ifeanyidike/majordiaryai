"""Object-level authorization helpers.

Role scoping rules:
  admin       → all farms
  farm        → only their own farm
  technician  → farms where they are the assigned technician, plus any farm
                they are covering for a recent/upcoming visit
  vet         → farms assigned via vet_farm_assignments

Out-of-scope resources return 404 (not 403) to avoid enumeration.
"""

import uuid
from datetime import timedelta
from typing import Optional, Set
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.timeutils import local_today
from app.models.models import Cow, Farm, FarmVisitAssignment, Vet, VetFarmAssignment

# How long a day-cover keeps granting the relief technician access to the farm,
# so late data entry still works without the grant lasting indefinitely.
RELIEF_ACCESS_GRACE_DAYS = 7


def farm_ids_select(current_user: dict):
    """Selectable of farm ids the user may access, or None for admin (all farms)."""
    role = current_user["role"]
    if role == "admin":
        return None
    if role == "farm":
        return select(Farm.id).where(Farm.id == current_user["farm_id"])
    if role == "technician":
        # Standing assignment, plus any farm they have been given a visit for.
        # A relief technician covering someone's route must be able to open the
        # farm and record work there, or the reassignment is cosmetic.
        #
        # Bounded on BOTH sides. Without an upper bound a visit dated years
        # ahead granted access from the moment it was created — and anyone who
        # can create an assignment could grant themselves indefinite access to
        # any farm. Access starts on the day of the visit and lasts
        # RELIEF_ACCESS_GRACE_DAYS afterwards for late data entry.
        today = local_today()
        cutoff = today - timedelta(days=RELIEF_ACCESS_GRACE_DAYS)
        covering = (
            select(FarmVisitAssignment.farm_id)
            .where(
                FarmVisitAssignment.assigned_technician_id == current_user["id"],
                FarmVisitAssignment.visit_date >= cutoff,
                FarmVisitAssignment.visit_date <= today,
            )
        )
        return select(Farm.id).where(
            or_(
                Farm.assigned_technician_id == current_user["id"],
                Farm.id.in_(covering),
            )
        )
    # vet
    return (
        select(VetFarmAssignment.farm_id)
        .join(Vet, Vet.id == VetFarmAssignment.vet_id)
        .where(Vet.user_id == current_user["id"])
    )


def scope_to_farms(stmt, current_user: dict, farm_id: Optional[uuid.UUID] = None, col=None):
    """Apply role scoping FIRST; a farm_id param may only narrow within it."""
    if col is None:
        col = Cow.farm_id
    allowed = farm_ids_select(current_user)
    if allowed is not None:
        stmt = stmt.where(col.in_(allowed))
    if farm_id:
        stmt = stmt.where(col == farm_id)
    return stmt


async def get_allowed_farm_ids(db: AsyncSession, current_user: dict) -> Optional[Set[uuid.UUID]]:
    """Concrete set of allowed farm ids; None means all farms (admin)."""
    allowed = farm_ids_select(current_user)
    if allowed is None:
        return None
    result = await db.execute(allowed)
    return {row[0] for row in result.all()}


async def check_farm_access(db: AsyncSession, current_user: dict, farm_id: uuid.UUID) -> bool:
    allowed = await get_allowed_farm_ids(db, current_user)
    return allowed is None or farm_id in allowed


async def get_cow_scoped(
    db: AsyncSession,
    current_user: dict,
    cow_id: uuid.UUID,
    for_update: bool = False,
) -> Cow:
    """Load a cow the caller is allowed to see, else 404."""
    stmt = select(Cow).where(Cow.id == cow_id)
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    cow = result.scalar_one_or_none()
    if not cow or not await check_farm_access(db, current_user, cow.farm_id):
        raise HTTPException(status_code=404, detail="Cow not found")
    return cow
