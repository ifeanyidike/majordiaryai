"""make the visit_weekdays constraint actually reject an empty schedule

0006 wrote:

    array_length(visit_weekdays, 1) between 1 and 7

array_length of an empty array is NULL, not 0, and `NULL between 1 and 7` is
NULL — which a CHECK constraint treats as passing. So the one state the
constraint existed to forbid ("this farm has no visit days") was accepted, and
the API's own validator was the only thing standing in the way.

cardinality() returns 0 for an empty array, so the same intent now holds.

Any existing empty rows are repaired to the Mon-Sat default first, otherwise
adding the constraint would fail against real data.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VALID = (
    "cardinality(visit_weekdays) between 1 and 7"
    " and visit_weekdays <@ '{0,1,2,3,4,5,6}'::smallint[]"
)
OLD = (
    "array_length(visit_weekdays, 1) between 1 and 7"
    " and visit_weekdays <@ '{0,1,2,3,4,5,6}'::smallint[]"
)


def upgrade() -> None:
    op.execute(
        "update farms set visit_weekdays = '{0,1,2,3,4,5}'::smallint[] "
        "where visit_weekdays is null or cardinality(visit_weekdays) = 0"
    )
    op.drop_constraint("ck_farms_visit_weekdays_valid", "farms", type_="check")
    op.create_check_constraint("ck_farms_visit_weekdays_valid", "farms", VALID)


def downgrade() -> None:
    op.drop_constraint("ck_farms_visit_weekdays_valid", "farms", type_="check")
    op.create_check_constraint("ck_farms_visit_weekdays_valid", "farms", OLD)
