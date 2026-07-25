"""drop vet visit scheduling (app does not manage vet scheduling)

The vet area is pregnancy diagnosis only; scheduling was removed per the
Vet Area / Pregnancy Check Workflow spec. Drops the vet_visit_schedules
table and the now-unused visit_type enum.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-25
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table first (it references the enum), then the enum type.
    op.execute("drop table if exists vet_visit_schedules cascade")
    op.execute("drop type if exists visit_type")


def downgrade() -> None:
    op.execute(
        "create type visit_type as enum "
        "('pregnancy_check', 'consultation', 'vaccination', 'herd_health')"
    )
    op.execute(
        """
        create table vet_visit_schedules (
            id uuid primary key default uuid_generate_v4(),
            farm_id uuid not null references farms(id) on delete cascade,
            vet_id uuid references users(id),
            scheduled_date date not null,
            visit_type visit_type not null default 'pregnancy_check',
            completed boolean default false,
            notes text,
            created_at timestamptz default now()
        )
        """
    )
    op.execute(
        "create index idx_vet_visit_schedules_scheduled_date "
        "on vet_visit_schedules(scheduled_date)"
    )
