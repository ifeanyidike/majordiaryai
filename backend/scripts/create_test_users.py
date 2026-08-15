"""Create one working login per role, for testing the app end to end.

Each role sees a different app, and two of them need more than a users row to
work at all:

  admin       all farms. Cannot be created through the app — signup deliberately
              refuses the admin role (see routers/users.SELF_SERVE_ROLES), so
              this script is the only way to get one.
  technician  farms where they are the assigned technician. Gets assigned to
              every farm here so the To-Do list is not empty.
  farm        one farm only — needs users.farm_id set, or every screen is blank.
  vet         farms assigned via vet_farm_assignments — needs a `vets` row AND
              the assignment rows, or the vet sees nothing.

Accounts are created in Supabase Auth with the email pre-confirmed, so you can
log in immediately without clicking a verification link.

    cd backend && .venv/bin/python -m scripts.create_test_users

Idempotent: re-running updates the existing accounts rather than failing. Pass
--password to choose your own.

NOT for production. It creates known-password accounts, including an admin.
"""

import argparse
import asyncio
import sys
import uuid

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from urllib.parse import quote_plus

from app.core.config import effective_db_port, settings
from app.models.models import Farm, User, UserRole, Vet, VetFarmAssignment

DEFAULT_PASSWORD = "MajorDairy!2026"

ACCOUNTS = [
    ("admin",      "admin@majordairy.test",      "Test Admin"),
    ("technician", "technician@majordairy.test", "Test Technician"),
    ("farm",       "farm@majordairy.test",       "Test Farm Manager"),
    ("vet",        "vet@majordairy.test",        "Test Veterinarian"),
]


async def _auth_user_id(client: httpx.AsyncClient, email: str, password: str) -> str:
    """Create the Supabase Auth user, or return the existing one's id."""
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/json",
    }
    resp = await client.post(
        f"{settings.supabase_url}/auth/v1/admin/users",
        headers=headers,
        json={"email": email, "password": password, "email_confirm": True},
    )
    if resp.status_code in (200, 201):
        return resp.json()["id"]

    # Already there — find it and reset the password so the printed one works.
    listed = await client.get(
        f"{settings.supabase_url}/auth/v1/admin/users",
        headers=headers,
        params={"page": 1, "per_page": 200},
    )
    listed.raise_for_status()
    for u in listed.json().get("users", []):
        if (u.get("email") or "").lower() == email.lower():
            await client.put(
                f"{settings.supabase_url}/auth/v1/admin/users/{u['id']}",
                headers=headers,
                json={"password": password, "email_confirm": True},
            )
            return u["id"]
    raise RuntimeError(f"Could not create or find the auth user for {email}: {resp.text[:200]}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    args = parser.parse_args()

    import os
    if os.getenv("ALLOW_TEST_USERS") != "1":
        print(
            "REFUSING TO RUN: this creates known-password accounts INCLUDING A "
            "FULL ADMIN.\n"
            f"It would run against {settings.supabase_url}.\n\n"
            "If that is a disposable environment, re-run with:\n"
            "    ALLOW_TEST_USERS=1 .venv/bin/python -m scripts.create_test_users",
            file=sys.stderr,
        )
        return 1

    if not settings.supabase_service_key or not settings.supabase_url:
        print("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.", file=sys.stderr)
        return 1

    url = (
        f"postgresql+asyncpg://{settings.db_user}:{quote_plus(settings.db_password)}"
        f"@{settings.db_host}:{effective_db_port()}/{settings.db_name}"
    )
    engine = create_async_engine(url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with httpx.AsyncClient(timeout=30) as client, Session() as db:
        farms = (await db.execute(select(Farm).order_by(Farm.name))).scalars().all()
        if not farms:
            print("No farms exist — seed the database first.", file=sys.stderr)
            return 1

        created = []
        for role, email, name in ACCOUNTS:
            user_id = uuid.UUID(await _auth_user_id(client, email, args.password))

            user = await db.get(User, user_id)
            if user is None:
                user = User(id=user_id, name=name, email=email, role=UserRole(role))
                db.add(user)
            user.name, user.email, user.role = name, email, UserRole(role)

            # A farm manager with no farm sees an empty app.
            user.farm_id = farms[0].id if role == "farm" else None

            # Insert the user BEFORE anything references it: farms.assigned_
            # technician_id is a foreign key, and autoflush would otherwise try
            # the farm update first and hit a violation.
            await db.flush()

            if role == "technician":
                # Assign every farm so the General To-Do list has something on it.
                for f in farms:
                    f.assigned_technician_id = user_id

            if role == "vet":
                vet = (await db.execute(
                    select(Vet).where(Vet.user_id == user_id)
                )).scalar_one_or_none()
                if vet is None:
                    vet = Vet(id=uuid.uuid4(), user_id=user_id, name=name, email=email)
                    db.add(vet)
                    await db.flush()
                existing = {
                    a.farm_id for a in (await db.execute(
                        select(VetFarmAssignment).where(VetFarmAssignment.vet_id == vet.id)
                    )).scalars().all()
                }
                for f in farms:
                    if f.id not in existing:
                        db.add(VetFarmAssignment(vet_id=vet.id, farm_id=f.id))

            created.append((role, email))

        await db.commit()

    await engine.dispose()

    print("\nAccounts ready — same password for all four:\n")
    for role, email in created:
        print(f"  {role:<11} {email}")
    print(f"\n  password: {args.password}\n")
    print("Log out in the app (Profile → Sign Out) to switch between them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
