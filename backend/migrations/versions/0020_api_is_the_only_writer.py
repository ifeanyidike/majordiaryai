"""the API is the only writer of messages and push tokens

Supabase grants `anon` and `authenticated` every privilege on every public
table, so row-level security is the only thing standing between the anon key
that ships inside the app and a direct write. 0015's policies were written as
if that were enough, and they were not:

  * messages_mark_read let a recipient UPDATE any column of a message in
    their inbox, not just read_at. A technician could rewrite an office
    alert's body, sender or channel -- and the administrator's outbox would
    then show the forged text as theirs.
  * messages_write let a farm manager INSERT an alarm claiming any farm_id,
    to any recipient -- the API's checks (own farm only, technicians only)
    apply only to requests that go through the API.

The app never touches either table through Supabase: every read and write is
an API call, and the API connects as the table owner, which these grants do
not affect. So the fix is not better policies but no path at all -- revoke the
write privileges and drop the policies that existed only to police them.
SELECT stays (policy-guarded) as defence in depth for the recipient's own
rows.

Guarded on the roles existing, so a bare Postgres without Supabase's roles
still migrates.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLES_EXIST = "exists (select 1 from pg_roles where rolname = 'authenticated')"


def upgrade() -> None:
    op.execute(f"""
        do $$ begin
          if {_ROLES_EXIST} then
            revoke insert, update, delete, truncate on messages from anon, authenticated;
            revoke all on push_tokens from anon, authenticated;
          end if;
        end $$
    """)
    op.execute('drop policy if exists "messages_write" on messages')
    op.execute('drop policy if exists "messages_mark_read" on messages')
    # push_tokens keeps RLS enabled with its policy; with no privileges the
    # policy is simply never reached.


def downgrade() -> None:
    op.execute(f"""
        do $$ begin
          if {_ROLES_EXIST} then
            grant insert, update, delete, truncate on messages to anon, authenticated;
            grant all on push_tokens to anon, authenticated;
          end if;
        end $$
    """)
    op.execute("""create policy "messages_write" on messages for insert
        with check (
            sender_id = auth.uid()
            and (
                (channel = 'alarm' and get_my_role() in ('farm', 'admin'))
                or (channel = 'office_alert'
                    and get_my_role() in ('admin', 'technician'))
            )
        )""")
    op.execute("""create policy "messages_mark_read" on messages for update
        using (recipient_id = auth.uid())
        with check (recipient_id = auth.uid())""")
