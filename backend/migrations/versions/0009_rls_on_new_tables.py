"""enable RLS on bulls and farm_visit_assignments

SECURITY FIX. Every table from 0001 has row level security; the two tables
added later (0005 farm_visit_assignments, 0008 bulls) were created without it,
so they were reachable directly through PostgREST with the anon key that ships
inside the mobile app.

farm_visit_assignments is the serious one. services/access.py grants a
technician access to any farm they have a visit assignment for, so a direct
INSERT naming yourself converted into full API access to that farm's herd —
the exact self-granting loop the API layer refuses, wide open underneath it.

The write policy here is deliberately STRICTER than the API: only admins may
write visit assignments directly. The API additionally lets a farm's standing
technician hand over their own day, but that check needs the farm row, which is
awkward to express in a policy and easy to get subtly wrong. Direct writes are
not a path anyone should be using, so the narrow rule is the safe one.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("bulls", "farm_visit_assignments"):
        op.execute(f"alter table {table} enable row level security")

    # Bulls: anyone who can see the farm can see what semen it stocks; only
    # admin/technician change it, matching routers/bulls.py.
    op.execute("""create policy "bulls_read" on bulls for select using (
        get_my_role() in ('admin', 'technician', 'vet')
        or farm_id = get_my_farm_id()
    )""")
    op.execute("""create policy "bulls_write" on bulls for all using (
        get_my_role() in ('admin', 'technician')
    )""")

    # Visit assignments: readable by staff and by the farm they concern.
    op.execute("""create policy "farm_visit_assignments_read"
        on farm_visit_assignments for select using (
            get_my_role() in ('admin', 'technician', 'vet')
            or farm_id = get_my_farm_id()
        )""")
    # Writes: admin only — see the module docstring.
    op.execute("""create policy "farm_visit_assignments_write"
        on farm_visit_assignments for all using (get_my_role() = 'admin')""")


def downgrade() -> None:
    for policy, table in (
        ("bulls_read", "bulls"),
        ("bulls_write", "bulls"),
        ("farm_visit_assignments_read", "farm_visit_assignments"),
        ("farm_visit_assignments_write", "farm_visit_assignments"),
    ):
        op.execute(f'drop policy if exists "{policy}" on {table}')
    for table in ("bulls", "farm_visit_assignments"):
        op.execute(f"alter table {table} disable row level security")
