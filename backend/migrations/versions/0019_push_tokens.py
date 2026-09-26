"""push tokens, so an Alarm can wake a technician's phone

Alarms and Office Alerts were in-app only: a farm owner raising "the cow in
pen 4 is down" reached the technician whenever he next happened to open the
app. This stores each installation's Expo push address against the user
signed in on it.

The token is the primary key, not (user, token): a device belongs to whoever
signed in on it last. Re-registering moves it, so a phone handed to another
technician stops waking the first one.

RLS: a user may see and manage only their own tokens. The API writes these as
the database owner; the policy is the floor for anyone arriving through
PostgREST with the anon key that ships inside the app — without it, any
signed-in user could read every technician's push address and message them
directly.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_tokens",
        sa.Column("token", sa.String(), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_push_tokens_user_id", "push_tokens", ["user_id"])
    op.execute("alter table push_tokens enable row level security")
    op.execute("""create policy "push_tokens_own" on push_tokens for all
        using (user_id = auth.uid())
        with check (user_id = auth.uid())""")


def downgrade() -> None:
    op.execute('drop policy if exists "push_tokens_own" on push_tokens')
    op.drop_index("ix_push_tokens_user_id", table_name="push_tokens")
    op.drop_table("push_tokens")
