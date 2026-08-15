"""give the RLS helper the same 'today' and the same grace period as the API

0012 introduced `get_my_farm_ids()` with two seams that only a comment held
together:

  * it hardcoded 7 days, duplicating services/access.RELIEF_ACCESS_GRACE_DAYS;
  * it used `current_date`, which is the DATABASE's timezone (UTC on Supabase),
    while every date the API reasons about comes from local_today() in the farm
    timezone.

So for the hours between local midnight and UTC midnight the database and the
API disagreed about what day it is, and a relief technician's access could
expire a day early or linger a day late relative to the API's own answer.

Both values are now generated from the single source they belong to --
`settings.farm_timezone` and `RELIEF_ACCESS_GRACE_DAYS` -- and
tests/test_migrations.py asserts the deployed function still matches them, so a
change on the Python side cannot silently leave the database behind.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op

from app.core.config import settings
from app.services.access import RELIEF_ACCESS_GRACE_DAYS

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A single definition of "what day is it on the farm", for anything that
    # runs inside the database rather than in the API process.
    op.execute(f"""
        create or replace function public.farm_today()
        returns date
        language sql
        stable
        as $$ select (now() at time zone '{settings.farm_timezone}')::date $$
    """)

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
                f.assigned_technician_id = auth.uid()
             or f.id = (select u.farm_id from users u where u.id = auth.uid())
             or exists (
                    select 1 from farm_visit_assignments a
                    where a.farm_id = f.id
                      and a.assigned_technician_id = auth.uid()
                      and a.visit_date <= farm_today()
                      and a.visit_date >= farm_today()
                          - interval '{RELIEF_ACCESS_GRACE_DAYS} days'
                )
        $$
    """)


def downgrade() -> None:
    op.execute("""
        create or replace function public.get_my_farm_ids()
        returns setof uuid
        language sql
        stable
        security definer
        set search_path = public
        as $$
            select f.id from farms f
            where
                f.assigned_technician_id = auth.uid()
             or f.id = (select u.farm_id from users u where u.id = auth.uid())
             or exists (
                    select 1 from farm_visit_assignments a
                    where a.farm_id = f.id
                      and a.assigned_technician_id = auth.uid()
                      and a.visit_date <= current_date
                      and a.visit_date >= current_date - interval '7 days'
                )
        $$
    """)
    op.execute("drop function if exists public.farm_today()")
