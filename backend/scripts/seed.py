"""
Seed the database with realistic dummy herd data.

Idempotent: clears the domain tables (NOT users / auth) and re-inserts a fresh
dataset covering every cow lifecycle stage, so all reports and profiles have
content.

Two layers. A hand-written set pins one cow to each rule -- the day-7 PGF, the
final-day timed AI, the 50-day overdue check -- so no report can be silently
empty. A generator then fills the twelve farms out to ~540 animals: each cow
draws a status from a plausible herd mix and every date is derived from the
constants the app itself uses, so she lands on exactly the reports her dates
earn. Nothing about the daily workload is typed in; it falls out of the rules. All user/technician/vet-account references are left NULL because
`users.id` references Supabase `auth.users` — real accounts are created through
the app's sign-up flow. Log in as an ADMIN to see the full seeded herd.

Run:  cd backend && .venv/bin/python -m scripts.seed
"""

import asyncio
import random
import uuid
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from urllib.parse import quote_plus

from app.core.config import settings
from app.services.protocols import get_scheduled_records
from app.services.report_catalog import VACCINATION_WINDOW
from app.services.visits import weekdays_for
from app.models.models import (
    Bull, CalfSex, CalvingRecord, Cow, CowStatus, CullRecord, EnrollmentStatus, Farm, HealthStatus,
    HeatCheck, Insemination, NeedlingEnrollment, NeedlingRecord, Notification,
    PregnancyCheck, PregnancyResult, ProtocolType, SemenType, Vet, VetFarmAssignment,
    VaccinationRecord,
)

TODAY = date.today()
GESTATION = 283
DRY_OFFSET = 223


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def days_from(base: date, n: int) -> date:
    return base + timedelta(days=n)


# Domain tables to clear, in FK-safe order (children first). Users/auth untouched.
CLEAR_ORDER = [
    "notifications", "vaccination_records", "cull_records",
    "calving_records", "pregnancy_checks", "heat_checks", "needling_records",
    "needling_enrollments", "farm_visit_assignments", "bulls",
]


async def clear(session: AsyncSession) -> None:
    for tbl in CLEAR_ORDER:
        await session.execute(text(f"DELETE FROM {tbl}"))
    # Break the cows <-> inseminations cycle before deleting either.
    await session.execute(text("UPDATE cows SET last_insemination_id = NULL"))
    await session.execute(text("DELETE FROM inseminations"))
    await session.execute(text("DELETE FROM cows"))
    await session.execute(text("DELETE FROM vet_farm_assignments"))
    await session.execute(text("DELETE FROM vets"))
    # Farm managers point at a farm (users.farm_id), and users are deliberately
    # left alone here — so the delete below hit that foreign key and the whole
    # seed aborted on any database where a farm manager had been assigned. The
    # accounts stay; they simply lose the farm that is about to stop existing,
    # and get reassigned from the People screen.
    await session.execute(text("UPDATE users SET farm_id = NULL WHERE farm_id IS NOT NULL"))
    await session.execute(text("DELETE FROM farms"))
    await session.flush()


def make_farm(name, owner, address, city, postal, phone, email, herd_size, note,
              days_per_week=6):
    """days_per_week: 5 = Mon-Fri, 6 = Mon-Sat (the default). Seeding a mix is
    the point of the General To-Do list — on a Saturday the 5-day farms drop
    off the technician's route."""
    return Farm(
        id=uuid.uuid4(), name=name, owner_name=owner, address=address, city=city,
        province="Ontario", postal_code=postal, phone=phone, email=email,
        herd_size=herd_size, notes=note,
        visit_weekdays=list(weekdays_for(days_per_week)),
    )


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres", "host.docker.internal"}


def _guard_destructive() -> None:
    """Refuse to wipe a database that is not explicitly marked as disposable.

    This script DELETEs every table against whatever .env points at, and .env
    points at PRODUCTION. Two separate gates, because one is demonstrably not
    enough:

    1. SEED_ALLOW_DESTRUCTIVE=1 — "yes, I mean to wipe a database."
    2. For any non-local host, SEED_TARGET_HOST must ALSO equal that exact
       host.

    Gate 2 exists because the connection is assembled from DB_HOST/DB_NAME/…,
    not from DATABASE_URL. Setting DATABASE_URL to a scratch database — the
    obvious way to redirect it, and what every other tool here accepts — is
    silently ignored, so the script runs against production while the operator
    believes it is pointed somewhere disposable. Gate 1 is satisfied in exactly
    that moment, and it does not help. Naming the remote host out loud is the
    only check a wrong override cannot pass by accident.
    """
    import os
    import sys

    if os.getenv("SEED_ALLOW_DESTRUCTIVE") != "1":
        print(
            "REFUSING TO RUN: seed.py deletes every row in every table.\n"
            f"It would run against {settings.db_host}/{settings.db_name}.\n\n"
            "If that really is a disposable database, re-run with:\n"
            "    SEED_ALLOW_DESTRUCTIVE=1 .venv/bin/python -m scripts.seed",
            file=sys.stderr,
        )
        raise SystemExit(1)

    host = (settings.db_host or "").strip().lower()
    if host in LOCAL_HOSTS:
        return
    if os.getenv("SEED_TARGET_HOST", "").strip().lower() == host:
        return

    print(
        f"REFUSING TO RUN: {host}/{settings.db_name} is not a local database.\n\n"
        "Note that DATABASE_URL is IGNORED here — the connection is built from\n"
        "DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME. If you meant to point at a\n"
        "scratch database, set those instead.\n\n"
        "To wipe this remote database on purpose, name it explicitly:\n"
        f"    SEED_ALLOW_DESTRUCTIVE=1 SEED_TARGET_HOST={host} \\\n"
        "        .venv/bin/python -m scripts.seed",
        file=sys.stderr,
    )
    raise SystemExit(1)


async def seed(session: AsyncSession) -> None:
    # ── Farms ──────────────────────────────────────────────
    gv = make_farm("Green Valley Dairy", "John Smith", "2841 Concession Rd 6", "London",
                   "N6P 1A7", "+1 (519) 555-0114", "office@greenvalleydairy.ca", 425,
                   "Prefers visits before noon. New parlor installed March 2026.",
                   # 5-day farm: Mon-Fri
                   days_per_week=5)
    sf = make_farm("Sunrise Farms", "David Brown", "1150 Oxford Rd 29", "Woodstock",
                   "N4S 7V8", "+1 (519) 555-0167", "david@sunrisefarms.ca", 310, "Gate code 4482.",
                   # 6-day farm: Mon-Sat
                   days_per_week=6)
    mr = make_farm("Maple Ridge Dairy", "Peter Jones", "7723 Wellington Rd 34", "Guelph",
                   "N1H 6J2", "+1 (519) 555-0139", "peter@mapleridgedairy.ca", 560, None,
                   # 5-day farm: off the route on Saturdays
                   days_per_week=5)
    # Nine more farms. The client's note on the screenshots was that a
    # three-farm, fifteen-cow demo reads as a toy: a real technician covers a
    # dozen farms and several hundred animals, and a report with one row on it
    # says nothing about how the app behaves when it is full.
    EXTRA_FARMS = [
        ("Willowbrook Holsteins", "Margaret Ellis", "4410 Perth Line 26", "Stratford",
         "N5A 6S3", "+1 (519) 555-0183", "office@willowbrookholsteins.ca", 240, 6),
        ("Cedar Lane Dairy", "Tom Vandenberg", "988 Huron Rd 8", "Clinton",
         "N0M 1L0", "+1 (519) 555-0195", "tom@cedarlanedairy.ca", 180, 5),
        ("Blue Heron Farms", "Alice Fournier", "3175 Elgin Rd 14", "St Thomas",
         "N5P 3T2", "+1 (519) 555-0208", "alice@blueheronfarms.ca", 310, 6),
        ("Rockway Dairy", "Henry Martin", "620 Waterloo Rd 12", "Kitchener",
         "N2P 2H9", "+1 (519) 555-0214", "henry@rockwaydairy.ca", 150, 5),
        ("Thornhill Farms", "Grace Okafor", "7789 Middlesex Rd 9", "Strathroy",
         "N7G 3H4", "+1 (519) 555-0227", "grace@thornhillfarms.ca", 275, 6),
        ("Mill Creek Dairy", "Daniel Reimer", "1420 Bruce Rd 3", "Walkerton",
         "N0G 2V0", "+1 (519) 555-0231", "daniel@millcreekdairy.ca", 200, 5),
        ("Silver Birch Holsteins", "Nadia Haddad", "5560 Grey Rd 17", "Owen Sound",
         "N4K 5N7", "+1 (519) 555-0244", "nadia@silverbirchholsteins.ca", 330, 6),
        ("Fox Run Dairy", "Peter Lam", "2210 Norfolk Rd 21", "Simcoe",
         "N3Y 4K2", "+1 (519) 555-0256", "peter@foxrundairy.ca", 165, 5),
        ("Harvest Moon Farms", "Ruth Delaney", "8840 Lambton Line 7", "Petrolia",
         "N0N 1R0", "+1 (519) 555-0268", "ruth@harvestmoonfarms.ca", 220, 6),
    ]
    extra = [make_farm(n, o, a, c, pc, ph, e, h, None, days_per_week=d)
             for n, o, a, c, pc, ph, e, h, d in EXTRA_FARMS]
    session.add_all([gv, sf, mr, *extra])
    await session.flush()
    all_farms = [gv, sf, mr, *extra]

    # ── Vets (no user account — user_id NULL) ──────────────
    v1 = Vet(id=uuid.uuid4(), name="Dr. Sarah Mitchell", clinic="Heartland Veterinary Services",
             phone="+1 (519) 555-0221", email="s.mitchell@heartlandvet.ca")
    v2 = Vet(id=uuid.uuid4(), name="Dr. James Carter", clinic="Oxford County Animal Health",
             phone="+1 (519) 555-0246", email="j.carter@oxfordvets.ca")
    v3 = Vet(id=uuid.uuid4(), name="Dr. Priya Raman", clinic="Grand River Bovine Clinic",
             phone="+1 (519) 555-0272", email="p.raman@grandriverbovine.ca")
    v4 = Vet(id=uuid.uuid4(), name="Dr. Owen Beaulieu", clinic="Lakeshore Dairy Health",
             phone="+1 (519) 555-0289", email="o.beaulieu@lakeshoredairyhealth.ca")
    session.add_all([v1, v2, v3, v4])
    await session.flush()
    # Every farm has a vet: an unassigned farm shows an empty vet card, which
    # reads as a bug rather than as "nobody is assigned yet".
    vets = [v1, v2, v3, v4]
    session.add_all([
        VetFarmAssignment(vet_id=vets[i % len(vets)].id, farm_id=f.id)
        for i, f in enumerate(all_farms)
    ])

    # ── Bulls (the farm's semen list) ──────────────────────
    # Seeded data had no bulls at all, so the insemination form's bull picker
    # rendered nothing on a freshly seeded database and every demo of the
    # feature looked like it was missing. Semen is bought per farm, so each
    # farm gets its own short list with a realistic sexed/conventional/beef mix.
    BULL_LISTS = {
        gv: [("Mogul", "7HO11314", SemenType.conventional),
             ("Delta-Lambda", "7HO14454", SemenType.sexed),
             ("Angus Prime", "29AN2011", SemenType.beef)],
        sf: [("Rubicon", "250HO12961", SemenType.conventional),
             ("Josuper", "7HO12587", SemenType.sexed)],
        mr: [("Crushabull", "551HO03379", SemenType.conventional),
             ("Charolais Red", "14CH0044", SemenType.beef),
             ("Frazzled", "7HO12788", SemenType.sexed)],
    }
    STOCK_BULLS = [
        ("Mogul", "7HO11314", SemenType.conventional),
        ("Delta-Lambda", "7HO14454", SemenType.sexed),
        ("Rubicon", "250HO12961", SemenType.conventional),
        ("Frazzled", "7HO12788", SemenType.sexed),
        ("Angus Prime", "29AN2011", SemenType.beef),
    ]
    bull_labels: dict = {}
    for farm_obj in all_farms:
        entries = BULL_LISTS.get(farm_obj) or STOCK_BULLS[:3]
        for name, code, semen in entries:
            session.add(Bull(id=uuid.uuid4(), farm_id=farm_obj.id, name=name,
                             code=code, semen_type=semen, active=True))
        # An insemination stores the bull as free text, so the generated herd
        # below has to draw from the same list the picker offers — otherwise a
        # cow's history names semen the farm does not stock.
        bull_labels[farm_obj.id] = [f"{n} {c}" for n, c, _ in entries]
    await session.flush()

    cows: list[Cow] = []

    def add_cow(**kw) -> Cow:
        kw.setdefault("id", uuid.uuid4())
        kw.setdefault("sex", CalfSex.female)
        kw.setdefault("health_status", HealthStatus.healthy)
        cow = Cow(**kw)
        session.add(cow)
        cows.append(cow)
        return cow

    async def add_insemination(cow: Cow, when: date, bull: str, semen=SemenType.conventional,
                               attempt=1, set_last=True) -> Insemination:
        # cows.last_insemination_id <-> inseminations.cow_id is a mutual FK with
        # no ORM relationship, so stage the inserts: cow, then insemination,
        # then the back-reference update.
        await session.flush()
        ins = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=when, bull_name=bull,
                           semen_type=semen, attempt_number=attempt)
        session.add(ins)
        await session.flush()
        if set_last:
            cow.last_insemination_id = ins.id
            cow.last_insemination_date = when
            await session.flush()
        return ins

    # ── PREGNANT cows (AI + 283 = due, AI + 223 = dry) ─────
    ai = days_ago(120)
    c = add_cow(farm_id=gv.id, ear_tag="CA 124 578 1042", breed="Holstein",
                date_of_birth=date(2022, 3, 14), lactation_number=3, status=CowStatus.pregnant,
                current_program="Pregnant", last_calving_date=days_ago(300),
                due_date=days_from(ai, GESTATION), dry_date=days_from(ai, DRY_OFFSET))
    ins = await add_insemination(c, ai, "Delta-Lambda 7HO14454", SemenType.sexed, attempt=2)
    await session.flush()
    session.add(PregnancyCheck(id=uuid.uuid4(), cow_id=c.id, insemination_id=ins.id,
                               check_date=days_from(ai, 33), result=PregnancyResult.pregnant))

    ai = days_ago(95)
    c = add_cow(farm_id=sf.id, ear_tag="CA 118 442 2210", breed="Jersey",
                date_of_birth=date(2022, 8, 9), lactation_number=2, status=CowStatus.pregnant,
                current_program="Pregnant", last_calving_date=days_ago(280),
                due_date=days_from(ai, GESTATION), dry_date=days_from(ai, DRY_OFFSET))
    ins = await add_insemination(c, ai, "Listowel 7JE01893")
    await session.flush()
    session.add(PregnancyCheck(id=uuid.uuid4(), cow_id=c.id, insemination_id=ins.id,
                               check_date=days_from(ai, 32), result=PregnancyResult.pregnant))

    # ── DRY cow (past day 223, dry_date in the past) ───────
    ai = days_ago(240)
    c = add_cow(farm_id=mr.id, ear_tag="CA 131 209 2755", breed="Holstein",
                date_of_birth=date(2020, 9, 12), lactation_number=4, status=CowStatus.dry,
                current_program="Dry", last_calving_date=days_ago(330),
                due_date=days_from(ai, GESTATION), dry_date=days_from(ai, DRY_OFFSET))
    ins = await add_insemination(c, ai, "Tahiti 551HO03693")
    await session.flush()
    session.add(PregnancyCheck(id=uuid.uuid4(), cow_id=c.id, insemination_id=ins.id,
                               check_date=days_from(ai, 32), result=PregnancyResult.pregnant))

    # ── FRESH cows (recent calving; one inside 30–50d vaccination window) ──
    fresh1 = add_cow(farm_id=gv.id, ear_tag="CA 124 578 1156", breed="Holstein",
                     date_of_birth=date(2023, 1, 22), lactation_number=2, status=CowStatus.fresh,
                     current_program="Fresh", last_calving_date=days_ago(35))
    add_cow(farm_id=mr.id, ear_tag="CA 131 209 2988", breed="Holstein",
            date_of_birth=date(2022, 10, 30), lactation_number=1, status=CowStatus.fresh,
            current_program="Fresh", last_calving_date=days_ago(12))

    # ── INSEMINATED cow inside the 19–25 day heat window ───
    ai = days_ago(21)
    c = add_cow(farm_id=mr.id, ear_tag="CA 131 209 3120", breed="Holstein",
                date_of_birth=date(2022, 5, 19), lactation_number=2, status=CowStatus.inseminated,
                current_program="Inseminated", last_calving_date=days_ago(175))
    await add_insemination(c, ai, "Parfect 200HO12128")

    # ── INSEMINATED, Day 35 — on the Pregnancy Report (due for vet check) ──
    c = add_cow(farm_id=gv.id, ear_tag="CA 124 578 1180", breed="Holstein",
                date_of_birth=date(2022, 2, 3), lactation_number=3, status=CowStatus.inseminated,
                current_program="Inseminated", last_calving_date=days_ago(190))
    await add_insemination(c, days_ago(35), "Delta-Lambda 7HO14454")

    # ── INSEMINATED, Day 55 — Pregnancy Check Warning (overdue 50+) ──
    c = add_cow(farm_id=gv.id, ear_tag="CA 124 578 1205", breed="Holstein",
                date_of_birth=date(2021, 12, 19), lactation_number=4, status=CowStatus.inseminated,
                current_program="Inseminated", last_calving_date=days_ago(210))
    await add_insemination(c, days_ago(55), "Mogul-Son 29HO18923")

    # ── OPEN cows: one healthy (ready to breed), one sick (recheck due) ──
    add_cow(farm_id=gv.id, ear_tag="CA 124 578 0902", breed="Holstein",
            date_of_birth=date(2021, 6, 2), lactation_number=3, status=CowStatus.open,
            current_program="Open", last_calving_date=days_ago(80))
    add_cow(farm_id=sf.id, ear_tag="CA 118 442 2401", breed="Jersey",
            date_of_birth=date(2021, 9, 14), lactation_number=2, status=CowStatus.open,
            health_status=HealthStatus.sick, recheck_due_date=days_from(TODAY, 4),
            current_program="Open", last_calving_date=days_ago(95), notes="Lame — rechecking before breeding.")

    # ── NEEDLING cow with an active Ovsynch enrollment + a record due today ──
    needle = add_cow(farm_id=gv.id, ear_tag="CA 124 578 0877", breed="Holstein",
                     date_of_birth=date(2021, 11, 2), lactation_number=4, status=CowStatus.needling,
                     current_program="Ovsynch", last_calving_date=days_ago(128))
    await session.flush()
    enr = NeedlingEnrollment(id=uuid.uuid4(), cow_id=needle.id, protocol=ProtocolType.ovsynch,
                             start_date=days_ago(6), current_day=7, status=EnrollmentStatus.active)
    session.add(enr)
    await session.flush()
    session.add_all([
        NeedlingRecord(id=uuid.uuid4(), enrollment_id=enr.id, cow_id=needle.id, protocol_day=1,
                       scheduled_date=days_ago(6), completed=True, completed_date=days_ago(6),
                       treatment="2cc GnRH"),
        # Day 7 PGF is due today → appears on Needling report / tasks
        NeedlingRecord(id=uuid.uuid4(), enrollment_id=enr.id, cow_id=needle.id, protocol_day=7,
                       scheduled_date=TODAY, completed=False, treatment="2cc PGF"),
        NeedlingRecord(id=uuid.uuid4(), enrollment_id=enr.id, cow_id=needle.id, protocol_day=10,
                       scheduled_date=days_from(TODAY, 3), completed=False, is_final=True,
                       treatment="2cc GnRH + Insemination"),
    ])

    # ── NEEDLING cow on her FINAL protocol day (Timed Breeding) ───────────
    # Exercises the same-day overlap rule: earlier shots are done and the final
    # day is today, so she appears ONLY on Timed Breeding with the injection
    # folded into the insemination task — never on the Needling report.
    tai = add_cow(farm_id=sf.id, ear_tag="CA 118 442 2480", breed="Jersey",
                  date_of_birth=date(2022, 4, 11), lactation_number=2,
                  status=CowStatus.needling, current_program="Ovsynch",
                  last_calving_date=days_ago(120))
    await session.flush()
    tai_enr = NeedlingEnrollment(id=uuid.uuid4(), cow_id=tai.id, protocol=ProtocolType.ovsynch,
                                 start_date=days_ago(9), current_day=10,
                                 status=EnrollmentStatus.active)
    session.add(tai_enr)
    await session.flush()
    session.add_all([
        NeedlingRecord(id=uuid.uuid4(), enrollment_id=tai_enr.id, cow_id=tai.id, protocol_day=1,
                       scheduled_date=days_ago(9), completed=True, completed_date=days_ago(9),
                       treatment="2cc GnRH"),
        NeedlingRecord(id=uuid.uuid4(), enrollment_id=tai_enr.id, cow_id=tai.id, protocol_day=7,
                       scheduled_date=days_ago(3), completed=True, completed_date=days_ago(3),
                       treatment="2cc PGF"),
        # Final day is TODAY → Timed Breeding only
        NeedlingRecord(id=uuid.uuid4(), enrollment_id=tai_enr.id, cow_id=tai.id, protocol_day=10,
                       scheduled_date=TODAY, completed=False, is_final=True,
                       treatment="2cc GnRH"),
    ])

    # ── CULL cow (with a cull record) ──────────────────────
    cull = add_cow(farm_id=mr.id, ear_tag="CA 131 209 2610", breed="Holstein",
                   date_of_birth=date(2019, 2, 27), lactation_number=6, status=CowStatus.cull,
                   current_program="Do Not Breed", last_calving_date=days_ago(250))
    await session.flush()
    session.add(CullRecord(id=uuid.uuid4(), cow_id=cull.id, cull_date=days_ago(20),
                           reason="Chronic lameness"))

    # ── A calf and a heifer (growing stock) ────────────────
    add_cow(farm_id=gv.id, ear_tag="CA 124 578 3301", breed="Holstein",
            date_of_birth=days_ago(40), lactation_number=0, status=CowStatus.calf,
            current_program="Calf")
    add_cow(farm_id=sf.id, ear_tag="CA 118 442 3110", breed="Jersey",
            date_of_birth=days_ago(400), lactation_number=0, status=CowStatus.heifer,
            current_program="Heifer")

    await session.flush()

    # ── The rest of the herd ───────────────────────────────
    # Everything above is hand-written: one cow per rule, so every report is
    # provably non-empty. That is a fixture, not a herd — with fifteen animals
    # a report shows a single row, and the client cannot tell a working screen
    # from a broken one. This fills each farm out to a real milking herd.
    #
    # Nothing here is a typed-in number: a cow gets a status from a plausible
    # mix, and every date is then derived from the same constants the app uses
    # (GESTATION, DRY_OFFSET, the protocol tables), so a generated cow lands on
    # exactly the reports her dates earn. How much work shows up today falls
    # out of that, rather than being set.
    rng = random.Random(20260908)  # fixed, so two runs produce the same herd

    HERD_PLAN = [
        # farm, cows to generate, ear-tag block (unique per farm)
        (gv, 62, "124 578"), (sf, 45, "118 442"), (mr, 71, "131 209"),
        (extra[0], 38, "142 331"), (extra[1], 30, "156 407"),
        (extra[2], 52, "163 522"), (extra[3], 26, "171 648"),
        (extra[4], 47, "184 719"), (extra[5], 33, "192 830"),
        (extra[6], 55, "205 946"), (extra[7], 28, "213 057"),
        (extra[8], 40, "227 168"),
    ]
    # Roughly what a well-run Ontario dairy looks like on any given day.
    STATUS_MIX = (
        [CowStatus.pregnant] * 34 + [CowStatus.inseminated] * 15 +
        [CowStatus.fresh] * 11 + [CowStatus.open] * 11 + [CowStatus.dry] * 9 +
        [CowStatus.needling] * 8 + [CowStatus.heifer] * 6 +
        [CowStatus.calf] * 4 + [CowStatus.cull] * 2
    )
    BREEDS = ["Holstein"] * 7 + ["Jersey"] * 2 + ["Holstein-Jersey"]
    SEMEN_MIX = [SemenType.conventional] * 6 + [SemenType.sexed] * 3 + [SemenType.beef]
    PROTOCOL_MIX = (
        [ProtocolType.ovsynch] * 5 + [ProtocolType.prostaglandin_heat] * 2 +
        [ProtocolType.double_ovsynch, ProtocolType.presynch, ProtocolType.general_synch]
    )
    CULL_REASONS = ["Chronic lameness", "Repeat breeder", "Low production",
                    "Mastitis — chronic high SCC", "Age"]

    generated: list[Cow] = []
    vaccinated: set = set()

    for farm_obj, count, block in HERD_PLAN:
        labels = bull_labels[farm_obj.id]
        for n in range(count):
            # Hand-written tags stop below 5000, so this block cannot collide.
            ear_tag = f"CA {block} {5000 + n:04d}"
            status = rng.choice(STATUS_MIX)
            breed = rng.choice(BREEDS)
            base = dict(farm_id=farm_obj.id, ear_tag=ear_tag, breed=breed)
            before = len(cows)

            if status is CowStatus.pregnant or status is CowStatus.dry:
                if status is CowStatus.pregnant:
                    # Confirmed pregnant through to nearly dry.
                    since_ai = rng.randint(40, DRY_OFFSET - 1)
                    program = "Pregnant"
                else:
                    # Past the dry-off day, still short of calving.
                    since_ai = rng.randint(DRY_OFFSET + 1, GESTATION - 10)
                    program = "Dry"
                ai_date = days_ago(since_ai)
                cow = add_cow(
                    **base, date_of_birth=days_ago(rng.randint(900, 2400)),
                    lactation_number=rng.randint(1, 5), status=status,
                    current_program=program,
                    last_calving_date=days_ago(since_ai + rng.randint(60, 110)),
                    due_date=days_from(ai_date, GESTATION),
                    dry_date=days_from(ai_date, DRY_OFFSET),
                )
                if status is CowStatus.dry:
                    # The Dry report keeps her up until the pen change is
                    # confirmed. Farms do confirm it, within a day or two, so
                    # leaving every dry cow unconfirmed turned a short daily
                    # list into a pile of every cow that had ever dried off.
                    dried = cow.dry_date
                    if (TODAY - dried).days > 3 and rng.random() < 0.9:
                        cow.dry_off_confirmed_date = days_from(dried, rng.randint(0, 3))
                ins = await add_insemination(cow, ai_date, rng.choice(labels),
                                             semen=rng.choice(SEMEN_MIX),
                                             attempt=rng.randint(1, 3))
                # The check that confirmed her — always already in the past,
                # because she is only pregnant once somebody has said so.
                session.add(PregnancyCheck(
                    id=uuid.uuid4(), cow_id=cow.id, insemination_id=ins.id,
                    check_date=days_from(ai_date, rng.randint(30, 38)),
                    result=PregnancyResult.pregnant,
                ))

            elif status is CowStatus.fresh:
                since_calving = rng.randint(1, 65)
                calved = days_ago(since_calving)
                cow = add_cow(
                    **base, date_of_birth=days_ago(rng.randint(900, 2400)),
                    lactation_number=rng.randint(1, 5), status=CowStatus.fresh,
                    current_program="Fresh", last_calving_date=calved,
                )
                await session.flush()
                male = rng.random() < 0.5
                calving = CalvingRecord(
                    id=uuid.uuid4(), cow_id=cow.id, calving_date=calved,
                    live_birth=True, still_birth=False,
                    calf_sex=CalfSex.male if male else CalfSex.female,
                    calf_ear_tag=None if male else f"CA {block} {7000 + n:04d}",
                    calf_sale_info="Sold to calf buyer" if male else None,
                )
                session.add(calving)
                await session.flush()
                # Post-calving vaccination: due 30–50 days after she calved, so
                # it is already done for the older fresh cows and still open for
                # the rest. That window is what puts her on the report.
                done = since_calving > 50
                session.add(VaccinationRecord(
                    id=uuid.uuid4(), cow_id=cow.id, calving_record_id=calving.id,
                    scheduled_date=days_from(calved, 30), completed=done,
                    completed_date=days_from(calved, rng.randint(30, 50)) if done else None,
                    vaccine_name="Bovi-Shield GOLD FP 5" if done else None,
                ))
                vaccinated.add(cow.id)

            elif status is CowStatus.open:
                sick = rng.random() < 0.12
                add_cow(
                    **base, date_of_birth=days_ago(rng.randint(900, 2400)),
                    lactation_number=rng.randint(1, 5), status=CowStatus.open,
                    current_program="Open",
                    last_calving_date=days_ago(rng.randint(70, 150)),
                    health_status=HealthStatus.sick if sick else HealthStatus.healthy,
                    recheck_due_date=days_from(TODAY, rng.randint(1, 7)) if sick else None,
                    notes="Under treatment — recheck before breeding." if sick else None,
                )

            elif status is CowStatus.inseminated:
                # A cow only stays "inseminated" until somebody diagnoses her:
                # after that she is pregnant or open. So most of them sit inside
                # the pre-check window, a working group is due for the vet, and
                # a few have run past day 50 — which is exactly the overdue
                # warning the Pregnancy report exists to raise. The heat window
                # (20–25 days) falls out of the first band on its own.
                since_ai = rng.choices(
                    [rng.randint(1, 31), rng.randint(32, 45), rng.randint(46, 60)],
                    weights=[6, 3, 1],
                )[0]
                attempt = rng.randint(1, 3)
                cow = add_cow(
                    **base, date_of_birth=days_ago(rng.randint(900, 2400)),
                    lactation_number=rng.randint(1, 5), status=CowStatus.inseminated,
                    current_program="Inseminated",
                    last_calving_date=days_ago(since_ai + rng.randint(70, 140)),
                )
                await add_insemination(cow, days_ago(since_ai), rng.choice(labels),
                                       semen=rng.choice(SEMEN_MIX), attempt=attempt)

            elif status is CowStatus.needling:
                protocol = rng.choice(PROTOCOL_MIX)
                steps = get_scheduled_records(protocol.value, TODAY)
                final_day = steps[-1]["protocol_day"]
                # Drop her somewhere inside the protocol rather than at the
                # start, so shots come due across the whole week instead of all
                # landing on the same day.
                elapsed = rng.randint(0, final_day - 1)
                start = days_ago(elapsed)
                cow = add_cow(
                    **base, date_of_birth=days_ago(rng.randint(900, 2400)),
                    lactation_number=rng.randint(1, 5), status=CowStatus.needling,
                    current_program=protocol.value,
                    last_calving_date=days_ago(elapsed + rng.randint(80, 160)),
                )
                await session.flush()
                enr = NeedlingEnrollment(
                    id=uuid.uuid4(), cow_id=cow.id, protocol=protocol,
                    start_date=start, current_day=elapsed + 1,
                    status=EnrollmentStatus.active,
                )
                session.add(enr)
                await session.flush()
                for step in get_scheduled_records(protocol.value, start):
                    past = step["scheduled_date"] < TODAY
                    session.add(NeedlingRecord(
                        id=uuid.uuid4(), enrollment_id=enr.id, cow_id=cow.id,
                        protocol_day=step["protocol_day"],
                        scheduled_date=step["scheduled_date"],
                        completed=past,
                        completed_date=step["scheduled_date"] if past else None,
                        treatment=step["treatment"], is_final=step["is_final"],
                    ))

            elif status is CowStatus.heifer:
                # Breeding age is day 395, so this range straddles it and some
                # of them are due to be bred.
                add_cow(
                    **base, date_of_birth=days_ago(rng.randint(70, 700)),
                    lactation_number=0, status=CowStatus.heifer,
                    current_program="Heifer",
                )

            elif status is CowStatus.calf:
                # A calf becomes a heifer at day 60; keep them under it.
                male = rng.random() < 0.2
                add_cow(
                    **base, date_of_birth=days_ago(rng.randint(1, 58)),
                    lactation_number=0, status=CowStatus.calf,
                    current_program="Calf",
                    sex=CalfSex.male if male else CalfSex.female,
                )

            else:  # cull
                cow = add_cow(
                    **base, date_of_birth=days_ago(rng.randint(1800, 3000)),
                    lactation_number=rng.randint(4, 7), status=CowStatus.cull,
                    current_program="Do Not Breed",
                    last_calving_date=days_ago(rng.randint(200, 320)),
                )
                await session.flush()
                session.add(CullRecord(id=uuid.uuid4(), cow_id=cow.id,
                                       cull_date=days_ago(rng.randint(1, 90)),
                                       reason=rng.choice(CULL_REASONS)))

            generated.extend(cows[before:])

    await session.flush()

    # The 2cc shot that was actually given.
    #
    # The Post Calving report keeps a cow visible for her whole lactation until
    # that shot is recorded — deliberately, so a miss escalates instead of
    # ageing out. Correct, but a herd where nobody has ever recorded one puts
    # every milking cow on the report, and 27 rows at a 75-cow farm is not what
    # a working dairy looks like. So record it for the cows whose window has
    # passed, and leave a realistic few outstanding: those are the misses the
    # report exists to catch.
    vacc_lo, vacc_hi = VACCINATION_WINDOW
    for cow in generated:
        if cow.id in vaccinated or cow.last_calving_date is None:
            continue
        if cow.status in (CowStatus.calf, CowStatus.heifer, CowStatus.cull):
            continue
        since = (TODAY - cow.last_calving_date).days
        if since < vacc_lo:
            # Not due yet — scheduled and waiting.
            session.add(VaccinationRecord(
                id=uuid.uuid4(), cow_id=cow.id,
                scheduled_date=days_from(cow.last_calving_date, vacc_lo),
                completed=False))
            continue
        if rng.random() < 0.07:
            continue  # genuinely missed; she stays on the report
        given = days_from(cow.last_calving_date, rng.randint(vacc_lo, vacc_hi))
        session.add(VaccinationRecord(
            id=uuid.uuid4(), cow_id=cow.id,
            scheduled_date=days_from(cow.last_calving_date, vacc_lo),
            completed=True, completed_date=given,
            vaccine_name="Bovi-Shield GOLD FP 5"))

    await session.flush()

    # The farm card shows herd_size, and the cow list shows the rows that
    # actually exist. Those were two unrelated numbers, so a farm advertised
    # 425 animals and listed five. Make the header tell the truth.
    for farm_obj in all_farms:
        farm_obj.herd_size = sum(1 for c in cows if c.farm_id == farm_obj.id)


    # ── A scheduled vaccination for the fresh cow (30–50d window) ──
    session.add(VaccinationRecord(id=uuid.uuid4(), cow_id=fresh1.id,
                                  scheduled_date=days_from(fresh1.last_calving_date, 30),
                                  completed=False))

    # ── Fresh-group calving record (history) ───────────────
    session.add(CalvingRecord(id=uuid.uuid4(), cow_id=fresh1.id, calving_date=fresh1.last_calving_date,
                              live_birth=True, still_birth=False, calf_sex=CalfSex.female,
                              calf_ear_tag="CA 124 578 4102", notes="Unassisted."))

    # ── Notifications ──────────────────────────────────────
    dry_cow = next(c for c in cows if c.status == CowStatus.dry)
    session.add_all([
        Notification(id=uuid.uuid4(), farm_id=dry_cow.farm_id, cow_id=dry_cow.id, type="dry_off",
                     message=f"{dry_cow.ear_tag} has dried off — move her to the dry pen.", read=False),
        Notification(id=uuid.uuid4(), farm_id=fresh1.farm_id, cow_id=fresh1.id, type="calving",
                     message=f"{fresh1.ear_tag} just calved — now Fresh.", read=True),
        Notification(id=uuid.uuid4(), farm_id=gv.id, cow_id=needle.id, type="open",
                     message=f"{needle.ear_tag} is Open and enrolled in Ovsynch.", read=False),
    ])

    # A week of alerts off the generated herd. Only the three types the backend
    # actually emits — dry_off, breeding_due and open — so the notification
    # settings toggles govern everything on the screen.
    recent_dry = [c for c in cows if c.status is CowStatus.dry and c.dry_date
                  and days_ago(9) <= c.dry_date <= TODAY]
    for c in recent_dry[:6]:
        session.add(Notification(
            id=uuid.uuid4(), farm_id=c.farm_id, cow_id=c.id, type="dry_off",
            message=f"{c.ear_tag} has dried off — move her to the dry pen.", read=False))
    ready = [c for c in cows if c.status is CowStatus.open and c.last_calving_date
             and (TODAY - c.last_calving_date).days >= 70
             and c.health_status is HealthStatus.healthy]
    for c in ready[:6]:
        session.add(Notification(
            id=uuid.uuid4(), farm_id=c.farm_id, cow_id=c.id, type="breeding_due",
            message=f"{c.ear_tag} is past 70 days fresh and ready to breed.", read=False))
    for c in ready[6:10]:
        session.add(Notification(
            id=uuid.uuid4(), farm_id=c.farm_id, cow_id=c.id, type="open",
            message=f"{c.ear_tag} is Open.", read=True))

    await session.flush()


async def main() -> None:
    _guard_destructive()
    # Use the SESSION pooler (port 5432) rather than the app's TRANSACTION
    # pooler (6543): session mode supports prepared statements, which asyncpg
    # needs. This is Supabase's recommended endpoint for migrations/seeds.
    seed_port = 5432 if settings.db_port == 6543 else settings.db_port
    db_url = (
        f"postgresql+asyncpg://{settings.db_user}:{quote_plus(settings.db_password)}"
        f"@{settings.db_host}:{seed_port}/{settings.db_name}"
    )
    engine = create_async_engine(db_url, poolclass=NullPool)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        await clear(session)
        await seed(session)
        await session.commit()

        # Report what landed.
        counts = {}
        for tbl in ("farms", "vets", "cows", "inseminations", "pregnancy_checks",
                    "needling_enrollments", "needling_records", "vaccination_records",
                    "cull_records", "notifications"):
            r = await session.execute(text(f"SELECT count(*) FROM {tbl}"))
            counts[tbl] = r.scalar()
        print("Seed complete:")
        for k, v in counts.items():
            print(f"  {k}: {v}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
