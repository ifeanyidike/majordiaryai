"""DairyComp 305 herd lists -> the app's cows (app/services/dairycomp.py).

Every row here is invented. The real export that shaped these rules (Oct
2026) is a farm's real herd and stays out of the repository.

A DairyComp LIST gives counts as of the day it was exported, so the export
day is the anchor for every date: EXPORT below. The import runs later
(TODAY), and statuses are decided on TODAY -- the farm's clock moved on.
"""

import uuid
from datetime import date, timedelta

import pytest

from app.models.models import Cow, CowStatus, Insemination
from app.services import dairycomp
from app.services.dairycomp import derive_export_date, parse_date, plan_rows
from app.services.status_engine import DRY_OFF_DAY, GESTATION_DAYS

EXPORT = date(2026, 10, 4)
TODAY = date(2026, 10, 6)


def dmy(d: date) -> str:
    """DairyComp's D/M/YY, padded the way it prints it."""
    return f"{d.day:>2}/{d.month:>2}/{d.year % 100:02d} "


def row(**kw):
    base = {"ID": 0.0, "TAG": "", "BNAME": "", "CREG": "", "CBRD": "", "GROUP": 1.0,
            "BDAT": dmy(date(2021, 3, 1)), "SIRE": "", "DID": 0.0, "RPRO": "",
            "DIM": 0.0, "DSLH": 0.0, "DOPN": 0.0, "DDAT": "", "DRY50": "",
            "LACT": 0.0, "TBRD": 0.0}
    base.update(kw)
    return base


def one(r, today=TODAY):
    plan = plan_rows([r], EXPORT, today)
    assert not plan.problems, plan.problems
    assert len(plan.cows) == 1, (plan.cows, plan.skipped)
    return plan.cows[0]


def preg_row(id_, bred: date, **kw):
    """A pregnant cow as DairyComp prints her: DRY50 is its 280-day due date
    less 50, DSLH the days since the heat she was bred on."""
    fields = dict(ID=float(id_), RPRO="PREG    ", LACT=2.0, DIM=200.0,
                  DSLH=float((EXPORT - bred).days),
                  DRY50=dmy(bred + timedelta(days=280 - 50)))
    fields.update(kw)
    return row(**fields)


# ── reading DairyComp's cells ────────────────────────────────────────

def test_dates_are_day_first_with_two_digit_years():
    assert parse_date("15/ 7/20 ", not_after=EXPORT) == date(2020, 7, 15)
    assert parse_date(" 1/10/26", not_after=EXPORT) == date(2026, 10, 1)
    # A two-digit year after the export is last century, not the future.
    assert parse_date(" 3/ 4/98", not_after=EXPORT) == date(1998, 4, 3)


def test_the_export_date_is_read_back_out_of_the_pregnant_cows():
    rows = [preg_row(1, date(2026, 6, 1)), preg_row(2, date(2026, 3, 20)),
            # A heat recorded after she was bred resets DSLH: an outlier.
            preg_row(3, date(2026, 5, 1), DSLH=12.0)]
    assert derive_export_date(rows) == EXPORT


def test_the_blank_line_and_the_total_footer_are_not_animals():
    rows = [row(ID=7.0, RPRO="HEIFER", BDAT=dmy(date(2026, 1, 1))),
            row(ID="", RPRO=""), row(ID="Total:", TAG=772.0)]
    plan = plan_rows(rows, EXPORT, TODAY)
    assert [c.ear_tag for c in plan.cows] == ["7"]
    assert not plan.problems and not plan.skipped


# ── statuses ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("age_days,status,program", [
    (30, CowStatus.calf, None),
    (200, CowStatus.heifer, None),
    # Master Structure: at 13 months she goes to the Insemination Program.
    (400, CowStatus.open, "Insemination"),
])
def test_a_heifer_is_placed_by_her_age(age_days, status, program):
    cow = one(row(ID=10.0, RPRO="HEIFER", BDAT=dmy(TODAY - timedelta(days=age_days))))
    assert cow.status == status
    assert cow.current_program == program
    assert cow.last_calving_date is None


@pytest.mark.parametrize("dc", ["NO BRED", "OK/OPEN"])
def test_an_unbred_heifer_is_a_heifer_not_a_cow_with_no_calving(dc):
    """DairyComp calls a heifer that was never bred (or did not take) NO BRED
    or OK/OPEN. With no lactation she has no calving date to count from."""
    cow = one(row(ID=11.0, RPRO=dc, LACT=0.0, BDAT=dmy(TODAY - timedelta(days=450))))
    assert cow.status == CowStatus.open
    assert cow.current_program == "Insemination"


def test_a_cow_is_fresh_until_day_70_then_open():
    young = one(row(ID=12.0, RPRO="FRESH", LACT=2.0, DIM=20.0))
    assert young.status == CowStatus.fresh
    assert young.last_calving_date == EXPORT - timedelta(days=20)

    old = one(row(ID=13.0, RPRO="NO BRED", LACT=2.0, DIM=120.0))
    assert old.status == CowStatus.open
    assert old.current_program is None  # the Open Cow Report, for a protocol


def test_a_bred_cow_gets_the_insemination_her_checks_are_filed_against():
    cow = one(row(ID=14.0, RPRO="BRED", LACT=1.0, DIM=110.0, DSLH=35.0, TBRD=2.0))
    assert cow.status == CowStatus.inseminated
    assert cow.insemination_date == EXPORT - timedelta(days=35)
    assert cow.attempt_number == 2
    assert cow.due_date is None  # only a confirmed pregnancy has one


def test_a_pregnant_cow_is_dated_by_the_apps_rules_not_dairycomps():
    bred = date(2026, 6, 1)
    cow = one(preg_row(15, bred))
    assert cow.status == CowStatus.pregnant
    assert cow.insemination_date == bred
    assert cow.due_date == bred + timedelta(days=GESTATION_DAYS)   # 283, not 280
    assert cow.dry_date == bred + timedelta(days=DRY_OFF_DAY)      # 223, not 230


def test_a_dry_cow_is_already_in_the_dry_pen():
    bred = date(2026, 2, 1)
    dried = date(2026, 9, 20)
    cow = one(preg_row(16, bred, RPRO="DRY     ", DDAT=dmy(dried)))
    assert cow.status == CowStatus.dry
    assert cow.dry_date == dried
    # Confirmed, so the Dry Report does not ask for a pen change made weeks ago.
    assert cow.dry_off_confirmed_date == dried


def test_dnb_puts_her_on_the_do_not_breed_list():
    cow = one(row(ID=17.0, RPRO="DNB", LACT=3.0, DIM=150.0))
    assert cow.do_not_breed is True
    assert cow.status == CowStatus.open


# ── who is left out ──────────────────────────────────────────────────

def test_bull_calves_are_held_out():
    plan = plan_rows([row(ID=52437.0, RPRO="BULLCAF", BDAT=dmy(date(2026, 9, 15)))],
                     EXPORT, TODAY)
    assert not plan.cows
    assert "bull calf" in plan.skipped[0].reason


def test_an_animal_that_never_calved_and_is_years_old_is_held_out_for_the_farm():
    """A dairy heifer calves at about two. One listed at six years old and
    never calved is almost always an animal that left and was never removed;
    putting her on the breeding list would send the technician after a cow
    that is not there."""
    plan = plan_rows([row(ID=3118.0, RPRO="HEIFER", BDAT=dmy(date(2020, 6, 18)))],
                     EXPORT, TODAY)
    assert not plan.cows
    assert plan.skipped[0].age_months >= 70
    assert "confirm she is still on the farm" in plan.skipped[0].reason
    # ...unless whoever runs the import says keep them all.
    kept = plan_rows([row(ID=3118.0, RPRO="HEIFER", BDAT=dmy(date(2020, 6, 18)))],
                     EXPORT, TODAY, oldest_uncalved_days=None)
    assert len(kept.cows) == 1


def test_a_repeated_id_is_reported_not_imported_twice():
    plan = plan_rows([row(ID=20.0, RPRO="HEIFER", BDAT=dmy(date(2026, 1, 1))),
                      row(ID=20.0, RPRO="HEIFER", BDAT=dmy(date(2026, 2, 1)))],
                     EXPORT, TODAY)
    assert len(plan.cows) == 1
    assert "also appears" in plan.problems[0][2]


# ── parentage ────────────────────────────────────────────────────────

def test_maternal_sire_is_her_mothers_sire_when_her_mother_is_in_the_herd():
    rows = [row(ID=249.0, RPRO="DRY", LACT=3.0, DIM=300.0, SIRE="SHAMROCK", DSLH=200.0),
            row(ID=33.0, RPRO="HEIFER", SIRE="POPSTAR", DID=249.0,
                BDAT=dmy(date(2026, 3, 25))),
            row(ID=34.0, RPRO="HEIFER", SIRE="POPSTAR", DID=9999.0,
                BDAT=dmy(date(2026, 3, 27)))]
    cows = {c.ear_tag: c for c in plan_rows(rows, EXPORT, TODAY).cows}
    assert cows["33"].sire == "POPSTAR"
    assert cows["33"].maternal_sire == "SHAMROCK"
    assert cows["34"].maternal_sire is None   # mother not in this herd


# ── writing ──────────────────────────────────────────────────────────

async def test_writing_adds_cows_with_their_inseminations_and_never_overwrites(db, farm):
    from sqlalchemy import select

    # Already on the farm, with something the app recorded since the export.
    db.add(Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="14", status=CowStatus.pregnant,
               lactation_number=1))
    await db.flush()

    plan = plan_rows([
        row(ID=14.0, RPRO="BRED", LACT=1.0, DIM=110.0, DSLH=35.0),
        preg_row(15, date(2026, 6, 1)),
        row(ID=12.0, RPRO="FRESH", LACT=2.0, DIM=20.0),
    ], EXPORT, TODAY)
    added, already = await dairycomp.write_plan(db, farm.id, plan, EXPORT)

    assert already == ["14"]
    assert {p.ear_tag for p in added} == {"15", "12"}
    kept = (await db.execute(select(Cow).where(Cow.farm_id == farm.id, Cow.ear_tag == "14"))
            ).scalar_one()
    assert kept.status == CowStatus.pregnant  # the app's record, untouched

    preg = (await db.execute(select(Cow).where(Cow.farm_id == farm.id, Cow.ear_tag == "15"))
            ).scalar_one()
    ins = await db.get(Insemination, preg.last_insemination_id)
    assert ins.date == date(2026, 6, 1) and ins.cow_id == preg.id


# ── the Vaccine Report after an import ───────────────────────────────

def test_a_cow_added_after_her_vaccine_window_is_not_chased_for_it():
    """The export carries no vaccination history. Without this every calved
    cow arrived 'overdue' for the post-calving shot -- 161 of them on the
    first real farm -- a list nobody can act on."""
    from datetime import datetime, timezone

    from app.services.report_catalog import WorklistContext, build_reports

    def cow(dim, created_days_ago):
        return Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(),
                   ear_tag=f"V{dim}-{created_days_ago}",
                   status=CowStatus.open, lactation_number=2,
                   last_calving_date=TODAY - timedelta(days=dim),
                   created_at=datetime.combine(TODAY - timedelta(days=created_days_ago),
                                               datetime.min.time(), tzinfo=timezone.utc))

    imported_late = cow(dim=120, created_days_ago=1)   # window long gone at import
    imported_in_window = cow(dim=40, created_days_ago=1)
    known_since_calving = cow(dim=120, created_days_ago=200)

    reports = {r["type"]: r for r in build_reports(WorklistContext(
        today=TODAY, role="technician",
        cows=[imported_late, imported_in_window, known_since_calving]))}
    on_report = {c["ear_tag"] for c in reports["post-calving"]["cows"]}
    assert on_report == {imported_in_window.ear_tag, known_since_calving.ear_tag}


# ── the dry run keeps nothing ────────────────────────────────────────

async def test_a_dry_run_keeps_nothing_even_when_the_sweep_commits(engine, monkeypatch):
    """The lifecycle sweep commits its own transitions. The first dry run of
    the script went through a plain session, so that commit kept the whole
    import -- 563 cows in what was meant to be a rehearsal -- and would have
    emailed the farm. It must leave the database exactly as it found it."""
    from argparse import Namespace

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import Farm, Notification
    from app.services import notifications, push
    from scripts import import_dairycomp

    # The dry run switches delivery off for the rest of its process; put it
    # back afterwards so other tests keep their own fixtures' behaviour.
    monkeypatch.setattr(notifications, "_schedule_email", notifications._schedule_email)
    monkeypatch.setattr(push, "_schedule", push._schedule)

    name = f"Dry Run Farm {uuid.uuid4().hex[:6]}"
    # A pregnant cow well past her dry-off day: the sweep WILL move her and
    # commit, which is the path that leaked.
    plan = plan_rows([preg_row(1, date(2026, 1, 5))], EXPORT, TODAY)
    args = Namespace(farm_id=None, farm_name=name, create_farm=False, owner_name=None,
                     apply=False, held_out_csv=None)

    await import_dairycomp._dry_run(engine, args, plan, EXPORT, TODAY)

    async with AsyncSession(engine) as check:
        farms = (await check.execute(select(func.count()).select_from(Farm)
                                     .where(Farm.name == name))).scalar()
        notes = (await check.execute(select(func.count()).select_from(Notification)
                                     .join(Farm, Farm.id == Notification.farm_id)
                                     .where(Farm.name == name))).scalar()
    assert farms == 0
    assert notes == 0
