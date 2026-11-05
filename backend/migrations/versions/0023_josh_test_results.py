"""Josh's test results (Nov 5): a DNB status, and what the new forms store

* cow_status gains 'dnb'. Do Not Breed becomes a status of its own; the mark
  on her record (cows.do_not_breed) stays, and says when she goes there.
* heat_checks.breed_anyway -- the farmer overruled the 60-day rule on this
  heat. Today's Breed Report re-applies the rule on every load, so the answer
  has to be kept.
* pregnancy_checks.infection_detail -- which infection, for the Infections
  tab on her history.
* Do Not Inseminate is removed: Do Not Breed replaces it, so a cow marked only
  Do Not Inseminate becomes Do Not Breed here. On production at the time of
  writing that is nobody -- one test heifer has it, and she has both.

Additive on purpose. Railway runs this BEFORE the new build takes traffic, and
the build that is live keeps running if the new one fails its health check:

* cows.do_not_inseminate stays, unused, until the next release drops it. The
  old build selects every column it knows, so dropping it now would turn a
  failed deploy into every cow query failing.
* No cow is moved to 'dnb' here, for the same reason: the old build cannot
  read that value. The new build's sweep does it, the moment it starts
  (status_engine.settle_do_not_breed).

ADD VALUE runs in its own autocommit block: a new enum value cannot be used in
the transaction that adds it, and this keeps that true of any later migration
in the same run.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE cow_status ADD VALUE IF NOT EXISTS 'dnb' AFTER 'dry'")

    op.add_column("heat_checks", sa.Column(
        "breed_anyway", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("pregnancy_checks", sa.Column("infection_detail", sa.String(), nullable=True))
    op.execute("UPDATE cows SET do_not_breed = true WHERE do_not_inseminate")


def downgrade() -> None:
    # Postgres cannot drop an enum value, so 'dnb' stays in the type; no cow
    # may keep it, because the code this goes back to cannot read it.
    op.execute("UPDATE cows SET status = 'open', current_program = NULL WHERE status = 'dnb'")
    op.drop_column("pregnancy_checks", "infection_detail")
    op.drop_column("heat_checks", "breed_anyway")
