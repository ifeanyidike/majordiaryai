"""a self-registered account has no access until an admin activates it

Signup is open: anyone who completes Supabase auth may claim `technician`,
`farm` or `vet` (admin is refused). A fresh technician gets no herd data --
farm access is derived from assignments they do not have -- but they do get the
staff directory (GET /users/) and, until this round, the whole vet directory
with each vet's farm coverage. That is the customer list.

Restricting which role can be claimed does not fix it: whichever role remains
self-serve inherits the same problem, and there is no role a stranger should
hold on someone's herd management system by virtue of knowing the sign-up URL.

So the gate is activation, not role choice. A signed-up account exists and can
read its OWN profile -- enough for the app to say "waiting for approval" --
and nothing else until an admin turns it on from the People screen.

Existing rows are activated, so nobody currently signed in is locked out, and
the column defaults to true so admin-created and admin-edited accounts keep
working. Only the signup endpoint writes false.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
    )
    # Everyone who already has an account keeps it.
    op.execute("update users set is_active = true")
    # Pending accounts are what an admin looks for, and there are few of them.
    op.create_index(
        "ix_users_pending", "users", ["is_active"],
        postgresql_where=sa.text("is_active = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_pending", table_name="users")
    op.drop_column("users", "is_active")
