"""let a route hand-off raise its own office alert

0015 wrote the Office Alerts insert policy as "admins only", matching
routers/messages.py where posting one BY HAND is an administrator's job.

But route-change alerts are not posted by hand. They are raised automatically
by whoever made the change, and `PUT/DELETE /farms/{id}/visit-assignments`
deliberately allows the farm's STANDING TECHNICIAN to hand their own day to a
relief -- so the sender of that alert is a technician, and the policy forbade
exactly the row the application creates.

Nothing broke at runtime: the API connects as the database owner, which
bypasses RLS. That is the problem. The policy is meant to be the floor under
the API for anyone arriving through PostgREST with the anon key that ships
inside the app, and a floor that contradicts the application above it is not
a floor -- it is a trap waiting for the first person who moves this table
behind PostgREST.

Manual posting stays narrower than the policy: SENDER_ROLES in
routers/messages.py still refuses an office alert from anyone but an admin.
Widening here only admits the automatic case the app already performs.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('drop policy if exists "messages_write" on messages')
    op.execute("""create policy "messages_write" on messages for insert
        with check (
            sender_id = auth.uid()
            and (
                (channel = 'alarm' and get_my_role() in ('farm', 'admin'))
                -- A technician reaches this channel only through a route
                -- change they are entitled to make; the API keeps hand-written
                -- office alerts to admins.
                or (channel = 'office_alert'
                    and get_my_role() in ('admin', 'technician'))
            )
        )""")


def downgrade() -> None:
    op.execute('drop policy if exists "messages_write" on messages')
    op.execute("""create policy "messages_write" on messages for insert
        with check (
            sender_id = auth.uid()
            and (
                (channel = 'alarm' and get_my_role() in ('farm', 'admin'))
                or (channel = 'office_alert' and get_my_role() = 'admin')
            )
        )""")
