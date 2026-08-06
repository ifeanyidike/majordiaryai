"""Test fixtures: a disposable Postgres, rolled back after every test.

These tests execute the ACTUAL query builders and endpoint helpers in
`app/services/` — no hand-written mirror of the predicates. Editing the real SQL
therefore breaks the tests, which is the entire point.

They NEVER touch the application database. The connection URL comes exclusively
from `TEST_DATABASE_URL`; if it is unset the whole suite skips with instructions
rather than silently falling back to `settings`, which points at production.

    make test          # starts a throwaway Postgres in Docker and runs pytest
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/majordairy_test \
        .venv/bin/python -m pytest tests/ -q

The schema is created from the models once per session and every test runs in a
transaction that is rolled back, so tests never see each other's rows.
"""

import os
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.base import Base
from app.models.models import (
    Cow, CowStatus, EnrollmentStatus, Farm, NeedlingEnrollment, NeedlingRecord,
    ProtocolType, User, UserRole,
)

TODAY = date.today()

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()

_SKIP_REASON = (
    "TEST_DATABASE_URL is not set. These tests need a THROWAWAY Postgres and "
    "must never run against the application database. Run `make test`, or set "
    "TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/dbname"
)

# Guard against a copy-pasted production URL: the app database is off limits even
# if someone points TEST_DATABASE_URL at it.
if TEST_DATABASE_URL:
    try:
        from app.core.config import settings

        if settings.db_host in TEST_DATABASE_URL and settings.db_name in TEST_DATABASE_URL:
            raise RuntimeError(
                "TEST_DATABASE_URL points at the application database "
                f"({settings.db_host}/{settings.db_name}). Refusing to run — tests "
                "create and delete rows. Use a throwaway database."
            )
    except ImportError:  # pragma: no cover — settings are optional for tests
        pass


def pytest_collection_modifyitems(config, items):
    """Skip everything (loudly) when no test database is configured."""
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        item.add_marker(skip)


_schema_ready = False


@pytest_asyncio.fixture
async def engine():
    """Per-test engine. asyncpg connections are bound to the event loop that
    created them, so a shared engine across loops raises "another operation is
    in progress"; NullPool + per-test scope keeps each test self-contained.
    """
    global _schema_ready
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    if not _schema_ready:
        # Rebuild from the models every session. `create_all` alone is
        # checkfirst, so a database left over from an older revision keeps its
        # stale columns and every test dies on an unrelated schema error.
        # Drop the whole schema rather than `drop_all`: cows <-> inseminations
        # is a mutual FK, which drop_all can't order.
        async with eng.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.run_sync(Base.metadata.create_all)
        _schema_ready = True
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine):
    """A session whose work is always rolled back."""
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def farm(db) -> Farm:
    """A throwaway farm for the test's cows (rolled back)."""
    f = Farm(id=uuid.uuid4(), name=f"Test Farm {uuid.uuid4().hex[:6]}",
             owner_name="Test Owner", herd_size=0)
    db.add(f)
    await db.flush()
    return f


@pytest_asyncio.fixture
async def technician(db) -> User:
    """A user to attribute recorded work to."""
    u = User(id=uuid.uuid4(), email=f"tech-{uuid.uuid4().hex[:6]}@test.local",
             name="Test Tech", role=UserRole.technician)
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
def make_cow(db, farm):
    """Build a cow with an enrollment + records, in one call.

    steps: list of (protocol_day, day_offset_from_today, treatment, is_final, completed)
    """
    async def _make(
        *,
        protocol: ProtocolType = ProtocolType.ovsynch,
        enrollment_status: EnrollmentStatus = EnrollmentStatus.active,
        cow_status: CowStatus = CowStatus.needling,
        steps=(),
        extra_enrollments=(),
        **cow_fields,
    ) -> Cow:
        cow = Cow(
            id=uuid.uuid4(), farm_id=farm.id,
            ear_tag=f"T-{uuid.uuid4().hex[:8]}",
            status=cow_status, lactation_number=1,
            **cow_fields,
        )
        db.add(cow)
        await db.flush()

        async def add_enrollment(proto, status, step_list):
            enr = NeedlingEnrollment(
                id=uuid.uuid4(), cow_id=cow.id, protocol=proto,
                start_date=TODAY - timedelta(days=9), current_day=1, status=status,
            )
            db.add(enr)
            await db.flush()
            for day, offset, treatment, is_final, completed in step_list:
                db.add(NeedlingRecord(
                    id=uuid.uuid4(), enrollment_id=enr.id, cow_id=cow.id,
                    protocol_day=day, scheduled_date=TODAY + timedelta(days=offset),
                    treatment=treatment, is_final=is_final, completed=completed,
                ))
            await db.flush()
            return enr

        cow.enrollment = await add_enrollment(protocol, enrollment_status, steps)
        for proto, status, step_list in extra_enrollments:
            await add_enrollment(proto, status, step_list)
        await db.flush()
        return cow

    return _make


@pytest_asyncio.fixture
def records_of(db):
    """All needling records for a cow, oldest first."""
    from sqlalchemy import select

    async def _get(cow):
        result = await db.execute(
            select(NeedlingRecord)
            .where(NeedlingRecord.cow_id == cow.id)
            .order_by(NeedlingRecord.scheduled_date)
        )
        return result.scalars().all()

    return _get
