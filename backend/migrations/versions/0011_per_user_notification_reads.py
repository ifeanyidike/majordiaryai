"""notification read state is per user, not per farm

`notifications.read` is a single boolean on a row that is addressed to a FARM.
Everyone who can see that farm -- the admin, the assigned technician, the farm
manager, the vet -- reads the same row, so whoever opened it first marked it
read for all of them. In practice the admin skimming the notification list
cleared the farm manager's unread badge for a dry-off they had not seen yet,
and `unread_only=true` returned nothing.

Read state belongs to the reader, so it moves to its own table. The old column
stays for now (dropping it is a separate, reversible step once nothing reads
it) but is no longer written.

Existing reads cannot be attributed to a person after the fact -- the old
column never recorded who -- so they are not migrated. Everyone starts with a
clean unread list once, which is the safe direction: a notification shown again
is noise, one hidden is a dry-off nobody was told about.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_reads",
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notification_id", "user_id"),
    )
    # The hot query is "which of these notifications has THIS user read".
    op.create_index("ix_notification_reads_user", "notification_reads", ["user_id"])

    # A read receipt is nobody else's business, and forging one only hides a
    # row from yourself -- so the policy is simply "your own rows".
    op.execute("alter table notification_reads enable row level security")
    op.execute(
        'create policy "notification_reads_own" on notification_reads '
        "for all using (user_id = auth.uid()) with check (user_id = auth.uid())"
    )


def downgrade() -> None:
    op.execute("drop policy if exists notification_reads_own on notification_reads")
    op.drop_index("ix_notification_reads_user", table_name="notification_reads")
    op.drop_table("notification_reads")
