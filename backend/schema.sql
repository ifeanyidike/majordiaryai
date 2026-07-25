-- ============================================================
-- Major Dairy AI — Full Database Schema
-- Run this in Supabase SQL Editor
-- ============================================================

-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- ============================================================
-- ENUMS
-- ============================================================

create type user_role as enum ('admin', 'technician', 'farm', 'vet');

create type cow_status as enum (
  'calf', 'heifer', 'fresh', 'open', 'needling',
  'inseminated', 'pregnant', 'dry', 'cull', 'sold', 'dead'
);

create type semen_type as enum ('sexed', 'conventional', 'beef');

create type protocol_type as enum (
  'ovsynch', 'prostaglandin_heat', 'double_ovsynch',
  'presynch', 'general_synch', 'general_synch_2'
);

create type enrollment_status as enum ('active', 'completed_pending_ai', 'completed', 'cancelled');

create type pregnancy_result as enum ('pregnant', 'not_pregnant');

create type calf_sex as enum ('male', 'female');


create type health_status as enum ('healthy', 'sick');

-- ============================================================
-- USERS (extends Supabase Auth)
-- ============================================================

create table users (
  id uuid primary key references auth.users(id) on delete cascade,
  name text not null,
  email text not null unique,
  role user_role not null,
  phone text,
  employee_id text,
  region text,
  farm_id uuid,  -- only set for users with role='farm'
  created_at timestamptz default now()
);

-- ============================================================
-- FARMS
-- ============================================================

create table farms (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  owner_name text not null,
  address text,
  city text,
  province text,
  postal_code text,
  phone text,
  email text,
  herd_size int default 0 constraint ck_farms_herd_size_non_negative check (herd_size >= 0),
  assigned_technician_id uuid references users(id),
  notes text,
  created_at timestamptz default now()
);

-- Link farm-role users to their farm
alter table users
  add constraint fk_users_farm
  foreign key (farm_id)
  references farms(id);

-- ============================================================
-- VETS
-- ============================================================

create table vets (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  name text not null,
  clinic text,
  phone text,
  email text,
  created_at timestamptz default now()
);

create table vet_farm_assignments (
  vet_id uuid references vets(id) on delete cascade,
  farm_id uuid references farms(id) on delete cascade,
  primary key (vet_id, farm_id)
);

-- ============================================================
-- COWS
-- ============================================================

create table cows (
  id uuid primary key default uuid_generate_v4(),
  ear_tag text not null,
  farm_id uuid not null references farms(id) on delete cascade,
  breed text,
  date_of_birth date,
  sex calf_sex not null default 'female',
  lactation_number int default 0 constraint ck_cows_lactation_number_non_negative check (lactation_number >= 0),
  status cow_status not null default 'calf',
  health_status health_status default 'healthy',
  recheck_due_date date,   -- set to today+7 when marked sick; cleared when healthy
  current_program text,
  last_calving_date date,
  last_insemination_date date,
  last_insemination_id uuid,
  due_date date,
  dry_date date,
  exit_date date,        -- set when the cow leaves the herd (sold / dead)
  exit_reason text,
  notes text,
  created_at timestamptz default now(),
  unique (farm_id, ear_tag)
);

-- ============================================================
-- INSEMINATIONS
-- ============================================================

create table inseminations (
  id uuid primary key default uuid_generate_v4(),
  cow_id uuid not null references cows(id) on delete cascade,
  date date not null,
  inseminated_at timestamptz,  -- full date+time of the insemination
  bull_name text,
  dose_id text,
  semen_type semen_type,
  technician_id uuid references users(id),
  attempt_number int default 1,
  notes text,
  created_at timestamptz default now()
);

-- Add FK from cows.last_insemination_id → inseminations.id
alter table cows
  add constraint fk_last_insemination
  foreign key (last_insemination_id)
  references inseminations(id);

-- ============================================================
-- NEEDLING ENROLLMENTS
-- ============================================================

create table needling_enrollments (
  id uuid primary key default uuid_generate_v4(),
  cow_id uuid not null references cows(id) on delete cascade,
  protocol protocol_type not null,
  start_date date not null,
  current_day int default 1,
  status enrollment_status default 'active',
  created_at timestamptz default now()
);

-- ============================================================
-- NEEDLING RECORDS (daily injections)
-- ============================================================

create table needling_records (
  id uuid primary key default uuid_generate_v4(),
  enrollment_id uuid not null references needling_enrollments(id) on delete cascade,
  cow_id uuid not null references cows(id) on delete cascade,
  protocol_day int not null constraint ck_needling_records_day_positive check (protocol_day > 0),
  scheduled_date date not null,
  completed_date date,
  treatment text not null,
  is_final boolean not null default false,  -- true on the protocol's final (AI) day
  completed boolean default false,
  bleeding_event boolean default false,
  technician_id uuid references users(id),
  notes text,
  created_at timestamptz default now()
);

-- ============================================================
-- HEAT CHECKS
-- ============================================================

create table heat_checks (
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
);

-- ============================================================
-- PREGNANCY CHECKS
-- ============================================================

create table pregnancy_checks (
  id uuid primary key default uuid_generate_v4(),
  cow_id uuid not null references cows(id) on delete cascade,
  insemination_id uuid not null references inseminations(id) on delete cascade,
  check_date date not null,
  vet_id uuid references users(id),          -- only set when the acting user is a vet
  performed_by_id uuid references users(id), -- always the acting user
  result pregnancy_result,
  has_infection boolean default false,
  has_cysts boolean default false,
  notes text,
  created_at timestamptz default now()
);

-- ============================================================
-- CALVING RECORDS
-- ============================================================

create table calving_records (
  id uuid primary key default uuid_generate_v4(),
  cow_id uuid not null references cows(id) on delete cascade,
  calving_date date not null,
  live_birth boolean default true,
  still_birth boolean default false,
  calf_sex calf_sex,
  calf_ear_tag text,
  calf_sale_info text,  -- for male calves (no herd record): sale/outcome details
  calf_id uuid references cows(id),
  technician_id uuid references users(id),
  notes text,
  created_at timestamptz default now(),
  constraint ck_calving_live_still_exclusive check (live_birth <> still_birth)
);

-- ============================================================
-- VACCINATION RECORDS
-- ============================================================

create table vaccination_records (
  id uuid primary key default uuid_generate_v4(),
  cow_id uuid not null references cows(id) on delete cascade,
  calving_record_id uuid references calving_records(id),
  scheduled_date date not null,
  completed_date date,
  administered_at timestamptz,  -- full date+time the vaccine was administered
  vaccine_name text,
  lot_number text,
  technician_id uuid references users(id),
  completed boolean default false,
  notes text,
  created_at timestamptz default now()
);

-- ============================================================
-- CULL RECORDS
-- ============================================================

create table cull_records (
  id uuid primary key default uuid_generate_v4(),
  cow_id uuid not null references cows(id) on delete cascade,
  cull_date date not null,
  reason text,
  technician_id uuid references users(id),
  notes text,
  created_at timestamptz default now()
);

-- ============================================================
-- NOTIFICATIONS (in-app farmer notifications)
-- ============================================================

create table notifications (
  id uuid primary key default uuid_generate_v4(),
  farm_id uuid not null references farms(id) on delete cascade,
  cow_id uuid references cows(id) on delete set null,
  type text not null,
  message text not null,
  read boolean not null default false,
  created_at timestamptz default now()
);


-- ============================================================
-- INDEXES (for report query performance)
-- ============================================================

create index idx_cows_farm_id on cows(farm_id);
create index idx_cows_status on cows(status);
create index idx_cows_last_insemination_date on cows(last_insemination_date);
create index idx_cows_due_date on cows(due_date);
create index idx_cows_dry_date on cows(dry_date);
create index idx_cows_last_calving_date on cows(last_calving_date);
create index idx_inseminations_cow_id on inseminations(cow_id);
create index idx_inseminations_date on inseminations(date);
create index idx_needling_records_scheduled_date on needling_records(scheduled_date);
create index idx_needling_records_cow_id on needling_records(cow_id);
create index idx_heat_checks_cow_id on heat_checks(cow_id);
create index idx_heat_checks_check_date on heat_checks(check_date);
create index idx_pregnancy_checks_cow_id on pregnancy_checks(cow_id);
create index idx_calving_records_cow_id on calving_records(cow_id);
create index idx_vaccination_records_scheduled_date on vaccination_records(scheduled_date);
create index idx_needling_records_enrollment_id on needling_records(enrollment_id);
create index idx_vaccination_records_cow_id on vaccination_records(cow_id);
create index idx_heat_checks_insemination_id on heat_checks(insemination_id);
create index idx_pregnancy_checks_insemination_id on pregnancy_checks(insemination_id);
create index idx_pregnancy_checks_check_date on pregnancy_checks(check_date);
create index idx_users_farm_id on users(farm_id);
create index idx_farms_assigned_technician_id on farms(assigned_technician_id);
create index idx_needling_enrollments_cow_id on needling_enrollments(cow_id);
create index idx_cull_records_cow_id on cull_records(cow_id);
create index idx_notifications_farm_id on notifications(farm_id);
create index idx_notifications_created_at on notifications(created_at);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================

alter table users enable row level security;
alter table farms enable row level security;
alter table vets enable row level security;
alter table vet_farm_assignments enable row level security;
alter table cows enable row level security;
alter table inseminations enable row level security;
alter table needling_enrollments enable row level security;
alter table needling_records enable row level security;
alter table heat_checks enable row level security;
alter table pregnancy_checks enable row level security;
alter table calving_records enable row level security;
alter table vaccination_records enable row level security;
alter table cull_records enable row level security;
alter table notifications enable row level security;

-- Helper: get current user's role
create or replace function get_my_role()
returns user_role as $$
  select role from users where id = auth.uid();
$$ language sql security definer;

-- Helper: get current user's farm_id
create or replace function get_my_farm_id()
returns uuid as $$
  select farm_id from users where id = auth.uid();
$$ language sql security definer;

-- Users: can read own record; admins read all
create policy "users_read_own" on users
  for select using (id = auth.uid() or get_my_role() = 'admin');

create policy "users_update_own" on users
  for update using (id = auth.uid());

-- Farms: admins + technicians see all; farm role sees own farm only
create policy "farms_read" on farms
  for select using (
    get_my_role() in ('admin', 'technician', 'vet')
    or id = get_my_farm_id()
  );

create policy "farms_write" on farms
  for all using (get_my_role() = 'admin');

-- Cows: scoped by farm visibility
create policy "cows_read" on cows
  for select using (
    get_my_role() in ('admin', 'technician')
    or farm_id = get_my_farm_id()
    or farm_id in (
      select farm_id from vet_farm_assignments
      where vet_id = (select id from vets where user_id = auth.uid())
    )
  );

create policy "cows_write" on cows
  for all using (get_my_role() in ('admin', 'technician'));

-- All event tables: technicians + admins write; scoped reads
create policy "inseminations_read" on inseminations
  for select using (get_my_role() in ('admin', 'technician', 'vet'));

create policy "inseminations_write" on inseminations
  for all using (get_my_role() in ('admin', 'technician'));

create policy "pregnancy_checks_read" on pregnancy_checks
  for select using (get_my_role() in ('admin', 'technician', 'vet'));

create policy "pregnancy_checks_write" on pregnancy_checks
  for all using (get_my_role() in ('admin', 'technician', 'vet'));

create policy "needling_read" on needling_enrollments
  for select using (get_my_role() in ('admin', 'technician'));

create policy "needling_write" on needling_enrollments
  for all using (get_my_role() in ('admin', 'technician'));

create policy "needling_records_read" on needling_records
  for select using (get_my_role() in ('admin', 'technician'));

create policy "needling_records_write" on needling_records
  for all using (get_my_role() in ('admin', 'technician'));

create policy "heat_checks_read" on heat_checks
  for select using (get_my_role() in ('admin', 'technician'));

create policy "heat_checks_write" on heat_checks
  for all using (get_my_role() in ('admin', 'technician'));

create policy "calving_records_read" on calving_records
  for select using (get_my_role() in ('admin', 'technician', 'farm'));

create policy "calving_records_write" on calving_records
  for all using (get_my_role() in ('admin', 'technician'));

create policy "vaccination_records_read" on vaccination_records
  for select using (get_my_role() in ('admin', 'technician'));

create policy "vaccination_records_write" on vaccination_records
  for all using (get_my_role() in ('admin', 'technician'));

create policy "cull_records_read" on cull_records
  for select using (get_my_role() in ('admin', 'technician'));

create policy "cull_records_write" on cull_records
  for all using (get_my_role() in ('admin', 'technician'));

create policy "notifications_read" on notifications
  for select using (
    get_my_role() in ('admin', 'technician', 'vet')
    or farm_id = get_my_farm_id()
  );

create policy "notifications_write" on notifications
  for all using (get_my_role() in ('admin', 'technician'));

create policy "vets_read" on vets
  for select using (get_my_role() in ('admin', 'technician', 'vet', 'farm'));

create policy "vet_assignments_read" on vet_farm_assignments
  for select using (get_my_role() in ('admin', 'technician', 'vet', 'farm'));
