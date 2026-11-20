import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.core.auth import get_current_user, get_token_claims, require_roles
from app.models.models import Farm, PushToken, User, UserRole
from app.schemas.users import (
    PushTokenBody, TechnicianCreate, UserAdminUpdate, UserCreate, UserUpdate, UserOut,
)
from app.services import auth_admin

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


async def _email_in_use(db: AsyncSession, email: str, other_than: Optional[uuid.UUID] = None) -> bool:
    stmt = select(func.count(User.id)).where(func.lower(User.email) == email.lower())
    if other_than is not None:
        stmt = stmt.where(User.id != other_than)
    return bool(await db.scalar(stmt))


_EMAIL_TAKEN = "An account with this email already exists. If it is waiting, approve it under People."


@router.post("/technicians", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_technician(
    body: TechnicianCreate,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin, Technicians, Add: a working login and its profile, active at once.

    The login is made first, because the profile's id is the login's. If the
    profile then cannot be saved, the login is removed again, so a failed add
    never leaves an email that can sign in to nothing.
    """
    if await _email_in_use(db, body.email):
        raise HTTPException(status_code=409, detail=_EMAIL_TAKEN)
    try:
        login_id = await auth_admin.create_login(body.email, body.password)
    except auth_admin.LoginError as exc:
        if exc.taken:
            raise HTTPException(status_code=409, detail=_EMAIL_TAKEN)
        raise HTTPException(status_code=502, detail="The sign-in service refused the new login. Try again.")

    user = User(
        id=login_id, name=body.name, email=body.email, role=UserRole.technician,
        phone=body.phone, employee_id=body.employee_id, region=body.region, is_active=True,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        await auth_admin.undo("remove the new login", login_id, auth_admin.delete_login(login_id))
        raise HTTPException(status_code=409, detail=_EMAIL_TAKEN)
    await db.refresh(user)
    return {**{c.key: getattr(user, c.key) for c in user.__table__.columns}, "farm_name": None}


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

    # Same reasoning for deactivation: an admin switching themselves off has
    # no way back in, and if they were the only admin nobody can approve
    # anyone ever again.
    if data.get("is_active") is False and user_id == current_user["id"]:
        raise HTTPException(
            status_code=409,
            detail="You cannot deactivate your own account — ask another admin",
        )

    if data.get("name") is None or not str(data.get("name")).strip():
        data.pop("name", None)  # non-nullable

    # farm_id scopes a Farm Manager to their farm. Checked before anything is
    # written: a missing farm used to surface as a foreign-key error from the
    # autoflush (a 500), and now that an edit can change the login's email,
    # nothing may reach the login until the edit is known to be valid.
    role_after = data.get("role") or user.role
    farm_after = data["farm_id"] if "farm_id" in data else user.farm_id
    if role_after == UserRole.farm and farm_after is not None \
            and await db.get(Farm, farm_after) is None:
        raise HTTPException(status_code=422, detail="That farm no longer exists — pick another")

    # The sign-in email lives on the login, so it moves there first; the row
    # follows. Without that they would sign in with the old one and be shown
    # the new one.
    new_email = (data.pop("email", None) or "").strip().lower() or None
    old_email = user.email
    if new_email and new_email != (old_email or "").lower():
        if await _email_in_use(db, new_email, other_than=user.id):
            raise HTTPException(status_code=409, detail=_EMAIL_TAKEN)
        try:
            await auth_admin.change_email(user.id, new_email)
        except auth_admin.LoginError as exc:
            if exc.taken:
                raise HTTPException(status_code=409, detail=_EMAIL_TAKEN)
            raise HTTPException(status_code=502, detail="The sign-in service refused the email change. Try again.")
        user.email = new_email
    else:
        new_email = None

    for field, value in data.items():
        setattr(user, field, value)

    # On any role but Farm Manager, farm_id is meaningless and would be
    # misleading to keep.
    if user.role != UserRole.farm:
        user.farm_id = None

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if new_email:
            await auth_admin.undo("put the old email back", user.id,
                                  auth_admin.change_email(user.id, old_email))
        raise HTTPException(status_code=409, detail=_EMAIL_TAKEN)
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
        raise HTTPException(status_code=403, detail="That role can't be chosen when signing up")

    # The email must come from the verified token, never the request body:
    # otherwise anyone can register under somebody else's address, which is
    # what the rest of the system uses to identify a person.
    verified_email = claims.get("email")
    if not verified_email:
        raise HTTPException(
            status_code=422,
            detail="Your sign-in provider did not supply a verified email address",
        )

    user = User(
        id=claims["id"],
        name=body.name,
        email=verified_email,
        role=body.role,
        phone=body.phone,
        employee_id=body.employee_id,
        region=body.region,
        farm_id=None,  # admin assigns via PATCH
        # Inert until an admin activates it. Signup is open to anyone who can
        # complete Supabase auth, so the role above is a request rather than a
        # grant — see migration 0013 and core/auth.get_current_user.
        is_active=False,
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


@router.post("/me/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def register_push_token(
    body: PushTokenBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Let this device be woken for this user's Alarms and Office Alerts.

    Called on every app start, so it is an upsert: a token already on file
    for someone else MOVES to whoever is signed in now — a phone handed from
    one technician to another must stop waking the first.
    """
    stmt = pg_insert(PushToken).values(
        token=body.token, user_id=current_user["id"], platform=body.platform,
    )
    await db.execute(stmt.on_conflict_do_update(
        index_elements=[PushToken.token],
        set_={"user_id": current_user["id"], "platform": body.platform,
              "last_seen_at": func.now()},
    ))
    await db.commit()


@router.delete("/me/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def forget_push_token(
    body: PushTokenBody,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sign-out: this device stops waking for this user. Scoped to the caller,
    so nobody can unregister someone else's phone by knowing its token."""
    await db.execute(delete(PushToken).where(
        PushToken.token == body.token, PushToken.user_id == current_user["id"],
    ))
    await db.commit()
