"""The Sept 17 client rules, each tested at the seam where it can go wrong.

  * a farm that gives its own last hormone (self_inject_needling)
  * calving telling the farm, the way dry-off already did
  * the pregnancy check coming due, told once and not once per sweep
  * a heat event demanding insemination the SAME day, rota or no rota
  * a cow answering to her name as well as her tag
"""

import uuid
from datetime import date, timedelta

import pytest

from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, EnrollmentStatus, Farm, HeatCheck, Insemination,
    NeedlingEnrollment, NeedlingRecord, Notification, ProtocolType, User, UserRole,
)
from app.services import status_engine
from app.services.protocols import get_final_day, self_inject_step
from app.services.report_catalog import WorklistContext, build_reports

TODAY = local_today()


def _reports(**ctx_kwargs) -> dict:
    """type -> the report's rows, for whatever context the test builds."""
    ctx = WorklistContext(today=TODAY, role="technician", **ctx_kwargs)
    return {r["type"]: r for r in build_reports(ctx)}


# ── the farmer's own injection ───────────────────────────────────────

async def test_a_self_injecting_farm_gets_the_last_hormone_the_day_before(
    db, farm, api, make_user,
):
    """Ovsynch's last day is one hormone plus the insemination, given together.
    A farm doing its own needling takes the hormone the day before and leaves
    the insemination to the technician — so the final step splits in two.
    """
    tech = await make_user(UserRole.technician)
    farm.self_inject_needling = True
    farm.assigned_technician_id = tech.id
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="SELF-1",
              status=CowStatus.open, lactation_number=1)
    db.add(cow)
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch",
            "start_date": TODAY.isoformat(),
        })
    assert r.status_code == 201, r.text

    from sqlalchemy import select
    records = (await db.execute(
        select(NeedlingRecord).where(NeedlingRecord.cow_id == cow.id)
        .order_by(NeedlingRecord.protocol_day)
    )).scalars().all()

    mine = [r for r in records if r.self_administered]
    assert len(mine) == 1, [(r.protocol_day, r.self_administered) for r in records]
    farmers = mine[0]
    assert farmers.protocol_day == get_final_day("ovsynch") - 1 == 9
    assert farmers.scheduled_date == TODAY + timedelta(days=8)
    # The hormone alone — the insemination stays with the technician on day 10.
    assert farmers.treatment == "2cc GnRH"
    assert "Insemination" not in farmers.treatment


async def test_the_farm_is_told_which_cow_needs_which_hormone(db, farm, api, make_user):
    """The point of the arrangement: the farmer cannot give a shot nobody
    named to them."""
    tech = await make_user(UserRole.technician)
    farm.self_inject_needling = True
    farm.assigned_technician_id = tech.id
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="SELF-2", name="Bluebell",
              status=CowStatus.open, lactation_number=1)
    db.add(cow)
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch",
            "start_date": TODAY.isoformat(),
        })

    from sqlalchemy import select
    notes = (await db.execute(
        select(Notification).where(Notification.cow_id == cow.id)
    )).scalars().all()
    assert [n.type for n in notes] == ["self_inject"]
    message = notes[0].message
    assert "2cc GnRH" in message
    # Named as the farm knows her, with the tag still there to remove all doubt.
    assert "Bluebell" in message and "SELF-2" in message


async def test_an_ordinary_farm_gets_no_extra_shot(db, farm, api, make_user):
    """Off by default: every existing farm keeps exactly today's schedule."""
    tech = await make_user(UserRole.technician)
    assert farm.self_inject_needling is False
    farm.assigned_technician_id = tech.id
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="ORD-1",
              status=CowStatus.open, lactation_number=1)
    db.add(cow)
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch",
            "start_date": TODAY.isoformat(),
        })

    from sqlalchemy import select
    records = (await db.execute(
        select(NeedlingRecord).where(NeedlingRecord.cow_id == cow.id)
    )).scalars().all()
    assert [r.protocol_day for r in sorted(records, key=lambda r: r.protocol_day)] == [1, 7, 10]
    assert not any(r.self_administered for r in records)


def test_a_protocol_with_no_fixed_ai_day_is_never_split():
    """Prostaglandin Heat ends on observed heat — inseminate only IF she is in
    heat. There is no day to inject "the day before", and inventing one would
    have the farmer giving a hormone for an insemination that may not happen.
    """
    assert self_inject_step("prostaglandin_heat", TODAY) is None
    assert self_inject_step("ovsynch", TODAY) is not None


async def test_the_farmers_shot_stays_off_the_technicians_injection_report(
    db, farm, api, make_user,
):
    """He does not give it. Counting it onto his route sends him out for a
    shot that is not his — and marks the farm's work as his to do."""
    tech = await make_user(UserRole.technician)
    farm.self_inject_needling = True
    farm.assigned_technician_id = tech.id
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="SELF-3",
              status=CowStatus.open, lactation_number=1)
    db.add(cow)
    await db.flush()

    # Start it so that the farmer's day-9 shot falls TODAY.
    start = TODAY - timedelta(days=8)
    async with api("technician", user_id=tech.id) as client:
        await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch",
            "start_date": start.isoformat(),
        })

    from app.services.worklists import needling_due_stmt
    from sqlalchemy import select

    due = (await db.execute(
        needling_due_stmt(TODAY).where(Cow.id == cow.id)
    )).all()
    assert all(not record.self_administered for record, _ in due), (
        "the farmer's own shot was put on the technician's route"
    )


def test_the_technician_is_prompted_to_leave_the_note():
    """The shot is the farm's; telling them exactly what to give is his, and
    it has to happen while he is standing there."""
    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="N-1",
              status=CowStatus.needling, lactation_number=1)
    reports = _reports(
        cows=[cow],
        farmer_injections={str(cow.id): {
            "id": str(uuid.uuid4()), "treatment": "2cc GnRH",
            "scheduled_date": TODAY + timedelta(days=1), "days_until": 1,
        }},
    )
    row = reports["farmer-injection"]["cows"][0]
    assert "note" in row["action"].lower()
    assert "2cc GnRH" in row["action"]
    assert row["farm_administered"] is True
    # It is his work, so it belongs on the To-Do count.
    assert reports["farmer-injection"]["is_work_report"] is True


def test_a_farmers_shot_whose_day_has_passed_with_no_note_is_overdue():
    """Past its date and still nobody told them: that is a missed shot, not a
    quiet row at the bottom of a list."""
    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="N-2",
              status=CowStatus.needling, lactation_number=1)
    reports = _reports(
        cows=[cow],
        farmer_injections={str(cow.id): {
            "id": str(uuid.uuid4()), "treatment": "2cc GnRH",
            "scheduled_date": TODAY - timedelta(days=2), "days_until": -2,
        }},
    )
    assert reports["farmer-injection"]["cows"][0]["overdue"] is True


# ── calving ──────────────────────────────────────────────────────────

async def test_calving_tells_the_farm_she_is_back_in_the_milking_herd(db, farm):
    """Dry-off has always notified; calving — the other end of the same pen
    change — silently did not."""
    from sqlalchemy import select

    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="CALV-1",
              status=CowStatus.pregnant, lactation_number=2,
              last_insemination_date=TODAY - timedelta(days=283))
    db.add(cow)
    await db.flush()

    await status_engine.on_calving(cow, TODAY, db)
    await db.flush()

    notes = (await db.execute(
        select(Notification).where(Notification.cow_id == cow.id)
    )).scalars().all()
    assert [n.type for n in notes] == ["calving"]
    assert "fresh" in notes[0].message.lower()
    assert cow.status is CowStatus.fresh


# ── the pregnancy check coming due ───────────────────────────────────

async def test_the_farm_is_told_when_a_check_falls_due(db, farm):
    from sqlalchemy import select

    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="PC-1",
              status=CowStatus.inseminated, lactation_number=1,
              last_insemination_date=TODAY - timedelta(
                  days=status_engine.PREGNANCY_REPORT_DAY))
    db.add(cow)
    await db.flush()

    await status_engine.run_lifecycle_transitions(db, farm_ids=[farm.id], today=TODAY)

    notes = (await db.execute(
        select(Notification).where(Notification.cow_id == cow.id)
    )).scalars().all()
    assert [n.type for n in notes] == ["preg_check"]


async def test_the_check_reminder_is_sent_once_not_once_per_sweep(db, farm):
    """The sweep runs several times a day. "Due for a check" arriving four
    times before lunch is how a farmer learns to ignore the feed."""
    from sqlalchemy import select

    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="PC-2",
              status=CowStatus.inseminated, lactation_number=1,
              last_insemination_date=TODAY - timedelta(
                  days=status_engine.PREGNANCY_REPORT_DAY))
    db.add(cow)
    await db.flush()

    for _ in range(3):
        await status_engine.run_lifecycle_transitions(db, farm_ids=[farm.id], today=TODAY)

    notes = (await db.execute(
        select(Notification).where(
            Notification.cow_id == cow.id, Notification.type == "preg_check")
    )).scalars().all()
    assert len(notes) == 1, f"sent {len(notes)} times"


async def test_a_cow_short_of_the_day_is_not_reminded_yet(db, farm):
    from sqlalchemy import select

    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="PC-3",
              status=CowStatus.inseminated, lactation_number=1,
              last_insemination_date=TODAY - timedelta(
                  days=status_engine.PREGNANCY_REPORT_DAY - 1))
    db.add(cow)
    await db.flush()

    await status_engine.run_lifecycle_transitions(db, farm_ids=[farm.id], today=TODAY)

    notes = (await db.execute(
        select(Notification).where(Notification.cow_id == cow.id)
    )).scalars().all()
    assert notes == []


# ── a heat event is same-day work ────────────────────────────────────

def test_a_cow_in_heat_is_bred_today_whatever_the_rota_says():
    """She is fertile for hours, not days. The Mon/Tue/Sat breeding rota moves
    routine work; it cannot move a heat, because the window shuts long before
    the next breeding day comes round.
    """
    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="H-1",
              status=CowStatus.open, current_program="Insemination",
              lactation_number=2, last_insemination_date=TODAY - timedelta(days=21))
    reports = _reports(cows=[cow], heat_events={str(cow.id): {"detected_on": TODAY}})

    row = reports["insemination"]["cows"][0]
    assert "TODAY" in row["action"]
    assert row["overdue"] is False


def test_a_heat_from_yesterday_reads_as_late():
    """A heat that was not bred on the day is a missed cycle — three weeks of
    lost days — so it must not look like ordinary pending work."""
    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="H-2",
              status=CowStatus.open, current_program="Insemination",
              lactation_number=2, last_insemination_date=TODAY - timedelta(days=22))
    reports = _reports(
        cows=[cow], heat_events={str(cow.id): {"detected_on": TODAY - timedelta(days=1)}},
    )

    row = reports["insemination"]["cows"][0]
    assert row["overdue"] is True
    assert "1 day ago" in row["action"]


def test_a_heifer_of_age_is_not_reported_as_a_missed_heat():
    """She reaches the Insemination Program by age, not by showing heat.
    Dating urgency from a heat she never had would report her weeks late."""
    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="H-3",
              status=CowStatus.open, current_program="Insemination",
              lactation_number=0)
    reports = _reports(cows=[cow], heat_events={})

    row = reports["insemination"]["cows"][0]
    assert row["overdue"] is False
    assert "first breeding" in row["action"].lower()


# ── a cow's name ─────────────────────────────────────────────────────

def test_a_named_cow_keeps_her_tag_in_the_label():
    """The name is an alias. The tag is the identity — it carries the unique
    constraint and it is what every other system knows her by — so it never
    disappears from how she is announced."""
    named = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="CA 124 578 1042",
                name="Bluebell", status=CowStatus.open, lactation_number=1)
    unnamed = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="CA 124 578 1043",
                  status=CowStatus.open, lactation_number=1)

    assert named.label == "Bluebell (CA 124 578 1042)"
    assert unnamed.label == "CA 124 578 1043"


def test_every_report_row_carries_both_the_name_and_the_tag():
    """Whichever a farm uses, the row has it — the app should never have to
    fetch the cow again just to print her name."""
    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="CA 999",
              name="Daisy", status=CowStatus.open, current_program="Insemination",
              lactation_number=1)
    row = _reports(cows=[cow], heat_events={})["insemination"]["cows"][0]

    assert row["ear_tag"] == "CA 999"
    assert row["name"] == "Daisy"
    assert row["label"] == "Daisy (CA 999)"


# ── the vaccine report on a self-vaccinating farm ────────────────────

def _post_calving_cow() -> Cow:
    return Cow(
        id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="V-1",
        status=CowStatus.fresh, lactation_number=2,
        last_calving_date=TODAY - timedelta(days=35),
    )


def test_a_self_vaccinating_farm_is_reminded_rather_than_visited():
    cow = _post_calving_cow()
    row = _reports(cows=[cow], farm_self_vaccinate=True)["post-calving"]["cows"][0]

    assert row["farm_administered"] is True
    assert "remind" in row["action"].lower()


def test_an_ordinary_farm_still_has_the_technician_give_it():
    cow = _post_calving_cow()
    row = _reports(cows=[cow], farm_self_vaccinate=False)["post-calving"]["cows"][0]

    assert row["farm_administered"] is False
    assert "give" in row["action"].lower()


def test_the_vaccine_report_is_named_for_the_vaccine():
    """Renamed from "Post Calving Report" per the client. The other vaccination
    report is renamed at the same time, because two reports called almost the
    same thing on one farm screen is worse than either old name."""
    from app.services.report_catalog import REPORTS

    titles = {r.type: r.title for r in REPORTS}
    assert titles["post-calving"] == "Vaccine Report"
    assert titles["vaccination"] == "Scheduled Vaccinations"
    assert titles["needling"] == "Injection Report"
    assert len(set(titles.values())) == len(titles), "two reports share a title"


# ── the wire itself ──────────────────────────────────────────────────

def test_the_worklist_schema_passes_through_every_field_the_builder_sets():
    """A field the builder sets but the response model omits is dropped
    silently — the row still validates, it is simply missing.

    That is exactly what happened to `name`, `label` and `farm_administered`:
    the builder attached them, the endpoint returned rows without them, and
    nothing failed. Every screen quietly fell back to the bare ear tag.
    """
    from app.schemas.reports import WorklistCow

    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="W-1", name="Daisy",
              status=CowStatus.open, current_program="Insemination",
              lactation_number=1)
    row = _reports(cows=[cow], heat_events={})["insemination"]["cows"][0]

    missing = set(row) - set(WorklistCow.model_fields)
    assert not missing, (
        "app/schemas/reports.py WorklistCow drops fields the builder sets: "
        f"{sorted(missing)}"
    )


def test_the_needling_record_schema_carries_who_gives_the_shot():
    """Same trap, other endpoint: without this the app shows the farm's own
    shot as a job for the technician."""
    from app.schemas.needling import NeedlingRecordOut

    assert "self_administered" in NeedlingRecordOut.model_fields
