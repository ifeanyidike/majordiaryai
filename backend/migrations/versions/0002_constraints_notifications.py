"""constraints, notifications table, new columns and indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-24
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum extension ────────────────────────────────────────
    # Final (AI-day) needling record completed; cow awaits insemination.
    op.execute("alter type enrollment_status add value if not exists 'completed_pending_ai' before 'completed'")

    # ── New columns ───────────────────────────────────────────
    op.execute("alter table cows add column exit_date date")
    op.execute("alter table cows add column exit_reason text")
    op.execute("alter table inseminations add column inseminated_at timestamptz")
    op.execute("alter table needling_records add column is_final boolean not null default false")
    op.execute("alter table pregnancy_checks add column performed_by_id uuid references users(id)")
    op.execute("alter table calving_records add column calf_sale_info text")
    op.execute("alter table vaccination_records add column administered_at timestamptz")

    # ── Constraints ───────────────────────────────────────────
    op.execute("alter table users add constraint users_email_key unique (email)")
    op.execute("""alter table cows
        add constraint ck_cows_lactation_number_non_negative check (lactation_number >= 0)""")
    op.execute("""alter table farms
        add constraint ck_farms_herd_size_non_negative check (herd_size >= 0)""")
    op.execute("""alter table calving_records
        add constraint ck_calving_live_still_exclusive check (live_birth <> still_birth)""")
    op.execute("""alter table needling_records
        add constraint ck_needling_records_day_positive check (protocol_day > 0)""")

    # ── Missing indexes ───────────────────────────────────────
    op.execute("create index idx_needling_records_enrollment_id on needling_records(enrollment_id)")
    op.execute("create index idx_vaccination_records_cow_id on vaccination_records(cow_id)")
    op.execute("create index idx_heat_checks_insemination_id on heat_checks(insemination_id)")
    op.execute("create index idx_pregnancy_checks_insemination_id on pregnancy_checks(insemination_id)")
    op.execute("create index idx_pregnancy_checks_check_date on pregnancy_checks(check_date)")
    op.execute("create index idx_users_farm_id on users(farm_id)")
    op.execute("create index idx_farms_assigned_technician_id on farms(assigned_technician_id)")
    op.execute("create index idx_needling_enrollments_cow_id on needling_enrollments(cow_id)")
    op.execute("create index idx_cull_records_cow_id on cull_records(cow_id)")

    # ── Notifications ─────────────────────────────────────────
    op.execute("""create table notifications (
        id uuid primary key default uuid_generate_v4(),
        farm_id uuid not null references farms(id) on delete cascade,
        cow_id uuid references cows(id) on delete set null,
        type text not null,
        message text not null,
        read boolean not null default false,
        created_at timestamptz default now()
    )""")
    op.execute("create index idx_notifications_farm_id on notifications(farm_id)")
    op.execute("create index idx_notifications_created_at on notifications(created_at)")

    op.execute("alter table notifications enable row level security")
    op.execute("""create policy "notifications_read" on notifications
        for select using (
            get_my_role() in ('admin', 'technician', 'vet')
            or farm_id = get_my_farm_id()
        )""")
    op.execute("""create policy "notifications_write" on notifications
        for all using (get_my_role() in ('admin', 'technician'))""")


def downgrade() -> None:
    op.execute('drop policy if exists "notifications_read" on notifications')
    op.execute('drop policy if exists "notifications_write" on notifications')
    op.execute("drop table if exists notifications cascade")

    op.execute("drop index if exists idx_cull_records_cow_id")
    op.execute("drop index if exists idx_needling_enrollments_cow_id")
    op.execute("drop index if exists idx_farms_assigned_technician_id")
    op.execute("drop index if exists idx_users_farm_id")
    op.execute("drop index if exists idx_pregnancy_checks_check_date")
    op.execute("drop index if exists idx_pregnancy_checks_insemination_id")
    op.execute("drop index if exists idx_heat_checks_insemination_id")
    op.execute("drop index if exists idx_vaccination_records_cow_id")
    op.execute("drop index if exists idx_needling_records_enrollment_id")

    op.execute("alter table needling_records drop constraint if exists ck_needling_records_day_positive")
    op.execute("alter table calving_records drop constraint if exists ck_calving_live_still_exclusive")
    op.execute("alter table farms drop constraint if exists ck_farms_herd_size_non_negative")
    op.execute("alter table cows drop constraint if exists ck_cows_lactation_number_non_negative")
    op.execute("alter table users drop constraint if exists users_email_key")

    op.execute("alter table vaccination_records drop column if exists administered_at")
    op.execute("alter table calving_records drop column if exists calf_sale_info")
    op.execute("alter table pregnancy_checks drop column if exists performed_by_id")
    op.execute("alter table needling_records drop column if exists is_final")
    op.execute("alter table inseminations drop column if exists inseminated_at")
    op.execute("alter table cows drop column if exists exit_reason")
    op.execute("alter table cows drop column if exists exit_date")
    # Note: PostgreSQL cannot remove a value from an enum type; the
    # 'completed_pending_ai' value is left in place on downgrade.
