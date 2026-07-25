"""cow health status + recheck, new visit types

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-24
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── New enum type ─────────────────────────────────────────
    op.execute("create type health_status as enum ('healthy', 'sick')")

    # ── Cow health columns ────────────────────────────────────
    op.execute("alter table cows add column health_status health_status default 'healthy'")
    # Set to today+7 when a cow is marked sick; cleared when marked healthy.
    op.execute("alter table cows add column recheck_due_date date")

    # ── visit_type extension ──────────────────────────────────
    # ADD VALUE requires PostgreSQL 12+; on PG12+ it is allowed inside a
    # transaction block as long as the new value is not used in the same one.
    op.execute("alter type visit_type add value if not exists 'vaccination'")
    op.execute("alter type visit_type add value if not exists 'herd_health'")


def downgrade() -> None:
    op.execute("alter table cows drop column if exists recheck_due_date")
    op.execute("alter table cows drop column if exists health_status")
    # health_status enum type was created in this migration, so drop it here.
    op.execute("drop type if exists health_status")
    # Note: PostgreSQL cannot remove a value from an enum type; the
    # 'vaccination' / 'herd_health' visit_type values are left in place.
