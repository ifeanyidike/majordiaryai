"""One-time codes for saves sent from the phone (offline mode)

An outcome saved with no signal is sent when signal returns, and one whose
answer was lost is sent again. Each carries a one-time code; the code is
stored in the same transaction as the save, so a repeat is recognised and
not recorded twice. Only adds a table.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    # Server-only bookkeeping: on, with no policy, so the key that ships in
    # the app can neither read nor write it (the server owns the table).
    op.execute("alter table idempotency_keys enable row level security")


def downgrade() -> None:
    op.drop_table("idempotency_keys")
