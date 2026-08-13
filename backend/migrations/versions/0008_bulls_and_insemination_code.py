"""per-farm bull list, bull link on inseminations, and the Insemination Code

Two spec items that had no home in the schema:

  Bull Selection (Status & Report) — the technician picks the bull the farmer
  chose. It was free text, so the same bull was spelled differently by every
  technician and per-bull conception rate could never be computed.

  Insemination Code (Programs.md) — listed as a field with no format given.

ASSUMPTIONS (unanswered by the specs, flagged for the client):
  · bulls are PER FARM, because the spec says semen is "selected by farmer" and
    lists inventory tracking as a future enhancement. A global stud catalogue
    would be a different table shape.
  · insemination_code is FREE TEXT.

bull_name stays: it is what was actually recorded, keeps existing history
intact, and lets a technician enter a straw that is not on the list rather than
being blocked mid-visit.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bulls",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("farm_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=True),
        # Reuse the enum created in 0001. It must be the postgresql ENUM with
        # create_type=False — sa.Enum ignores that flag and re-issues CREATE
        # TYPE, which fails because the type already exists.
        sa.Column("semen_type",
                  postgresql.ENUM("sexed", "conventional", "beef",
                                  name="semen_type", create_type=False),
                  nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["farm_id"], ["farms.id"], ondelete="CASCADE"),
        # One entry per bull per farm; two farms may stock the same bull.
        sa.UniqueConstraint("farm_id", "name", name="uq_bulls_farm_name"),
    )
    op.create_index("ix_bulls_farm_active", "bulls", ["farm_id", "active"])

    op.add_column(
        "inseminations",
        sa.Column("bull_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_inseminations_bull", "inseminations", "bulls", ["bull_id"], ["id"]
    )
    op.add_column("inseminations", sa.Column("insemination_code", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("inseminations", "insemination_code")
    op.drop_constraint("fk_inseminations_bull", "inseminations", type_="foreignkey")
    op.drop_column("inseminations", "bull_id")
    op.drop_index("ix_bulls_farm_active", table_name="bulls")
    op.drop_table("bulls")
