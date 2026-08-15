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

from app.core.timeutils import local_today
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.base import Base
from app.models.models import (
    Cow, CowStatus, EnrollmentStatus, Farm, NeedlingEnrollment, NeedlingRecord,
    ProtocolType, User, UserRole,
)

# The app computes 'today' in the farm timezone; using the machine's
# UTC date made boundary tests flake on CI between 00:00 and 04:00.
TODAY = local_today()

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


# Fixtures that need the throwaway Postgres. A test asking for none of these is
# a pure unit test and must still run without it.
_DB_FIXTURES = frozenset({
    "db", "engine", "api", "farm", "make_cow", "technician", "records_of",
})


def pytest_collection_modifyitems(config, items):
    """Skip only the tests that actually need a database.

    This used to skip the WHOLE suite, which made `pytest` on a machine
    without the Docker container exit 0 having asserted nothing at all — the
    spec constants, the schema-freshness guards, the import parsing rules and
    the scheduler tests all reported as passing-by-absence. A green run that
    verified nothing is worse than a red one.
    """
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        if not (_DB_FIXTURES & set(getattr(item, "fixturenames", ()))):
            continue  # pure unit test — runs anywhere
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


# ── HTTP-level harness ───────────────────────────────────────────────
# The suite above drives services directly, which leaves the routers — auth,
# role gates, request validation, error mapping — verified by reading only.
# These fixtures exercise the real app through ASGI so a role gate that stops
# matching the spec fails a test instead of shipping.


@pytest_asyncio.fixture
async def api(db):
    """Factory returning an HTTP client authenticated as a given role.

    `get_current_user` is overridden (not `require_roles`), so the real
    permission logic still runs — only token verification is stubbed, since
    minting Supabase JWTs in tests would test Supabase, not this app.
    """
    import httpx

    from app.core.auth import get_current_user
    from app.core.database import get_db
    from main import app

    def _make(
        role: str = "admin", user_id=None, farm_id=None,
        *, real_auth: bool = False, token_only_email: str = None,
    ) -> "httpx.AsyncClient":
        # real_auth=True stubs ONLY the token layer and lets get_current_user
        # run its real query. Needed for anything the dependency itself decides
        # -- the activation gate lives inside it, so overriding the whole
        # dependency (the default below) would step straight past the thing
        # under test.
        if real_auth or token_only_email:
            import app.core.auth as auth_mod
            from fastapi.security import HTTPAuthorizationCredentials

            uid = user_id or uuid.uuid4()
            claims = {"user_id": uid, "id": uid,
                      "email": token_only_email or f"{role}@test.local"}

            async def _fake_decode(_token):
                return claims

            auth_mod._decode_token = _fake_decode
            app.dependency_overrides[auth_mod.bearer_scheme] = (
                lambda: HTTPAuthorizationCredentials(scheme="Bearer", credentials="x")
            )
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides[get_db] = lambda: db
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer x"},
            )

        # Recorded work carries technician_id FKs, so the caller must be a real
        # users row. When the test supplies an id it owns that row already;
        # otherwise create one here (autoflush persists it before the first
        # query the endpoint runs).
        if user_id is None:
            user_id = uuid.uuid4()
            db.add(User(
                id=user_id, name=f"Test {role}",
                email=f"{uuid.uuid4().hex[:8]}@test.local",
                role=UserRole(role),
            ))
        caller = {
            "id": user_id,
            "name": f"Test {role}",
            "email": f"{role}@test.local",
            "role": role,
            "farm_id": farm_id,
        }
        # Hand the request the test's transaction so rows created in the test
        # are visible to the endpoint (and roll back with everything else).
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: caller
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    yield _make
    from main import app as _app
    _app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def make_user(db):
    """A persisted user of a given role, for FK-bearing assignments."""
    async def _make(role: UserRole = UserRole.technician, name: str = "Tech") -> User:
        u = User(
            id=uuid.uuid4(), name=name,
            email=f"{uuid.uuid4().hex[:8]}@test.local", role=role,
        )
        db.add(u)
        await db.flush()
        return u

    return _make
