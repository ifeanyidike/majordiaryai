"""farm visits are a weekday schedule, not an every-N-days rotation

Client clarification: a "5-day farm" means Monday–Friday and a "6-day farm"
means Monday–Saturday (Sunday off), rather than "one visit every 5/6 days".
Replaces farms.visit_interval_days / visit_anchor_date with the actual set of
weekdays, so an irregular pattern (Mon/Thu only) needs no further schema change.

Existing rows are mapped by their old interval: 5 → Mon–Fri, anything else →
Mon–Sat (the default).

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MON_SAT = "'{0,1,2,3,4,5}'::smallint[]"
MON_FRI = "'{0,1,2,3,4}'::smallint[]"


def upgrade() -> None:
    op.add_column(
        "farms",
        sa.Column(
            "visit_weekdays",
            sa.dialects.postgresql.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default=sa.text(MON_SAT),
        ),
    )
    # Carry the old intent across: only a 5-day interval maps to Mon–Fri.
    op.execute(f"update farms set visit_weekdays = {MON_FRI} where visit_interval_days = 5")

    # A farm must be visitable on at least one day, and 0-6 are the only valid
    # weekday values (Mon=0 … Sun=6).
    op.create_check_constraint(
        "ck_farms_visit_weekdays_valid",
        "farms",
        "array_length(visit_weekdays, 1) between 1 and 7"
        " and visit_weekdays <@ '{0,1,2,3,4,5,6}'::smallint[]",
    )

    op.drop_constraint("ck_farms_visit_interval_positive", "farms", type_="check")
    op.drop_column("farms", "visit_anchor_date")
    op.drop_column("farms", "visit_interval_days")


def downgrade() -> None:
    op.add_column(
        "farms",
        sa.Column("visit_interval_days", sa.Integer(), nullable=False, server_default="7"),
    )
    op.add_column("farms", sa.Column("visit_anchor_date", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_farms_visit_interval_positive", "farms", "visit_interval_days > 0"
    )
    op.execute(
        f"update farms set visit_interval_days = 5 where visit_weekdays = {MON_FRI}"
    )
    op.drop_constraint("ck_farms_visit_weekdays_valid", "farms", type_="check")
    op.drop_column("farms", "visit_weekdays")
