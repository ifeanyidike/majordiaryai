import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.auth import get_current_user, get_token_claims, require_roles
from app.models.models import Farm, User, UserRole
from app.schemas.users import UserAdminUpdate, UserCreate, UserUpdate, UserOut

router = APIRouter()

# Roles a user may claim for themselves at signup — NEVER admin.
SELF_SERVE_ROLES = {UserRole.technician, UserRole.farm, UserRole.vet}


@router.get("/", response_model=List[UserOut])
async def list_users(
    role: Optional[UserRole] = None,
    current_user: dict = Depends(require_roles("admin", "technician")),
    db: AsyncSession = Depends(get_db),
):
    """Users, optionally filtered by role.

    Admins get the whole staff directory (the farm form's technician picker).
    Technicians can only enumerate OTHER TECHNICIANS — they need that to hand a
    day's visit to a relief tech, but have no business listing farm managers,
    vets or admins.
    """
    stmt = select(User, Farm.name).outerjoin(Farm, Farm.id == User.farm_id).order_by(User.name)
    if current_user["role"] != "admin":
        stmt = stmt.where(User.role == UserRole.technician)
    elif role is not None:
        stmt = stmt.where(User.role == role)
    return [
        {**{c.key: getattr(u, c.key) for c in u.__table__.columns}, "farm_name": farm_name}
        for u, farm_name in (await db.execute(stmt)).all()
    ]


@router.patch("/{user_id}", response_model=UserOut)
async def admin_update_user(
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Set another user's role and farm — how a Farm Manager is actually made.

    Signup deliberately refuses the admin role and ignores farm_id, so without
    this there was no way to turn a signed-up account into a farm manager (or
    into an admin) at all.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    data = body.model_dump(exclude_unset=True)

    # An admin demoting themselves could leave the system with no admin and no
    # way back in. Changing someone else's role is fine.
    if "role" in data and data["role"] is not None and user_id == current_user["id"] \
            and data["role"] != UserRole.admin:
        raise HTTPException(
            status_code=409,
            detail="You cannot change your own role — ask another admin",
        )

    if data.get("name") is None:
        data.pop("name", None)  # non-nullable

    for field, value in data.items():
        setattr(user, field, value)

    # farm_id scopes a Farm Manager to their farm; on any other role it is
    # meaningless and would be misleading to keep.
    if user.role != UserRole.farm:
        user.farm_id = None
    elif user.farm_id is not None and await db.get(Farm, user.farm_id) is None:
        raise HTTPException(status_code=422, detail="farm_id does not exist")

    await db.commit()
    await db.refresh(user)
    farm_name = None
    if user.farm_id:
        farm = await db.get(Farm, user.farm_id)
        farm_name = farm.name if farm else None
    return {**{c.key: getattr(user, c.key) for c in user.__table__.columns},
            "farm_name": farm_name}


@router.get("/me", response_model=UserOut)
async def get_me(
    claims: dict = Depends(get_token_claims),
    db: AsyncSession = Depends(get_db),
):
    """Return the caller's profile.

    Uses token-only auth so a missing profile is a clean 404 (not 401) — the
    client relies on that 404 to trigger first-login profile creation via
    POST /users/me.
    """
    user = await db.get(User, claims["id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return user


@router.post("/me", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: UserCreate,
    claims: dict = Depends(get_token_claims),
    db: AsyncSession = Depends(get_db),
):
    """Called once after Supabase Auth signup to write the users table record.

    Uses token-only auth (no users row exists yet). farm_id is ignored here —
    an admin assigns it later via PATCH.
    """
    existing = await db.get(User, claims["id"])
    if existing:
        raise HTTPException(status_code=409, detail="Profile already exists")

    if body.role not in SELF_SERVE_ROLES:
        raise HTTPException(status_code=403, detail="Role not allowed at signup")

    user = User(
        id=claims["id"],
        name=body.name,
        email=body.email,
        role=body.role,
        phone=body.phone,
        employee_id=body.employee_id,
        region=body.region,
        farm_id=None,  # admin assigns via PATCH
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    await db.refresh(user)
    return user


@router.patch("/me", response_model=UserOut)
async def update_profile(
    body: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue  # name is non-nullable
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user
