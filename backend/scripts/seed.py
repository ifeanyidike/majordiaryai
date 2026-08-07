"""
Seed the database with realistic dummy herd data.

Idempotent: clears the domain tables (NOT users / auth) and re-inserts a fresh
dataset covering every cow lifecycle stage, so all reports and profiles have
content. All user/technician/vet-account references are left NULL because
`users.id` references Supabase `auth.users` — real accounts are created through
the app's sign-up flow. Log in as an ADMIN to see the full seeded herd.

Run:  cd backend && .venv/bin/python -m scripts.seed
"""

import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from urllib.parse import quote_plus

from app.core.config import settings
from app.services.visits import weekdays_for
from app.models.models import (
    CalfSex, CalvingRecord, Cow, CowStatus, EnrollmentStatus, Farm, HealthStatus,
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
    "needling_enrollments", "farm_visit_assignments",
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
    session.add_all([gv, sf, mr])
    await session.flush()

    # ── Vets (no user account — user_id NULL) ──────────────
    v1 = Vet(id=uuid.uuid4(), name="Dr. Sarah Mitchell", clinic="Heartland Veterinary Services",
             phone="+1 (519) 555-0221", email="s.mitchell@heartlandvet.ca")
    v2 = Vet(id=uuid.uuid4(), name="Dr. James Carter", clinic="Oxford County Animal Health",
             phone="+1 (519) 555-0246", email="j.carter@oxfordvets.ca")
    session.add_all([v1, v2])
    await session.flush()
    session.add_all([
        VetFarmAssignment(vet_id=v1.id, farm_id=gv.id),
        VetFarmAssignment(vet_id=v1.id, farm_id=mr.id),
        VetFarmAssignment(vet_id=v2.id, farm_id=sf.id),
    ])

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
    from app.models.models import CullRecord
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

    await session.flush()


async def main() -> None:
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
