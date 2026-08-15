-- Major Dairy AI — public schema, GENERATED from the Alembic migrations.
--
-- Do NOT hand-edit. Regenerate with:
--
--   cd backend && ./scripts/dump_schema.sh
--
-- Alembic remains the source of truth; this is a reference snapshot.

--
-- PostgreSQL database dump
--

\restrict UesLn1zR6wuhcgK9dWn8pg3B9cTtzbkk5PGHWepOHXxphUbApoSd3TRJJsxxFCj

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: calf_sex; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.calf_sex AS ENUM (
    'male',
    'female'
);


--
-- Name: cow_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.cow_status AS ENUM (
    'calf',
    'heifer',
    'fresh',
    'open',
    'needling',
    'inseminated',
    'pregnant',
    'dry',
    'cull',
    'sold',
    'dead'
);


--
-- Name: enrollment_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.enrollment_status AS ENUM (
    'active',
    'completed_pending_ai',
    'completed',
    'cancelled'
);


--
-- Name: health_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.health_status AS ENUM (
    'healthy',
    'sick'
);


--
-- Name: pregnancy_result; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.pregnancy_result AS ENUM (
    'pregnant',
    'not_pregnant'
);


--
-- Name: protocol_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.protocol_type AS ENUM (
    'ovsynch',
    'prostaglandin_heat',
    'double_ovsynch',
    'presynch',
    'general_synch',
    'general_synch_2'
);


--
-- Name: semen_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.semen_type AS ENUM (
    'sexed',
    'conventional',
    'beef'
);


--
-- Name: user_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_role AS ENUM (
    'admin',
    'technician',
    'farm',
    'vet'
);


--
-- Name: get_my_farm_id(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_my_farm_id() RETURNS uuid
    LANGUAGE sql SECURITY DEFINER
    AS $$
            select farm_id from users where id = auth.uid();
        $$;


--
-- Name: get_my_farm_ids(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_my_farm_ids() RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
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
                      and a.visit_date >= current_date - interval '7 days'
                )
        $$;


--
-- Name: get_my_role(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_my_role() RETURNS public.user_role
    LANGUAGE sql SECURITY DEFINER
    AS $$
            select role from users where id = auth.uid();
        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: bulls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bulls (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    farm_id uuid NOT NULL,
    name character varying NOT NULL,
    code character varying,
    semen_type public.semen_type,
    active boolean DEFAULT true NOT NULL,
    notes character varying,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: calving_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.calving_records (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    cow_id uuid NOT NULL,
    calving_date date NOT NULL,
    live_birth boolean DEFAULT true,
    still_birth boolean DEFAULT false,
    calf_sex public.calf_sex,
    calf_ear_tag text,
    calf_id uuid,
    technician_id uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    calf_sale_info text,
    CONSTRAINT ck_calving_live_still_exclusive CHECK ((live_birth <> still_birth))
);


--
-- Name: cows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cows (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    ear_tag text NOT NULL,
    farm_id uuid NOT NULL,
    breed text,
    date_of_birth date,
    sex public.calf_sex DEFAULT 'female'::public.calf_sex NOT NULL,
    lactation_number integer DEFAULT 0,
    status public.cow_status DEFAULT 'calf'::public.cow_status NOT NULL,
    current_program text,
    last_calving_date date,
    last_insemination_date date,
    last_insemination_id uuid,
    due_date date,
    dry_date date,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    exit_date date,
    exit_reason text,
    health_status public.health_status DEFAULT 'healthy'::public.health_status,
    recheck_due_date date,
    dry_off_confirmed_date date,
    CONSTRAINT ck_cows_lactation_number_non_negative CHECK ((lactation_number >= 0))
);


--
-- Name: cull_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cull_records (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    cow_id uuid NOT NULL,
    cull_date date NOT NULL,
    reason text,
    technician_id uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: farm_visit_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.farm_visit_assignments (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    farm_id uuid NOT NULL,
    visit_date date NOT NULL,
    assigned_technician_id uuid,
    reason character varying,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: farms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.farms (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name text NOT NULL,
    owner_name text NOT NULL,
    address text,
    city text,
    province text,
    postal_code text,
    phone text,
    email text,
    herd_size integer DEFAULT 0,
    assigned_technician_id uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    visit_weekdays smallint[] DEFAULT '{0,1,2,3,4,5}'::smallint[] NOT NULL,
    CONSTRAINT ck_farms_herd_size_non_negative CHECK ((herd_size >= 0)),
    CONSTRAINT ck_farms_visit_weekdays_valid CHECK ((((cardinality(visit_weekdays) >= 1) AND (cardinality(visit_weekdays) <= 7)) AND (visit_weekdays <@ '{0,1,2,3,4,5,6}'::smallint[])))
);


--
-- Name: heat_checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.heat_checks (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    cow_id uuid NOT NULL,
    insemination_id uuid NOT NULL,
    check_date date NOT NULL,
    days_since_insemination integer NOT NULL,
    heat_detected boolean,
    bleeding_event boolean DEFAULT false,
    technician_id uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: inseminations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inseminations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    cow_id uuid NOT NULL,
    date date NOT NULL,
    bull_name text,
    dose_id text,
    semen_type public.semen_type,
    technician_id uuid,
    attempt_number integer DEFAULT 1,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    inseminated_at timestamp with time zone,
    bull_id uuid,
    insemination_code character varying
);


--
-- Name: needling_enrollments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.needling_enrollments (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    cow_id uuid NOT NULL,
    protocol public.protocol_type NOT NULL,
    start_date date NOT NULL,
    current_day integer DEFAULT 1,
    status public.enrollment_status DEFAULT 'active'::public.enrollment_status,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: needling_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.needling_records (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    enrollment_id uuid NOT NULL,
    cow_id uuid NOT NULL,
    protocol_day integer NOT NULL,
    scheduled_date date NOT NULL,
    completed_date date,
    treatment text NOT NULL,
    completed boolean DEFAULT false,
    bleeding_event boolean DEFAULT false,
    technician_id uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    is_final boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_needling_records_day_positive CHECK ((protocol_day > 0))
);


--
-- Name: notification_reads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notification_reads (
    notification_id uuid NOT NULL,
    user_id uuid NOT NULL,
    read_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    farm_id uuid NOT NULL,
    cow_id uuid,
    type text NOT NULL,
    message text NOT NULL,
    read boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    email_status character varying,
    emailed_at timestamp with time zone,
    email_error character varying
);


--
-- Name: pregnancy_checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pregnancy_checks (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    cow_id uuid NOT NULL,
    insemination_id uuid NOT NULL,
    check_date date NOT NULL,
    vet_id uuid,
    result public.pregnancy_result,
    has_infection boolean DEFAULT false,
    has_cysts boolean DEFAULT false,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    performed_by_id uuid
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    name text NOT NULL,
    email text NOT NULL,
    role public.user_role NOT NULL,
    phone text,
    employee_id text,
    region text,
    farm_id uuid,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: vaccination_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vaccination_records (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    cow_id uuid NOT NULL,
    calving_record_id uuid,
    scheduled_date date NOT NULL,
    completed_date date,
    vaccine_name text,
    lot_number text,
    technician_id uuid,
    completed boolean DEFAULT false,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    administered_at timestamp with time zone
);


--
-- Name: vet_farm_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vet_farm_assignments (
    vet_id uuid NOT NULL,
    farm_id uuid NOT NULL
);


--
-- Name: vets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vets (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid,
    name text NOT NULL,
    clinic text,
    phone text,
    email text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: bulls bulls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bulls
    ADD CONSTRAINT bulls_pkey PRIMARY KEY (id);


--
-- Name: calving_records calving_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calving_records
    ADD CONSTRAINT calving_records_pkey PRIMARY KEY (id);


--
-- Name: cows cows_farm_id_ear_tag_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cows
    ADD CONSTRAINT cows_farm_id_ear_tag_key UNIQUE (farm_id, ear_tag);


--
-- Name: cows cows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cows
    ADD CONSTRAINT cows_pkey PRIMARY KEY (id);


--
-- Name: cull_records cull_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cull_records
    ADD CONSTRAINT cull_records_pkey PRIMARY KEY (id);


--
-- Name: farm_visit_assignments farm_visit_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.farm_visit_assignments
    ADD CONSTRAINT farm_visit_assignments_pkey PRIMARY KEY (id);


--
-- Name: farms farms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.farms
    ADD CONSTRAINT farms_pkey PRIMARY KEY (id);


--
-- Name: heat_checks heat_checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.heat_checks
    ADD CONSTRAINT heat_checks_pkey PRIMARY KEY (id);


--
-- Name: inseminations inseminations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inseminations
    ADD CONSTRAINT inseminations_pkey PRIMARY KEY (id);


--
-- Name: needling_enrollments needling_enrollments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.needling_enrollments
    ADD CONSTRAINT needling_enrollments_pkey PRIMARY KEY (id);


--
-- Name: needling_records needling_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.needling_records
    ADD CONSTRAINT needling_records_pkey PRIMARY KEY (id);


--
-- Name: notification_reads notification_reads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_reads
    ADD CONSTRAINT notification_reads_pkey PRIMARY KEY (notification_id, user_id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: pregnancy_checks pregnancy_checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pregnancy_checks
    ADD CONSTRAINT pregnancy_checks_pkey PRIMARY KEY (id);


--
-- Name: bulls uq_bulls_farm_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bulls
    ADD CONSTRAINT uq_bulls_farm_name UNIQUE (farm_id, name);


--
-- Name: farm_visit_assignments uq_farm_visit_assignment_day; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.farm_visit_assignments
    ADD CONSTRAINT uq_farm_visit_assignment_day UNIQUE (farm_id, visit_date);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: vaccination_records vaccination_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vaccination_records
    ADD CONSTRAINT vaccination_records_pkey PRIMARY KEY (id);


--
-- Name: vet_farm_assignments vet_farm_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vet_farm_assignments
    ADD CONSTRAINT vet_farm_assignments_pkey PRIMARY KEY (vet_id, farm_id);


--
-- Name: vets vets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vets
    ADD CONSTRAINT vets_pkey PRIMARY KEY (id);


--
-- Name: idx_calving_records_cow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_calving_records_cow_id ON public.calving_records USING btree (cow_id);


--
-- Name: idx_cows_dry_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cows_dry_date ON public.cows USING btree (dry_date);


--
-- Name: idx_cows_due_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cows_due_date ON public.cows USING btree (due_date);


--
-- Name: idx_cows_farm_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cows_farm_id ON public.cows USING btree (farm_id);


--
-- Name: idx_cows_last_calving_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cows_last_calving_date ON public.cows USING btree (last_calving_date);


--
-- Name: idx_cows_last_insemination_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cows_last_insemination_date ON public.cows USING btree (last_insemination_date);


--
-- Name: idx_cows_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cows_status ON public.cows USING btree (status);


--
-- Name: idx_cull_records_cow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cull_records_cow_id ON public.cull_records USING btree (cow_id);


--
-- Name: idx_farms_assigned_technician_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_farms_assigned_technician_id ON public.farms USING btree (assigned_technician_id);


--
-- Name: idx_heat_checks_check_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_heat_checks_check_date ON public.heat_checks USING btree (check_date);


--
-- Name: idx_heat_checks_cow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_heat_checks_cow_id ON public.heat_checks USING btree (cow_id);


--
-- Name: idx_heat_checks_insemination_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_heat_checks_insemination_id ON public.heat_checks USING btree (insemination_id);


--
-- Name: idx_inseminations_cow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inseminations_cow_id ON public.inseminations USING btree (cow_id);


--
-- Name: idx_inseminations_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inseminations_date ON public.inseminations USING btree (date);


--
-- Name: idx_needling_enrollments_cow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_needling_enrollments_cow_id ON public.needling_enrollments USING btree (cow_id);


--
-- Name: idx_needling_records_cow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_needling_records_cow_id ON public.needling_records USING btree (cow_id);


--
-- Name: idx_needling_records_enrollment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_needling_records_enrollment_id ON public.needling_records USING btree (enrollment_id);


--
-- Name: idx_needling_records_scheduled_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_needling_records_scheduled_date ON public.needling_records USING btree (scheduled_date);


--
-- Name: idx_notifications_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_created_at ON public.notifications USING btree (created_at);


--
-- Name: idx_notifications_farm_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_farm_id ON public.notifications USING btree (farm_id);


--
-- Name: idx_pregnancy_checks_check_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pregnancy_checks_check_date ON public.pregnancy_checks USING btree (check_date);


--
-- Name: idx_pregnancy_checks_cow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pregnancy_checks_cow_id ON public.pregnancy_checks USING btree (cow_id);


--
-- Name: idx_pregnancy_checks_insemination_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pregnancy_checks_insemination_id ON public.pregnancy_checks USING btree (insemination_id);


--
-- Name: idx_users_farm_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_farm_id ON public.users USING btree (farm_id);


--
-- Name: idx_vaccination_records_cow_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_vaccination_records_cow_id ON public.vaccination_records USING btree (cow_id);


--
-- Name: idx_vaccination_records_scheduled_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_vaccination_records_scheduled_date ON public.vaccination_records USING btree (scheduled_date);


--
-- Name: ix_bulls_farm_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bulls_farm_active ON public.bulls USING btree (farm_id, active);


--
-- Name: ix_farm_visit_assignments_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_farm_visit_assignments_date ON public.farm_visit_assignments USING btree (visit_date, assigned_technician_id);


--
-- Name: ix_notification_reads_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notification_reads_user ON public.notification_reads USING btree (user_id);


--
-- Name: ix_notifications_email_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_email_status ON public.notifications USING btree (email_status, created_at);


--
-- Name: bulls bulls_farm_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bulls
    ADD CONSTRAINT bulls_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.farms(id) ON DELETE CASCADE;


--
-- Name: calving_records calving_records_calf_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calving_records
    ADD CONSTRAINT calving_records_calf_id_fkey FOREIGN KEY (calf_id) REFERENCES public.cows(id);


--
-- Name: calving_records calving_records_cow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calving_records
    ADD CONSTRAINT calving_records_cow_id_fkey FOREIGN KEY (cow_id) REFERENCES public.cows(id) ON DELETE CASCADE;


--
-- Name: calving_records calving_records_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calving_records
    ADD CONSTRAINT calving_records_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.users(id);


--
-- Name: cows cows_farm_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cows
    ADD CONSTRAINT cows_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.farms(id) ON DELETE CASCADE;


--
-- Name: cull_records cull_records_cow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cull_records
    ADD CONSTRAINT cull_records_cow_id_fkey FOREIGN KEY (cow_id) REFERENCES public.cows(id) ON DELETE CASCADE;


--
-- Name: cull_records cull_records_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cull_records
    ADD CONSTRAINT cull_records_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.users(id);


--
-- Name: farm_visit_assignments farm_visit_assignments_assigned_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.farm_visit_assignments
    ADD CONSTRAINT farm_visit_assignments_assigned_technician_id_fkey FOREIGN KEY (assigned_technician_id) REFERENCES public.users(id);


--
-- Name: farm_visit_assignments farm_visit_assignments_farm_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.farm_visit_assignments
    ADD CONSTRAINT farm_visit_assignments_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.farms(id) ON DELETE CASCADE;


--
-- Name: farms farms_assigned_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.farms
    ADD CONSTRAINT farms_assigned_technician_id_fkey FOREIGN KEY (assigned_technician_id) REFERENCES public.users(id);


--
-- Name: inseminations fk_inseminations_bull; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inseminations
    ADD CONSTRAINT fk_inseminations_bull FOREIGN KEY (bull_id) REFERENCES public.bulls(id);


--
-- Name: cows fk_last_insemination; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cows
    ADD CONSTRAINT fk_last_insemination FOREIGN KEY (last_insemination_id) REFERENCES public.inseminations(id);


--
-- Name: users fk_users_farm; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_farm FOREIGN KEY (farm_id) REFERENCES public.farms(id);


--
-- Name: heat_checks heat_checks_cow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.heat_checks
    ADD CONSTRAINT heat_checks_cow_id_fkey FOREIGN KEY (cow_id) REFERENCES public.cows(id) ON DELETE CASCADE;


--
-- Name: heat_checks heat_checks_insemination_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.heat_checks
    ADD CONSTRAINT heat_checks_insemination_id_fkey FOREIGN KEY (insemination_id) REFERENCES public.inseminations(id) ON DELETE CASCADE;


--
-- Name: heat_checks heat_checks_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.heat_checks
    ADD CONSTRAINT heat_checks_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.users(id);


--
-- Name: inseminations inseminations_cow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inseminations
    ADD CONSTRAINT inseminations_cow_id_fkey FOREIGN KEY (cow_id) REFERENCES public.cows(id) ON DELETE CASCADE;


--
-- Name: inseminations inseminations_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inseminations
    ADD CONSTRAINT inseminations_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.users(id);


--
-- Name: needling_enrollments needling_enrollments_cow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.needling_enrollments
    ADD CONSTRAINT needling_enrollments_cow_id_fkey FOREIGN KEY (cow_id) REFERENCES public.cows(id) ON DELETE CASCADE;


--
-- Name: needling_records needling_records_cow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.needling_records
    ADD CONSTRAINT needling_records_cow_id_fkey FOREIGN KEY (cow_id) REFERENCES public.cows(id) ON DELETE CASCADE;


--
-- Name: needling_records needling_records_enrollment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.needling_records
    ADD CONSTRAINT needling_records_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.needling_enrollments(id) ON DELETE CASCADE;


--
-- Name: needling_records needling_records_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.needling_records
    ADD CONSTRAINT needling_records_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.users(id);


--
-- Name: notification_reads notification_reads_notification_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_reads
    ADD CONSTRAINT notification_reads_notification_id_fkey FOREIGN KEY (notification_id) REFERENCES public.notifications(id) ON DELETE CASCADE;


--
-- Name: notification_reads notification_reads_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_reads
    ADD CONSTRAINT notification_reads_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_cow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_cow_id_fkey FOREIGN KEY (cow_id) REFERENCES public.cows(id) ON DELETE SET NULL;


--
-- Name: notifications notifications_farm_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.farms(id) ON DELETE CASCADE;


--
-- Name: pregnancy_checks pregnancy_checks_cow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pregnancy_checks
    ADD CONSTRAINT pregnancy_checks_cow_id_fkey FOREIGN KEY (cow_id) REFERENCES public.cows(id) ON DELETE CASCADE;


--
-- Name: pregnancy_checks pregnancy_checks_insemination_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pregnancy_checks
    ADD CONSTRAINT pregnancy_checks_insemination_id_fkey FOREIGN KEY (insemination_id) REFERENCES public.inseminations(id) ON DELETE CASCADE;


--
-- Name: pregnancy_checks pregnancy_checks_performed_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pregnancy_checks
    ADD CONSTRAINT pregnancy_checks_performed_by_id_fkey FOREIGN KEY (performed_by_id) REFERENCES public.users(id);


--
-- Name: pregnancy_checks pregnancy_checks_vet_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pregnancy_checks
    ADD CONSTRAINT pregnancy_checks_vet_id_fkey FOREIGN KEY (vet_id) REFERENCES public.users(id);


--
-- Name: users users_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: vaccination_records vaccination_records_calving_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vaccination_records
    ADD CONSTRAINT vaccination_records_calving_record_id_fkey FOREIGN KEY (calving_record_id) REFERENCES public.calving_records(id);


--
-- Name: vaccination_records vaccination_records_cow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vaccination_records
    ADD CONSTRAINT vaccination_records_cow_id_fkey FOREIGN KEY (cow_id) REFERENCES public.cows(id) ON DELETE CASCADE;


--
-- Name: vaccination_records vaccination_records_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vaccination_records
    ADD CONSTRAINT vaccination_records_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.users(id);


--
-- Name: vet_farm_assignments vet_farm_assignments_farm_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vet_farm_assignments
    ADD CONSTRAINT vet_farm_assignments_farm_id_fkey FOREIGN KEY (farm_id) REFERENCES public.farms(id) ON DELETE CASCADE;


--
-- Name: vet_farm_assignments vet_farm_assignments_vet_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vet_farm_assignments
    ADD CONSTRAINT vet_farm_assignments_vet_id_fkey FOREIGN KEY (vet_id) REFERENCES public.vets(id) ON DELETE CASCADE;


--
-- Name: vets vets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vets
    ADD CONSTRAINT vets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: bulls; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bulls ENABLE ROW LEVEL SECURITY;

--
-- Name: bulls bulls_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY bulls_read ON public.bulls FOR SELECT USING (((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'vet'::public.user_role])) OR (farm_id = public.get_my_farm_id())));


--
-- Name: bulls bulls_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY bulls_write ON public.bulls USING (((public.get_my_role() = 'admin'::public.user_role) OR ((public.get_my_role() = 'technician'::public.user_role) AND (farm_id IN ( SELECT public.get_my_farm_ids() AS get_my_farm_ids))))) WITH CHECK (((public.get_my_role() = 'admin'::public.user_role) OR ((public.get_my_role() = 'technician'::public.user_role) AND (farm_id IN ( SELECT public.get_my_farm_ids() AS get_my_farm_ids)))));


--
-- Name: calving_records; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.calving_records ENABLE ROW LEVEL SECURITY;

--
-- Name: calving_records calving_records_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY calving_records_read ON public.calving_records FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'farm'::public.user_role])));


--
-- Name: calving_records calving_records_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY calving_records_write ON public.calving_records USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: cows; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.cows ENABLE ROW LEVEL SECURITY;

--
-- Name: cows cows_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cows_read ON public.cows FOR SELECT USING (((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])) OR (farm_id = public.get_my_farm_id()) OR (farm_id IN ( SELECT vet_farm_assignments.farm_id
   FROM public.vet_farm_assignments
  WHERE (vet_farm_assignments.vet_id = ( SELECT vets.id
           FROM public.vets
          WHERE (vets.user_id = auth.uid())))))));


--
-- Name: cows cows_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cows_write ON public.cows USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: cull_records; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.cull_records ENABLE ROW LEVEL SECURITY;

--
-- Name: cull_records cull_records_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cull_records_read ON public.cull_records FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: cull_records cull_records_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cull_records_write ON public.cull_records USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: farm_visit_assignments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.farm_visit_assignments ENABLE ROW LEVEL SECURITY;

--
-- Name: farm_visit_assignments farm_visit_assignments_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY farm_visit_assignments_read ON public.farm_visit_assignments FOR SELECT USING (((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'vet'::public.user_role])) OR (farm_id = public.get_my_farm_id())));


--
-- Name: farm_visit_assignments farm_visit_assignments_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY farm_visit_assignments_write ON public.farm_visit_assignments USING ((public.get_my_role() = 'admin'::public.user_role));


--
-- Name: farms; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.farms ENABLE ROW LEVEL SECURITY;

--
-- Name: farms farms_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY farms_read ON public.farms FOR SELECT USING (((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'vet'::public.user_role])) OR (id = public.get_my_farm_id())));


--
-- Name: farms farms_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY farms_write ON public.farms USING ((public.get_my_role() = 'admin'::public.user_role));


--
-- Name: heat_checks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.heat_checks ENABLE ROW LEVEL SECURITY;

--
-- Name: heat_checks heat_checks_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY heat_checks_read ON public.heat_checks FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: heat_checks heat_checks_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY heat_checks_write ON public.heat_checks USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: inseminations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.inseminations ENABLE ROW LEVEL SECURITY;

--
-- Name: inseminations inseminations_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY inseminations_read ON public.inseminations FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'vet'::public.user_role])));


--
-- Name: inseminations inseminations_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY inseminations_write ON public.inseminations USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: needling_enrollments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.needling_enrollments ENABLE ROW LEVEL SECURITY;

--
-- Name: needling_enrollments needling_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY needling_read ON public.needling_enrollments FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: needling_records; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.needling_records ENABLE ROW LEVEL SECURITY;

--
-- Name: needling_records needling_records_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY needling_records_read ON public.needling_records FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: needling_records needling_records_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY needling_records_write ON public.needling_records USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: needling_enrollments needling_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY needling_write ON public.needling_enrollments USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: notification_reads; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.notification_reads ENABLE ROW LEVEL SECURITY;

--
-- Name: notification_reads notification_reads_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY notification_reads_own ON public.notification_reads USING ((user_id = auth.uid())) WITH CHECK ((user_id = auth.uid()));


--
-- Name: notifications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

--
-- Name: notifications notifications_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY notifications_read ON public.notifications FOR SELECT USING (((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'vet'::public.user_role])) OR (farm_id = public.get_my_farm_id())));


--
-- Name: notifications notifications_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY notifications_write ON public.notifications USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: pregnancy_checks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pregnancy_checks ENABLE ROW LEVEL SECURITY;

--
-- Name: pregnancy_checks pregnancy_checks_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pregnancy_checks_read ON public.pregnancy_checks FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'vet'::public.user_role])));


--
-- Name: pregnancy_checks pregnancy_checks_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pregnancy_checks_write ON public.pregnancy_checks USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'vet'::public.user_role])));


--
-- Name: users; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

--
-- Name: users users_read_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_read_own ON public.users FOR SELECT USING (((id = auth.uid()) OR (public.get_my_role() = 'admin'::public.user_role)));


--
-- Name: users users_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY users_update_own ON public.users FOR UPDATE USING ((id = auth.uid()));


--
-- Name: vaccination_records; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.vaccination_records ENABLE ROW LEVEL SECURITY;

--
-- Name: vaccination_records vaccination_records_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY vaccination_records_read ON public.vaccination_records FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: vaccination_records vaccination_records_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY vaccination_records_write ON public.vaccination_records USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role])));


--
-- Name: vet_farm_assignments vet_assignments_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY vet_assignments_read ON public.vet_farm_assignments FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'vet'::public.user_role, 'farm'::public.user_role])));


--
-- Name: vet_farm_assignments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.vet_farm_assignments ENABLE ROW LEVEL SECURITY;

--
-- Name: vets; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.vets ENABLE ROW LEVEL SECURITY;

--
-- Name: vets vets_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY vets_read ON public.vets FOR SELECT USING ((public.get_my_role() = ANY (ARRAY['admin'::public.user_role, 'technician'::public.user_role, 'vet'::public.user_role, 'farm'::public.user_role])));


--
-- PostgreSQL database dump complete
--

\unrestrict UesLn1zR6wuhcgK9dWn8pg3B9cTtzbkk5PGHWepOHXxphUbApoSd3TRJJsxxFCj

