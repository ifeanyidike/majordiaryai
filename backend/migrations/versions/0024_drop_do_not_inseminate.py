"""Do Not Inseminate is gone

Josh's test results (Nov 5): "Remove it completely (DNB replaces it)". Migration
0023 merged it into Do Not Breed and left the column, because the build that was
live then still selected it, and a failed deploy would have left that build
running on a table without it. The build that replaced it does not read the
column, so it can go.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("cows", "do_not_inseminate")


def downgrade() -> None:
    op.add_column("cows", sa.Column(
        "do_not_inseminate", sa.Boolean(), nullable=False, server_default=sa.text("false")))
