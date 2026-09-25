"""a cow may be identified by her tag OR her name

On the call: "put an additional option for name ... some places will have
both, some places will have one." Asked directly whether both fields could be
optional, the client said yes -- so a cow can exist on a name alone.

`ear_tag` therefore becomes nullable, and a CHECK takes over the job it was
doing implicitly: she must carry at least ONE identifier. An animal with
neither is not a record of anything.

The (farm_id, ear_tag) unique constraint stays exactly as it is. Postgres
treats NULLs as distinct in a unique index, so any number of unnamed-tag cows
coexist on a farm while two cows still cannot share a real tag -- which is the
property worth keeping.

Names are deliberately NOT made unique. Farms reuse them across generations
("Bluebell" again, two lactations later) and blocking that would be the app
telling a farmer what to call his cows.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("cows", "ear_tag", existing_type=sa.String(), nullable=True)
    op.create_check_constraint(
        "ck_cows_has_an_identifier",
        "cows",
        "ear_tag IS NOT NULL OR name IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_cows_has_an_identifier", "cows", type_="check")
    # Anything created name-only since the upgrade has no tag to go back to;
    # borrow the name so the NOT NULL can be restored rather than failing.
    op.execute("update cows set ear_tag = name where ear_tag is null")
    op.alter_column("cows", "ear_tag", existing_type=sa.String(), nullable=False)
