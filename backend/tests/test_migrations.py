"""Guards for things that exist ONLY in migrations.

Every other test builds the schema with `create_all`, so server-side defaults,
check constraints and row level security were never exercised. That is how
schema.sql rotted to the 0004 state and how two tables shipped without RLS.

These read the committed schema.sql, which scripts/dump_schema.sh regenerates
from the migration chain — so a migration that forgets RLS fails here.
"""

import pathlib
import re

import pytest

SCHEMA = pathlib.Path(__file__).resolve().parents[1] / "schema.sql"


def _schema_text() -> str:
    if not SCHEMA.exists():  # pragma: no cover
        pytest.skip("schema.sql not generated")
    return SCHEMA.read_text()


def _tables(sql: str):
    return set(re.findall(r"CREATE TABLE public\.(\w+)", sql))


# alembic_version is Alembic's own bookkeeping and is never client-reachable.
EXEMPT = {"alembic_version"}


def test_every_table_has_row_level_security():
    """RLS is the last line of defence: PostgREST exposes these tables directly
    with the anon key that ships inside the mobile app. bulls and
    farm_visit_assignments were created without it, and a direct insert into
    farm_visit_assignments granted the writer API access to that farm."""
    sql = _schema_text()
    protected = set(re.findall(r"ALTER TABLE (?:ONLY )?public\.(\w+) ENABLE ROW LEVEL SECURITY", sql))
    missing = _tables(sql) - protected - EXEMPT
    assert not missing, f"tables without RLS: {sorted(missing)}"


def test_schema_is_not_stale():
    """A database provisioned from a stale schema.sql crashes the ORM on the
    first query for a column the models expect."""
    sql = _schema_text()
    for expected in [
        "visit_weekdays",            # 0006
        "CREATE TABLE public.bulls", # 0008
        "farm_visit_assignments",    # 0005
        "insemination_code",         # 0008
        "dry_off_confirmed_date",    # 0005
        "email_status",              # 0007
    ]:
        assert expected in sql, f"schema.sql is missing {expected!r} — re-run scripts/dump_schema.sh"


def test_empty_visit_schedule_is_rejected_by_the_constraint():
    """array_length() of an empty array is NULL, and a CHECK treats NULL as
    passing — so the original constraint accepted the exact "no visit days"
    state it claimed to forbid. cardinality() returns 0 and rejects it."""
    sql = _schema_text()
    constraint = next(
        (line for line in sql.splitlines() if "ck_farms_visit_weekdays_valid" in line), ""
    )
    assert "cardinality" in constraint, (
        "the weekday constraint still uses array_length, which lets an empty "
        f"array through: {constraint.strip()}"
    )
