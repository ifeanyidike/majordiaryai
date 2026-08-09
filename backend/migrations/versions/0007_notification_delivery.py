"""record whether a notification's email actually reached the farmer

Sending was fire-and-forget: a rejected or dropped message was logged and
forgotten, so nothing could answer "was the farmer told to move this cow?".
That matters precisely when it is disputed. Records the outcome on the row.

email_status values:
  sent      — SendGrid accepted it (2xx)
  failed    — SendGrid rejected it, or the request errored
  no_email  — the farm has no email address on file
  disabled  — SENDGRID_API_KEY is unset, so sending is off

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("email_status", sa.String(), nullable=True))
    op.add_column(
        "notifications",
        sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("notifications", sa.Column("email_error", sa.String(), nullable=True))
    # "Which notifications failed to reach anyone?" is the query this exists for.
    op.create_index(
        "ix_notifications_email_status", "notifications", ["email_status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_email_status", table_name="notifications")
    op.drop_column("notifications", "email_error")
    op.drop_column("notifications", "emailed_at")
    op.drop_column("notifications", "email_status")
