"""
Link a signed-up account to farms/vet so role-scoping shows data.

A fresh signup is a technician/farm/vet with no farm attached, so role-scoping
returns nothing. This wires the account up. Run against a real account (created
via the app's sign-up) — identified by email.

Examples:
  # See everything (all farms/cows):
  python -m scripts.link_user --email you@example.com --admin

  # Assign as the technician for every farm (or one with --farm):
  python -m scripts.link_user --email you@example.com --technician
  python -m scripts.link_user --email you@example.com --technician --farm "Green Valley Dairy"

  # Farm manager for one farm:
  python -m scripts.link_user --email owner@example.com --farm-manager "Sunrise Farms"

  # Link to a seeded vet record:
  python -m scripts.link_user --email vet@example.com --as-vet "Dr. Sarah Mitchell"
"""

import argparse
import asyncio
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from urllib.parse import quote_plus

from app.core.config import settings
from app.models.models import Farm, User, UserRole, Vet


def _engine():
    # Session pooler (5432) supports prepared statements — see database.py.
    port = 5432 if settings.db_port == 6543 else settings.db_port
    url = (
        f"postgresql+asyncpg://{settings.db_user}:{quote_plus(settings.db_password)}"
        f"@{settings.db_host}:{port}/{settings.db_name}"
    )
    return create_async_engine(url, poolclass=NullPool)


async def _find_farm(s: AsyncSession, name: str) -> Farm:
    farm = (await s.execute(select(Farm).where(Farm.name == name))).scalar_one_or_none()
    if not farm:
        names = [f.name for f in (await s.execute(select(Farm))).scalars().all()]
        raise SystemExit(f"Farm '{name}' not found. Available: {names}")
    return farm


async def run(args) -> None:
    async with async_sessionmaker(_engine(), class_=AsyncSession, expire_on_commit=False)() as s:
        user = (await s.execute(select(User).where(User.email == args.email))).scalar_one_or_none()
        if not user:
            raise SystemExit(f"No account with email {args.email}. Sign up in the app first.")

        actions = []

        if args.admin:
            user.role = UserRole.admin
            actions.append("role → admin (sees all farms)")

        if args.technician:
            user.role = UserRole.technician
            if args.farm:
                farm = await _find_farm(s, args.farm)
                farm.assigned_technician_id = user.id
                actions.append(f"assigned technician for '{farm.name}'")
            else:
                await s.execute(update(Farm).values(assigned_technician_id=user.id))
                actions.append("assigned technician for ALL farms")

        if args.farm_manager:
            farm = await _find_farm(s, args.farm_manager)
            user.role = UserRole.farm
            user.farm_id = farm.id
            actions.append(f"role → farm, farm_id → '{farm.name}'")

        if args.as_vet:
            vet = (await s.execute(select(Vet).where(Vet.name == args.as_vet))).scalar_one_or_none()
            if not vet:
                names = [v.name for v in (await s.execute(select(Vet))).scalars().all()]
                raise SystemExit(f"Vet '{args.as_vet}' not found. Available: {names}")
            user.role = UserRole.vet
            vet.user_id = user.id
            actions.append(f"role → vet, linked to '{vet.name}'")

        if not actions:
            raise SystemExit("Nothing to do — pass one of --admin / --technician / --farm-manager / --as-vet")

        await s.commit()
        print(f"Linked {args.email}:")
        for a in actions:
            print(f"  • {a}")


def main() -> None:
    p = argparse.ArgumentParser(description="Link an account to farms/vet")
    p.add_argument("--email", required=True)
    p.add_argument("--admin", action="store_true", help="Promote to admin (sees all data)")
    p.add_argument("--technician", action="store_true", help="Assign as technician (all farms, or one with --farm)")
    p.add_argument("--farm", help="Limit --technician to this farm name")
    p.add_argument("--farm-manager", metavar="FARM_NAME", help="Set role=farm and attach to this farm")
    p.add_argument("--as-vet", metavar="VET_NAME", help="Set role=vet and link to this vet record")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
