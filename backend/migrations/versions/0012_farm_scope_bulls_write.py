"""scope bulls writes to the farms a technician actually covers

0009 enabled RLS on `bulls` and gated writes on the ROLE only:

    create policy "bulls_write" on bulls for all using (
        get_my_role() in ('admin', 'technician'))

routers/bulls.py is farm-scoped -- a technician may only touch bulls on a farm
they cover -- but PostgREST exposes the table directly with the anon key that
ships inside the app, and the database floor was wider than the API ceiling.
Any technician could rewrite any farm's semen list: retire the bull the farm
actually stocks, or add one it does not, on a herd they have never visited.

`get_my_farm_ids()` mirrors services/access.get_allowed_farm_ids, including the
relief technician's bounded visit window, so the two cannot drift apart
silently -- and it is SECURITY DEFINER for the same reason the existing helpers
are: the policy has to read `users` and `farms`, which the caller cannot.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in step with services/access.RELIEF_ACCESS_GRACE_DAYS.
RELIEF_GRACE_DAYS = 7


def upgrade() -> None:
    op.execute(f"""
        create or replace function public.get_my_farm_ids()
        returns setof uuid
        language sql
        stable
        security definer
        set search_path = public
        as $$
            select f.id from farms f
            where
                -- Admins and vets are not narrowed here; callers combine this
                -- with get_my_role() as they need.
                f.assigned_technician_id = auth.uid()
             or f.id = (select u.farm_id from users u where u.id = auth.uid())
             or exists (
                    select 1 from farm_visit_assignments a
                    where a.farm_id = f.id
                      and a.assigned_technician_id = auth.uid()
                      and a.visit_date <= current_date
                      and a.visit_date >= current_date - interval '{RELIEF_GRACE_DAYS} days'
                )
        $$
    """)

    op.execute('drop policy if exists "bulls_write" on bulls')
    op.execute("""create policy "bulls_write" on bulls for all
        using (
            get_my_role() = 'admin'
            or (get_my_role() = 'technician' and farm_id in (select get_my_farm_ids()))
        )
        with check (
            get_my_role() = 'admin'
            or (get_my_role() = 'technician' and farm_id in (select get_my_farm_ids()))
        )""")


def downgrade() -> None:
    op.execute('drop policy if exists "bulls_write" on bulls')
    op.execute("""create policy "bulls_write" on bulls for all using (
        get_my_role() in ('admin', 'technician')
    )""")
    op.execute("drop function if exists public.get_my_farm_ids()")
