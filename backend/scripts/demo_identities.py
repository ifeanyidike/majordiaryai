"""Give the demo sign-ins real identities, linked to the seeded data.

The four demo accounts are created through Supabase auth, not by seed.py, so
a reseed left them as "Test Veterinarian" and "Test Farm Manager" -- and,
worse, unlinked: the vet login pointed at no vet record, so the vet signed in
to 0 farms and 0 cows. Each account is matched to someone who already exists
in the seeded data:

  vet@        -> Dr. Sarah Mitchell, and her vet record now points at this login
  farm@       -> Green Valley Dairy's owner on record, linked to that farm
  technician@ -> Robert Hayes, and any farm with no technician is given to him
  admin@      -> Karen Walsh, the office

Idempotent, keyed on email, and it only ever touches these four accounts.
Run on its own after a reseed, or let seed.py call apply() at the end.

  cd backend && .venv/bin/python -m scripts.demo_identities --apply
"""

import asyncio
import sys
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

TECHNICIAN = "technician@majordairy.test"
FARM_MANAGER = "farm@majordairy.test"
VET = "vet@majordairy.test"
ADMIN = "admin@majordairy.test"

MANAGER_FARM = "Green Valley Dairy"
VET_RECORD = "Dr. Sarah Mitchell"


async def apply(session: AsyncSession) -> list:
    """Make the demo accounts match the seeded data. Returns what changed."""
    done = []
    q = lambda sql, **kw: session.execute(text(sql), kw)

    async def user_id(email):
        return (await q("select id from users where email = :e", e=email)).scalar()

    tech = await user_id(TECHNICIAN)
    if tech:
        await q("""update users set name = 'Robert Hayes', phone = '+1 (519) 555-0102',
                   employee_id = 'TECH-0142', region = 'Southwestern Ontario'
                   where id = :i""", i=tech)
        n = (await q("update farms set assigned_technician_id = :i "
                     "where assigned_technician_id is null", i=tech)).rowcount
        done.append(f"technician: Robert Hayes; {n} unassigned farm(s) given to him")

    manager = await user_id(FARM_MANAGER)
    farm = (await q("select id, owner_name, phone from farms where name = :n",
                    n=MANAGER_FARM)).first()
    if manager and farm:
        await q("update users set name = :n, phone = :p, farm_id = :f where id = :i",
                n=farm.owner_name, p=farm.phone, f=farm.id, i=manager)
        done.append(f"farm manager: {farm.owner_name}, linked to {MANAGER_FARM}")

    vet_user = await user_id(VET)
    vet = (await q("select id, name, phone from vets where name = :n", n=VET_RECORD)).first()
    if vet_user and vet:
        # One login, one vet: unhook it from any other record first.
        await q("update vets set user_id = null where user_id = :u and id <> :v",
                u=vet_user, v=vet.id)
        await q("update vets set user_id = :u where id = :v", u=vet_user, v=vet.id)
        await q("update users set name = :n, phone = :p where id = :i",
                n=vet.name, p=vet.phone, i=vet_user)
        farms = (await q("select count(*) from vet_farm_assignments where vet_id = :v",
                         v=vet.id)).scalar()
        done.append(f"vet: {vet.name}, linked to her vet record ({farms} farms)")

    admin = await user_id(ADMIN)
    if admin:
        await q("update users set name = 'Karen Walsh' where id = :i", i=admin)
        done.append("admin: Karen Walsh")

    return done


async def main() -> None:
    target = f"{settings.db_host}/{settings.db_name}"
    if "--apply" not in sys.argv:
        print(f"Would update the four demo accounts on {target}. Re-run with --apply.")
        return
    port = 5432 if settings.db_port == 6543 else settings.db_port
    engine = create_async_engine(
        f"postgresql+asyncpg://{settings.db_user}:{quote_plus(settings.db_password)}"
        f"@{settings.db_host}:{port}/{settings.db_name}",
        poolclass=NullPool,
    )
    async with async_sessionmaker(engine, class_=AsyncSession)() as session:
        done = await apply(session)
        await session.commit()
    await engine.dispose()
    print(f"Updated on {target}:")
    for line in done or ["nothing — none of the demo accounts exist here"]:
        print("  -", line)


if __name__ == "__main__":
    asyncio.run(main())
