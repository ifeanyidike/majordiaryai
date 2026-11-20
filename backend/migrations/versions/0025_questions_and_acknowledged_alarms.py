"""Notices that ask a question; alarms that are acknowledged; notes

Josh's change requests (Nov 20): the farm answers "Moved to dry pen? Yes / No"
on Day 223, and the technician "Has she given birth? Yes / No" on Day 293, so a
notice carries its answer. A technician acknowledges an alarm, which then
leaves their list, and a farm can send a note as well as an alarm.

Only adds columns, with defaults, so the build still live keeps working.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("answer", sa.String(), nullable=True))
    op.add_column("notifications", sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notifications", sa.Column(
        "answered_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("messages", sa.Column(
        "kind", sa.String(), nullable=False, server_default=sa.text("'alarm'")))
    op.add_column("messages", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "acknowledged_at")
    op.drop_column("messages", "kind")
    op.drop_column("notifications", "answered_by_id")
    op.drop_column("notifications", "answered_at")
    op.drop_column("notifications", "answer")
