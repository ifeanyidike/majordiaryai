from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.auth import get_current_user, get_token_claims
from app.models.models import User, UserRole
from app.schemas.users import UserCreate, UserUpdate, UserOut

router = APIRouter()

# Roles a user may claim for themselves at signup — NEVER admin.
SELF_SERVE_ROLES = {UserRole.technician, UserRole.farm, UserRole.vet}


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
