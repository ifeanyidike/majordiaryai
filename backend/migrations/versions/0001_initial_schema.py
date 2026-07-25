"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-07-23
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('create extension if not exists "uuid-ossp"')

    # ENUMS
    op.execute("create type user_role as enum ('admin', 'technician', 'farm', 'vet')")
    op.execute("""create type cow_status as enum (
        'calf', 'heifer', 'fresh', 'open', 'needling',
        'inseminated', 'pregnant', 'dry', 'cull', 'sold', 'dead'
    )""")
    op.execute("create type semen_type as enum ('sexed', 'conventional', 'beef')")
    op.execute("""create type protocol_type as enum (
        'ovsynch', 'prostaglandin_heat', 'double_ovsynch',
        'presynch', 'general_synch', 'general_synch_2'
    )""")
    op.execute("create type enrollment_status as enum ('active', 'completed', 'cancelled')")
    op.execute("create type pregnancy_result as enum ('pregnant', 'not_pregnant')")
    op.execute("create type calf_sex as enum ('male', 'female')")
    op.execute("create type visit_type as enum ('pregnancy_check', 'consultation')")

    # USERS
    op.execute("""create table users (
        id uuid primary key references auth.users(id) on delete cascade,
        name text not null,
        email text not null,
        role user_role not null,
        phone text,
        employee_id text,
        region text,
        farm_id uuid,
        created_at timestamptz default now()
    )""")

    # FARMS
    op.execute("""create table farms (
        id uuid primary key default uuid_generate_v4(),
        name text not null,
        owner_name text not null,
        address text,
        city text,
        province text,
        postal_code text,
        phone text,
        email text,
        herd_size int default 0,
        assigned_technician_id uuid references users(id),
        notes text,
        created_at timestamptz default now()
    )""")

    op.execute("""alter table users
        add constraint fk_users_farm foreign key (farm_id) references farms(id)""")

    # VETS
    op.execute("""create table vets (
        id uuid primary key default uuid_generate_v4(),
        user_id uuid references users(id) on delete cascade,
        name text not null,
        clinic text,
        phone text,
        email text,
        created_at timestamptz default now()
    )""")

    op.execute("""create table vet_farm_assignments (
        vet_id uuid references vets(id) on delete cascade,
        farm_id uuid references farms(id) on delete cascade,
        primary key (vet_id, farm_id)
    )""")

    # COWS
    op.execute("""create table cows (
        id uuid primary key default uuid_generate_v4(),
        ear_tag text not null,
        farm_id uuid not null references farms(id) on delete cascade,
        breed text,
        date_of_birth date,
        sex calf_sex not null default 'female',
        lactation_number int default 0,
        status cow_status not null default 'calf',
        current_program text,
        last_calving_date date,
        last_insemination_date date,
        last_insemination_id uuid,
        due_date date,
        dry_date date,
        notes text,
        created_at timestamptz default now(),
        unique (farm_id, ear_tag)
    )""")

    # INSEMINATIONS
    op.execute("""create table inseminations (
        id uuid primary key default uuid_generate_v4(),
        cow_id uuid not null references cows(id) on delete cascade,
        date date not null,
        bull_name text,
        dose_id text,
        semen_type semen_type,
        technician_id uuid references users(id),
        attempt_number int default 1,
        notes text,
        created_at timestamptz default now()
    )""")

    op.execute("""alter table cows
        add constraint fk_last_insemination
        foreign key (last_insemination_id) references inseminations(id)""")

    # NEEDLING
    op.execute("""create table needling_enrollments (
        id uuid primary key default uuid_generate_v4(),
        cow_id uuid not null references cows(id) on delete cascade,
        protocol protocol_type not null,
        start_date date not null,
        current_day int default 1,
        status enrollment_status default 'active',
        created_at timestamptz default now()
    )""")

    op.execute("""create table needling_records (
        id uuid primary key default uuid_generate_v4(),
        enrollment_id uuid not null references needling_enrollments(id) on delete cascade,
        cow_id uuid not null references cows(id) on delete cascade,
        protocol_day int not null,
        scheduled_date date not null,
        completed_date date,
        treatment text not null,
        completed boolean default false,
        bleeding_event boolean default false,
        technician_id uuid references users(id),
        notes text,
        created_at timestamptz default now()
    )""")

    # HEAT CHECKS
    op.execute("""create table heat_checks (
        id uuid primary key default uuid_generate_v4(),
        cow_id uuid not null references cows(id) on delete cascade,
        insemination_id uuid not null references inseminations(id) on delete cascade,
        check_date date not null,
        days_since_insemination int not null,
        heat_detected boolean,
        bleeding_event boolean default false,
        technician_id uuid references users(id),
        notes text,
        created_at timestamptz default now()
    )""")

    # PREGNANCY CHECKS
    op.execute("""create table pregnancy_checks (
        id uuid primary key default uuid_generate_v4(),
        cow_id uuid not null references cows(id) on delete cascade,
        insemination_id uuid not null references inseminations(id) on delete cascade,
        check_date date not null,
        vet_id uuid references users(id),
        result pregnancy_result,
        has_infection boolean default false,
        has_cysts boolean default false,
        notes text,
        created_at timestamptz default now()
    )""")

    # CALVING
    op.execute("""create table calving_records (
        id uuid primary key default uuid_generate_v4(),
        cow_id uuid not null references cows(id) on delete cascade,
        calving_date date not null,
        live_birth boolean default true,
        still_birth boolean default false,
        calf_sex calf_sex,
        calf_ear_tag text,
        calf_id uuid references cows(id),
        technician_id uuid references users(id),
        notes text,
        created_at timestamptz default now()
    )""")

    # VACCINATION
    op.execute("""create table vaccination_records (
        id uuid primary key default uuid_generate_v4(),
        cow_id uuid not null references cows(id) on delete cascade,
        calving_record_id uuid references calving_records(id),
        scheduled_date date not null,
        completed_date date,
        vaccine_name text,
        lot_number text,
        technician_id uuid references users(id),
        completed boolean default false,
        notes text,
        created_at timestamptz default now()
    )""")

    # CULL
    op.execute("""create table cull_records (
        id uuid primary key default uuid_generate_v4(),
        cow_id uuid not null references cows(id) on delete cascade,
        cull_date date not null,
        reason text,
        technician_id uuid references users(id),
        notes text,
        created_at timestamptz default now()
    )""")

    # VET VISITS
    op.execute("""create table vet_visit_schedules (
        id uuid primary key default uuid_generate_v4(),
        farm_id uuid not null references farms(id) on delete cascade,
        vet_id uuid references users(id),
        scheduled_date date not null,
        visit_type visit_type not null default 'pregnancy_check',
        completed boolean default false,
        notes text,
        created_at timestamptz default now()
    )""")

    # INDEXES
    op.execute("create index idx_cows_farm_id on cows(farm_id)")
    op.execute("create index idx_cows_status on cows(status)")
    op.execute("create index idx_cows_last_insemination_date on cows(last_insemination_date)")
    op.execute("create index idx_cows_due_date on cows(due_date)")
    op.execute("create index idx_cows_dry_date on cows(dry_date)")
    op.execute("create index idx_cows_last_calving_date on cows(last_calving_date)")
    op.execute("create index idx_inseminations_cow_id on inseminations(cow_id)")
    op.execute("create index idx_inseminations_date on inseminations(date)")
    op.execute("create index idx_needling_records_scheduled_date on needling_records(scheduled_date)")
    op.execute("create index idx_needling_records_cow_id on needling_records(cow_id)")
    op.execute("create index idx_heat_checks_cow_id on heat_checks(cow_id)")
    op.execute("create index idx_heat_checks_check_date on heat_checks(check_date)")
    op.execute("create index idx_pregnancy_checks_cow_id on pregnancy_checks(cow_id)")
    op.execute("create index idx_calving_records_cow_id on calving_records(cow_id)")
    op.execute("create index idx_vaccination_records_scheduled_date on vaccination_records(scheduled_date)")
    op.execute("create index idx_vet_visit_schedules_scheduled_date on vet_visit_schedules(scheduled_date)")

    # RLS
    for table in [
        "users", "farms", "vets", "vet_farm_assignments", "cows",
        "inseminations", "needling_enrollments", "needling_records",
        "heat_checks", "pregnancy_checks", "calving_records",
        "vaccination_records", "cull_records", "vet_visit_schedules",
    ]:
        op.execute(f"alter table {table} enable row level security")

    op.execute("""create or replace function get_my_role()
        returns user_role as $$
            select role from users where id = auth.uid();
        $$ language sql security definer""")

    op.execute("""create or replace function get_my_farm_id()
        returns uuid as $$
            select farm_id from users where id = auth.uid();
        $$ language sql security definer""")

    op.execute('create policy "users_read_own" on users for select using (id = auth.uid() or get_my_role() = \'admin\')')
    op.execute('create policy "users_update_own" on users for update using (id = auth.uid())')
    op.execute("""create policy "farms_read" on farms for select using (
        get_my_role() in ('admin', 'technician', 'vet') or id = get_my_farm_id()
    )""")
    op.execute('create policy "farms_write" on farms for all using (get_my_role() = \'admin\')')
    op.execute("""create policy "cows_read" on cows for select using (
        get_my_role() in ('admin', 'technician')
        or farm_id = get_my_farm_id()
        or farm_id in (select farm_id from vet_farm_assignments where vet_id = (select id from vets where user_id = auth.uid()))
    )""")
    op.execute("create policy \"cows_write\" on cows for all using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"inseminations_read\" on inseminations for select using (get_my_role() in ('admin', 'technician', 'vet'))")
    op.execute("create policy \"inseminations_write\" on inseminations for all using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"pregnancy_checks_read\" on pregnancy_checks for select using (get_my_role() in ('admin', 'technician', 'vet'))")
    op.execute("create policy \"pregnancy_checks_write\" on pregnancy_checks for all using (get_my_role() in ('admin', 'technician', 'vet'))")
    op.execute("create policy \"needling_read\" on needling_enrollments for select using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"needling_write\" on needling_enrollments for all using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"needling_records_read\" on needling_records for select using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"needling_records_write\" on needling_records for all using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"heat_checks_read\" on heat_checks for select using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"heat_checks_write\" on heat_checks for all using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"calving_records_read\" on calving_records for select using (get_my_role() in ('admin', 'technician', 'farm'))")
    op.execute("create policy \"calving_records_write\" on calving_records for all using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"vaccination_records_read\" on vaccination_records for select using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"vaccination_records_write\" on vaccination_records for all using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"cull_records_read\" on cull_records for select using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"cull_records_write\" on cull_records for all using (get_my_role() in ('admin', 'technician'))")
    op.execute("create policy \"vet_visits_read\" on vet_visit_schedules for select using (get_my_role() in ('admin', 'technician', 'vet'))")
    op.execute("create policy \"vet_visits_write\" on vet_visit_schedules for all using (get_my_role() in ('admin', 'technician', 'vet'))")
    op.execute("create policy \"vets_read\" on vets for select using (get_my_role() in ('admin', 'technician', 'vet', 'farm'))")
    op.execute("create policy \"vet_assignments_read\" on vet_farm_assignments for select using (get_my_role() in ('admin', 'technician', 'vet', 'farm'))")


def downgrade() -> None:
    for policy, table in [
        ("users_read_own", "users"), ("users_update_own", "users"),
        ("farms_read", "farms"), ("farms_write", "farms"),
        ("cows_read", "cows"), ("cows_write", "cows"),
        ("inseminations_read", "inseminations"), ("inseminations_write", "inseminations"),
        ("pregnancy_checks_read", "pregnancy_checks"), ("pregnancy_checks_write", "pregnancy_checks"),
        ("needling_read", "needling_enrollments"), ("needling_write", "needling_enrollments"),
        ("needling_records_read", "needling_records"), ("needling_records_write", "needling_records"),
        ("heat_checks_read", "heat_checks"), ("heat_checks_write", "heat_checks"),
        ("calving_records_read", "calving_records"), ("calving_records_write", "calving_records"),
        ("vaccination_records_read", "vaccination_records"), ("vaccination_records_write", "vaccination_records"),
        ("cull_records_read", "cull_records"), ("cull_records_write", "cull_records"),
        ("vet_visits_read", "vet_visit_schedules"), ("vet_visits_write", "vet_visit_schedules"),
        ("vets_read", "vets"), ("vet_assignments_read", "vet_farm_assignments"),
    ]:
        op.execute(f'drop policy if exists "{policy}" on {table}')

    op.execute("drop function if exists get_my_role()")
    op.execute("drop function if exists get_my_farm_id()")

    for table in [
        "vet_visit_schedules", "cull_records", "vaccination_records",
        "calving_records", "pregnancy_checks", "heat_checks",
        "needling_records", "needling_enrollments", "inseminations",
        "cows", "vet_farm_assignments", "vets", "farms", "users",
    ]:
        op.execute(f"drop table if exists {table} cascade")

    for t in [
        "visit_type", "calf_sex", "pregnancy_result", "enrollment_status",
        "protocol_type", "semen_type", "cow_status", "user_role",
    ]:
        op.execute(f"drop type if exists {t}")
