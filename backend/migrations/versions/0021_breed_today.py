"""Josh's Oct 2 / Oct 4 changes: parentage, the breeding lists, any-time heat

* cows.sire / cows.maternal_sire -- parentage on her personal info.
* cows.do_not_breed / cows.do_not_inseminate -- a cow on either list who is
  seen in heat is not put on Today's Breed Report. The demo data already said
  "Do Not Breed" as free text in current_program; that becomes the flag.
* heat_checks.insemination_id / days_since_insemination become nullable: a
  heat can now be recorded on a cow that is not inseminated (an open cow, one
  mid-protocol), and there is no insemination to measure it from.
* Cows a detected heat parked in the Insemination Program. Under the old rule
  they stayed there, "returned for breeding", until someone bred them. Josh's
  rule is that a cow in heat is bred that day or not at all: if she is not
  bred by the next day she "goes back to the Open Cow Report and program --
  assume nothing happened". Every such cow's heat is already in the past, so
  she moves to the Open Cow Report now. Heifers that reached breeding age
  (never inseminated) are a different route into the same program and stay.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cows", sa.Column("sire", sa.String(), nullable=True))
    op.add_column("cows", sa.Column("maternal_sire", sa.String(), nullable=True))
    op.add_column("cows", sa.Column(
        "do_not_breed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("cows", sa.Column(
        "do_not_inseminate", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.execute("UPDATE cows SET do_not_breed = true WHERE current_program = 'Do Not Breed'")

    op.alter_column("heat_checks", "insemination_id", nullable=True)
    op.alter_column("heat_checks", "days_since_insemination", nullable=True)

    op.execute(
        "UPDATE cows SET current_program = NULL "
        "WHERE status = 'open' AND current_program = 'Insemination' "
        "AND last_insemination_date IS NOT NULL"
    )


def downgrade() -> None:
    # Heats recorded without an insemination cannot satisfy NOT NULL again.
    op.execute("DELETE FROM heat_checks WHERE insemination_id IS NULL")
    op.alter_column("heat_checks", "days_since_insemination", nullable=False)
    op.alter_column("heat_checks", "insemination_id", nullable=False)
    op.drop_column("cows", "do_not_inseminate")
    op.drop_column("cows", "do_not_breed")
    op.drop_column("cows", "maternal_sire")
    op.drop_column("cows", "sire")
