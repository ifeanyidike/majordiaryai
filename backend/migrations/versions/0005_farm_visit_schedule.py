"""farm visit rotation, technician reassignment, dry-off confirmation

The technician's General To-Do list shows the farms he visits TODAY. Farms run
on rotations (5-day, 6-day, ...), and a day can be handed to a relief
technician, so the list varies day to day. Adds:

  farms.visit_interval_days / visit_anchor_date  — the rotation
  farm_visit_assignments                          — who covers a specific date
  cows.dry_off_confirmed_date                     — makes the Dry Report
                                                    completable instead of a
                                                    permanently repeating item

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "farms",
        sa.Column("visit_interval_days", sa.Integer(), nullable=False, server_default="7"),
    )
    op.add_column("farms", sa.Column("visit_anchor_date", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_farms_visit_interval_positive", "farms", "visit_interval_days > 0"
    )

    op.add_column("cows", sa.Column("dry_off_confirmed_date", sa.Date(), nullable=True))

    op.create_table(
        "farm_visit_assignments",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("farm_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visit_date", sa.Date(), nullable=False),
        # NULL technician = the visit is explicitly skipped that day.
        sa.Column("assigned_technician_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_technician_id"], ["users.id"]),
        sa.UniqueConstraint("farm_id", "visit_date", name="uq_farm_visit_assignment_day"),
    )
    # The General To-Do list queries "who covers what on this date" every load.
    op.create_index(
        "ix_farm_visit_assignments_date", "farm_visit_assignments",
        ["visit_date", "assigned_technician_id"],
    )


def downgrade() -> None:
    op.drop_column("cows", "dry_off_confirmed_date")
    op.drop_index("ix_farm_visit_assignments_date", table_name="farm_visit_assignments")
    op.drop_table("farm_visit_assignments")
    op.drop_constraint("ck_farms_visit_interval_positive", "farms", type_="check")
    op.drop_column("farms", "visit_anchor_date")
    op.drop_column("farms", "visit_interval_days")
