"""Josh's Oct 2 / Oct 4 changes: a cow seen in heat is bred that day.

    Heat Detected -- Yes   -> on Today's Breed Report at once
    inseminated             -> off the report; on the Heat Report 19 days later
    not bred by next day    -> gone, "assume nothing happened"

Not bred at all if she is under 60 days post calving, on the Do Not Breed or
Do Not Inseminate list, a cull, or under 13 months old. The tests below are
the ways those rules fail quietly: a cow kept off the report who should be on
it, one left on it the day after, one whose program is wrecked by a heat
nobody acted on.
"""

import uuid
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import select

from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, HeatCheck, Insemination, Notification, UserRole,
)
from app.services.report_catalog import REPORTS, WorklistContext, build_reports

TODAY = local_today()


def _reports(cows, heat_today=()) -> dict:
    ctx = WorklistContext(
        today=TODAY, role="technician", cows=cows,
        heat_events={str(c.id): {"detected_on": TODAY} for c in heat_today},
    )
    return {r["type"]: r for r in build_reports(ctx)}


def _cow(**kw) -> Cow:
    kw.setdefault("status", CowStatus.open)
    kw.setdefault("lactation_number", 2)
    kw.setdefault("last_calving_date", TODAY - timedelta(days=120))
    return Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(),
               ear_tag=f"B-{uuid.uuid4().hex[:6]}", **kw)


def _on_breed_today(cow) -> bool:
    rows = _reports([cow], heat_today=[cow]).get("breed-today", {"cows": []})["cows"]
    return any(r["cow_id"] == str(cow.id) for r in rows)


# ── who goes on the report ───────────────────────────────────────────

@pytest.mark.parametrize("fields,expected", [
    ({}, True),
    ({"do_not_breed": True}, False),
    ({"do_not_inseminate": True}, False),
    ({"last_calving_date": TODAY - timedelta(days=59)}, False),
    ({"last_calving_date": TODAY - timedelta(days=60)}, True),
    # A heifer: never calved, so only her age can keep her off.
    ({"status": CowStatus.heifer, "lactation_number": 0, "last_calving_date": None,
      "date_of_birth": TODAY - timedelta(days=394)}, False),
    ({"status": CowStatus.heifer, "lactation_number": 0, "last_calving_date": None,
      "date_of_birth": TODAY - timedelta(days=395)}, True),
    # Most milking cows are entered with no birth date. "We don't know" is
    # not a reason to waste a heat.
    ({"date_of_birth": None, "last_calving_date": None}, True),
    ({"status": CowStatus.needling}, True),
    ({"status": CowStatus.cull}, False),
])
def test_who_goes_on_todays_breed_report(fields, expected):
    assert _on_breed_today(_cow(**fields)) is expected


def test_she_leaves_the_report_when_she_is_bred():
    cow = _cow(status=CowStatus.inseminated, last_insemination_date=TODAY)
    assert _on_breed_today(cow) is False


def test_a_cow_on_the_breed_report_is_not_also_asked_for_a_protocol():
    """Two instructions for one cow on one visit -- breed her, and pick her a
    protocol -- is how the wrong one gets done."""
    cow = _cow()
    reports = _reports([cow], heat_today=[cow])
    assert "open-report" not in reports
    # Tomorrow, with no heat today, she is back where she was.
    assert _reports([cow])["open-report"]["cows"][0]["cow_id"] == str(cow.id)


@pytest.mark.parametrize("flag", ["do_not_breed", "do_not_inseminate"])
def test_a_cow_on_either_list_is_given_no_breeding_work(flag):
    """"Do not breed" cannot be followed by a report telling the technician to
    pick her a protocol (which ends in a timed AI) or to breed her."""
    open_cow = _cow(**{flag: True})
    heifer = _cow(**{flag: True}, current_program="Insemination", lactation_number=0,
                  last_calving_date=None)
    reports = _reports([open_cow, heifer])
    assert "open-report" not in reports
    assert "insemination" not in reports
    # Still on the reference list -- she has not vanished from the herd.
    assert {r["cow_id"] for r in reports["open"]["cows"]} == {str(open_cow.id), str(heifer.id)}


def test_the_reports_are_named_as_josh_names_them():
    titles = {r.type: r.title for r in REPORTS}
    assert titles["timed-breeding"] == "Timed Breeding Report"
    assert titles["breed-today"] == "Today's Breed Report"
    order = [r.type for r in REPORTS]
    # Straight after the report whose "Yes" fills it.
    assert order.index("breed-today") == order.index("heat") + 1


# ── through the API ──────────────────────────────────────────────────

@pytest.fixture
async def tech(db, farm, make_user):
    t = await make_user(UserRole.technician)
    farm.assigned_technician_id = t.id
    await db.flush()
    return t


async def _add(db, cow):
    db.add(cow)
    await db.flush()
    return cow


def _farm_cow(farm, **kw) -> Cow:
    cow = _cow(**kw)
    cow.farm_id = farm.id
    return cow


async def _worklist(client, farm) -> dict:
    r = await client.get("/reports/worklist", params={"farm_id": str(farm.id)})
    assert r.status_code == 200, r.text
    (f,) = [f for f in r.json()["farms"] if f["farm_id"] == str(farm.id)]
    return f


def _ids(farm_payload, report_type) -> set:
    for r in farm_payload["reports"]:
        if r["type"] == report_type:
            return {c["cow_id"] for c in r["cows"]}
    return set()


async def _heat(client, cow, **body):
    return await client.post("/checks/heat", json={
        "cow_id": str(cow.id), "check_date": TODAY.isoformat(),
        "heat_detected": True, "bleeding_event": False, **body,
    })


async def test_a_heat_seen_on_an_open_cow_puts_her_on_the_report_until_she_is_bred(
    db, farm, api, tech,
):
    """Josh: "any time a cow is seen in heat, not only inside the Heat Report
    window". She has no insemination to be checked against -- the heat check
    used to demand one, so this heat was unrecordable."""
    cow = await _add(db, _farm_cow(farm))

    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow)
        assert r.status_code == 201, r.text
        assert r.json()["on_breed_report"] is True
        assert r.json()["insemination_id"] is None

        f = await _worklist(client, farm)
        assert str(cow.id) in _ids(f, "breed-today")
        assert str(cow.id) not in _ids(f, "open-report")

        r = await client.post("/inseminations/", json={
            "cow_id": str(cow.id),
            "date": datetime.combine(TODAY, time(9, 30)).isoformat(),
            "bull_name": "Mogul", "semen_type": "conventional",
        })
        assert r.status_code == 201, r.text

        f = await _worklist(client, farm)
        assert str(cow.id) not in _ids(f, "breed-today")
    assert cow.status == CowStatus.inseminated


async def test_a_yes_on_the_heat_report_sends_her_to_todays_breed_report(db, farm, api, tech):
    """Day 19: the AI she is on has failed. She is open again and is bred
    today -- not parked in a program waiting for a breeding day."""
    cow = await _add(db, _farm_cow(farm, status=CowStatus.inseminated,
                                   last_insemination_date=TODAY - timedelta(days=19)))
    ins = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=cow.last_insemination_date,
                       bull_name="Mogul", attempt_number=1)
    db.add(ins)
    await db.flush()
    cow.last_insemination_id = ins.id
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow, insemination_id=str(ins.id))
        assert r.status_code == 201, r.text
        assert r.json()["on_breed_report"] is True
        f = await _worklist(client, farm)

    assert cow.status == CowStatus.open
    assert cow.current_program is None
    assert str(cow.id) in _ids(f, "breed-today")
    assert str(cow.id) not in _ids(f, "heat")


async def test_a_no_on_the_heat_report_leaves_her_where_she_is(db, farm, api, tech):
    cow = await _add(db, _farm_cow(farm, status=CowStatus.inseminated,
                                   last_insemination_date=TODAY - timedelta(days=20)))
    ins = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=cow.last_insemination_date,
                       bull_name="Mogul", attempt_number=1)
    db.add(ins)
    await db.flush()
    cow.last_insemination_id = ins.id
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow, insemination_id=str(ins.id), heat_detected=False)
        assert r.status_code == 201, r.text
        assert r.json()["on_breed_report"] is False
        f = await _worklist(client, farm)

    assert cow.status == CowStatus.inseminated
    assert str(cow.id) not in _ids(f, "breed-today")


async def test_a_heat_on_a_do_not_breed_cow_is_recorded_but_she_is_not_bred(
    db, farm, api, tech,
):
    cow = await _add(db, _farm_cow(farm, do_not_breed=True))

    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow)
        assert r.status_code == 201, r.text
        body = r.json()
        f = await _worklist(client, farm)

    assert body["on_breed_report"] is False
    assert "Do Not Breed" in body["not_bred_because"]
    assert str(cow.id) not in _ids(f, "breed-today")


async def test_a_heat_nobody_acted_on_does_not_wreck_her_protocol(db, farm, api, tech, make_cow):
    """"Assume nothing happened": a cow mid-protocol who shows heat and isn't
    bred carries on with the protocol she was on. Parking her anywhere --
    open, a program -- would have to be undone by something, and nothing
    would."""
    cow = await make_cow(steps=[(7, 0, "2cc PGF", False, False),
                                (10, 3, "2cc GnRH + Insemination", True, False)],
                         last_calving_date=TODAY - timedelta(days=100))

    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow)
        assert r.status_code == 201, r.text
        f = await _worklist(client, farm)

    assert cow.status == CowStatus.needling
    assert str(cow.id) in _ids(f, "breed-today")
    # Her protocol work is still there for whoever doesn't breed her.
    assert str(cow.id) in _ids(f, "needling")


async def test_only_todays_heats_reach_the_report(db, farm, api, tech):
    """Yesterday's heat, not bred: she is not on today's report, and she is
    back on the Open Cow Report with no mark against her."""
    cow = await _add(db, _farm_cow(farm))
    db.add(HeatCheck(id=uuid.uuid4(), cow_id=cow.id, check_date=TODAY - timedelta(days=1),
                     heat_detected=True, bleeding_event=False))
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        f = await _worklist(client, farm)

    assert str(cow.id) not in _ids(f, "breed-today")
    assert str(cow.id) in _ids(f, "open-report")


async def test_a_farm_with_a_cow_to_breed_stays_on_the_route_on_an_off_day(
    db, farm, api, tech,
):
    farm.visit_weekdays = [(TODAY.weekday() + 1) % 7]
    cow = await _add(db, _farm_cow(farm))

    async with api("technician", user_id=tech.id) as client:
        before = await _worklist(client, farm)
        r = await _heat(client, cow)
        assert r.status_code == 201, r.text
        after = await _worklist(client, farm)

    assert before["schedule"] == "not_due"
    assert after["schedule"] == "visit_today"


async def test_the_farm_is_told_to_breed_her_today(db, farm, api, tech):
    cow = await _add(db, _farm_cow(farm))

    async with api("technician", user_id=tech.id) as client:
        assert (await _heat(client, cow)).status_code == 201

    notes = (await db.execute(
        select(Notification).where(Notification.cow_id == cow.id)
    )).scalars().all()
    assert [n.type for n in notes] == ["breeding_due"]
    assert "Today's Breed Report" in notes[0].message


@pytest.mark.parametrize("status", [CowStatus.pregnant, CowStatus.dry])
async def test_a_pregnant_cow_seen_in_heat_is_bred_like_any_other(
    db, farm, api, tech, status,
):
    """Josh, Oct 2: "Anytime a cow is in heat, no matter conditions, must be
    inseminated" -- pregnant is not one of his four exceptions. A heat means
    the pregnancy failed: she is open, her due and dry dates go, and she is
    on today's report."""
    cow = await _add(db, _farm_cow(farm, status=status,
                                   due_date=TODAY + timedelta(days=100),
                                   dry_date=TODAY + timedelta(days=40)))

    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow)
        assert r.status_code == 201, r.text
        assert r.json()["on_breed_report"] is True
        f = await _worklist(client, farm)

    assert cow.status == CowStatus.open
    assert cow.due_date is None and cow.dry_date is None
    assert str(cow.id) in _ids(f, "breed-today")


async def test_a_listed_cow_cannot_be_inseminated_from_any_form(db, farm, api, tech, make_cow):
    """Not on the breed report, not on the Timed Breeding Report, and the
    insemination itself is refused -- the list means it."""
    cow = await make_cow(steps=[(10, 0, "2cc GnRH + Insemination", True, False)],
                         do_not_inseminate=True)

    async with api("technician", user_id=tech.id) as client:
        f = await _worklist(client, farm)
        r = await client.post("/inseminations/", json={
            "cow_id": str(cow.id),
            "date": datetime.combine(TODAY, time(9, 30)).isoformat(),
            "bull_name": "Mogul", "semen_type": "conventional",
        })

    assert str(cow.id) not in _ids(f, "timed-breeding")
    assert r.status_code == 409
    assert "Do Not Inseminate" in r.json()["detail"]


async def test_a_no_on_a_cow_that_was_never_due_a_check_is_refused(db, farm, api, tech):
    cow = await _add(db, _farm_cow(farm))

    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow, heat_detected=False)

    assert r.status_code == 422


# ── parentage and the two lists ──────────────────────────────────────

async def test_parentage_and_the_breeding_lists_are_saved_on_the_cow(db, farm, api, tech):
    cow = await _add(db, _farm_cow(farm))

    async with api("technician", user_id=tech.id) as client:
        r = await client.patch(f"/cows/{cow.id}", json={
            "sire": "Delta-Lambda", "maternal_sire": "Mogul",
            "do_not_breed": True, "do_not_inseminate": False,
        })
        assert r.status_code == 200, r.text
        got = (await client.get(f"/cows/{cow.id}")).json()

    assert got["sire"] == "Delta-Lambda"
    assert got["maternal_sire"] == "Mogul"
    assert got["do_not_breed"] is True
    assert got["do_not_inseminate"] is False


# ── the lists cover every route to a breeding ────────────────────────

async def test_a_listed_cow_cannot_start_a_protocol(db, farm, api, tech):
    cow = await _add(db, _farm_cow(farm, do_not_breed=True))

    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch",
            "start_date": TODAY.isoformat(),
        })

    assert r.status_code == 409
    assert "Do Not Breed" in r.json()["detail"]
    assert cow.status == CowStatus.open


async def test_a_cow_listed_mid_protocol_gets_no_more_shots_asked_for(
    db, farm, api, tech, make_cow,
):
    """Her protocol is left in place (reversible), but nobody is sent to
    inject a cow whose protocol can only end in an AI she may not have."""
    cow = await make_cow(steps=[(7, 0, "2cc PGF", False, False),
                                (10, 3, "2cc GnRH + Insemination", True, False)],
                         do_not_breed=True)

    async with api("technician", user_id=tech.id) as client:
        f = await _worklist(client, farm)

    assert str(cow.id) not in _ids(f, "needling")
    assert cow.status == CowStatus.needling


async def test_the_breeding_lists_can_be_read_as_lists(db, farm, api, tech):
    dnb = await _add(db, _farm_cow(farm, do_not_breed=True))
    dni = await _add(db, _farm_cow(farm, do_not_inseminate=True))
    await _add(db, _farm_cow(farm))

    async with api("technician", user_id=tech.id) as client:
        f = await _worklist(client, farm)

    assert _ids(f, "do-not-breed") == {str(dnb.id)}
    assert _ids(f, "do-not-inseminate") == {str(dni.id)}
    titles = {r["type"]: r["title"] for r in f["reports"]}
    assert titles["do-not-breed"] == "Do Not Breed List"
    # Reference lists, never counted as the day's work.
    assert all(not r["is_work_report"] for r in f["reports"]
               if r["type"] in ("do-not-breed", "do-not-inseminate"))


async def test_an_open_listed_cow_is_not_sent_for_a_protocol(db, farm):
    from app.services import status_engine

    cow = await _add(db, _farm_cow(farm, status=CowStatus.inseminated, do_not_breed=True))
    await status_engine.on_pregnancy_negative(cow, db)
    await db.flush()

    (note,) = (await db.execute(
        select(Notification).where(Notification.cow_id == cow.id)
    )).scalars().all()
    assert "select a needling protocol" not in note.message
    assert "Do Not Breed" in note.message


# ── the bull list the form now depends on ────────────────────────────

async def test_re_adding_a_retired_bull_brings_it_back(db, farm, api, tech):
    """Retired bulls are hidden from the form, and the bull must be picked
    from the list -- refusing the re-add left the straw unrecordable."""
    from app.models.models import Bull

    old = Bull(id=uuid.uuid4(), farm_id=farm.id, name="Mogul", active=False)
    db.add(old)
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/bulls/farm/{farm.id}", json={"name": "mogul"})
        listed = (await client.get(f"/bulls/farm/{farm.id}")).json()

    assert r.status_code == 201, r.text
    assert r.json()["id"] == str(old.id)
    assert [b["name"] for b in listed] == ["Mogul"]


async def test_a_bull_already_listed_is_not_added_twice_in_another_case(db, farm, api, tech):
    from app.models.models import Bull

    db.add(Bull(id=uuid.uuid4(), farm_id=farm.id, name="Mogul", active=True))
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/bulls/farm/{farm.id}", json={"name": "MOGUL"})

    assert r.status_code == 409


async def test_a_listed_cow_is_not_promised_a_report_she_is_kept_off(db, farm, api, tech):
    cow = await _add(db, _farm_cow(farm, status=CowStatus.pregnant, do_not_breed=True))

    async with api("technician", user_id=tech.id) as client:
        assert (await _heat(client, cow)).status_code == 201

    (note,) = (await db.execute(
        select(Notification).where(Notification.cow_id == cow.id)
    )).scalars().all()
    assert "Do Not Breed" in note.message
    assert "Open Cow Report" not in note.message


# ── no report question has a default, at the API either ──────────────

@pytest.mark.parametrize("path,body", [
    ("/checks/heat", {"heat_detected": True}),                      # blood on tail unanswered
    ("/checks/pregnancy", {"result": "pregnant", "has_cysts": False}),  # infection unanswered
    ("/calving/", {"live_birth": True}),                            # still birth unanswered
])
async def test_an_unanswered_question_is_refused_not_assumed(db, farm, api, tech, path, body):
    """The app will not save an unanswered question; the API used to fill in
    "no" for one that arrived missing, which is the toggle's silent default
    by another route (Josh, Oct 4)."""
    cow = await _add(db, _farm_cow(farm))
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(path, json={
            "cow_id": str(cow.id), "check_date": TODAY.isoformat(),
            "calving_date": TODAY.isoformat(),
            "insemination_id": str(uuid.uuid4()), **body,
        })
    assert r.status_code == 422, r.text
