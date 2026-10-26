"""The tag on her ear is the number shown; a heifer is never dried off

* cows.herd_id -- her ID in the farm's herd software (DairyComp's ID), kept
  when a herd list is imported. Josh: the app shows and searches the TAG, and
  the old ID must still find her. The ID, not the tag, is what is unique on a
  farm: real herds reuse tags (Josh's test herd has a cow and a heifer on tag
  9066, as real exports do), so the (farm_id, ear_tag) unique constraint
  becomes a plain index. Adding a cow in the app still refuses a
  tag already in use -- that check is in the API now, not the database.
* A heifer has never calved, however old she is (Josh), so she is not in milk
  and has nothing to dry off: no dry date, never Dry, no "stop milking"
  notice. She stays Pregnant until she calves. Heifers already holding a dry
  date lose it, and any the sweep already made Dry go back to Pregnant. On
  production at the time of writing that is 9 pregnant heifers and none Dry.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HEIFER = "lactation_number = 0 AND last_calving_date IS NULL"


def upgrade() -> None:
    op.add_column("cows", sa.Column("herd_id", sa.String(), nullable=True))
    op.create_unique_constraint("uq_cows_farm_id_herd_id", "cows", ["farm_id", "herd_id"])
    # Named by Postgres from 0001's inline `unique (farm_id, ear_tag)`.
    op.drop_constraint("cows_farm_id_ear_tag_key", "cows", type_="unique")
    op.create_index("ix_cows_farm_id_ear_tag", "cows", ["farm_id", "ear_tag"])

    op.execute(
        "UPDATE cows SET status = 'pregnant', dry_date = NULL, dry_off_confirmed_date = NULL "
        f"WHERE status = 'dry' AND {_HEIFER}"
    )
    op.execute(f"UPDATE cows SET dry_date = NULL WHERE status = 'pregnant' AND {_HEIFER}")


def downgrade() -> None:
    # Fails if a farm now has two animals on one tag; those have to be
    # retagged first. Heifers' dry dates are not put back.
    op.drop_index("ix_cows_farm_id_ear_tag", table_name="cows")
    op.create_unique_constraint("cows_farm_id_ear_tag_key", "cows", ["farm_id", "ear_tag"])
    op.drop_constraint("uq_cows_farm_id_herd_id", "cows", type_="unique")
    op.drop_column("cows", "herd_id")
