"""remember that a calving was assumed, so the real one can still be recorded

0017's companion change (the day-283 sweep) moves a dry cow to Fresh on her
due date because the client asked for it: "on 283 days, the status changes
from dry to fresh." Nobody has said she calved, so the sweep assumes the
calving date and deliberately does not count the lactation.

Nothing then let anyone record the REAL calving. The app offers "Record
Calving" only for pregnant and dry cows, and she is neither any more. So for
every cow that calved after her due date -- about half of them -- the
lactation stayed one short for good, the assumed date was never corrected,
and the calf was never created. The notification told the farm to "confirm
the calving"; there was no way to.

`calving_assumed` is the missing fact: true from the sweep's flip until a
calving is recorded. It is what puts "Record Calving" back on her and a
confirm row on the Fresh report.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cows", sa.Column(
        "calving_assumed", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("cows", "calving_assumed")
