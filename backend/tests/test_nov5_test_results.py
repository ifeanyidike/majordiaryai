"""Josh's test results, Nov 5 (Test_Results_Changes_Needed.xlsx).

Each section is one thing he asked for, named by his checklist row. The day-283
change (row 48) is in test_sept17_rules.py beside the rule it replaced.
"""

import io
import uuid
from datetime import datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, EnrollmentStatus, HeatCheck, Insemination, NeedlingEnrollment,
    Notification, ProtocolType, UserRole,
)
from app.services import kpis, status_engine
from app.services.protocols import PROTOCOLS

TODAY = local_today()
YESTERDAY = TODAY - timedelta(days=1)
# A protocol can only start on a breeding day, whatever day the suite runs.
START = status_engine.adjust_to_breeding_day(TODAY)
OFF_DAY = next(TODAY + timedelta(days=i) for i in range(7)
               if (TODAY + timedelta(days=i)).weekday() not in status_engine.BREEDING_WEEKDAYS)


@pytest.fixture
async def tech(db, farm, make_user):
    t = await make_user(UserRole.technician)
    farm.assigned_technician_id = t.id
    await db.flush()
    return t


async def _cow(db, farm, **kw) -> Cow:
    kw.setdefault("ear_tag", f"N-{uuid.uuid4().hex[:6]}")
    kw.setdefault("status", CowStatus.open)
    kw.setdefault("lactation_number", 2)
    kw.setdefault("last_calving_date", TODAY - timedelta(days=120))
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, **kw)
    db.add(cow)
    await db.flush()
    return cow


async def _sweep(db, farm, today=TODAY):
    await status_engine.run_lifecycle_transitions(db, farm_ids=[farm.id], today=today)


async def _reports(client, farm) -> dict:
    r = await client.get("/reports/worklist", params={"farm_id": str(farm.id)})
    assert r.status_code == 200, r.text
    (f,) = [f for f in r.json()["farms"] if f["farm_id"] == str(farm.id)]
    return {rep["type"]: rep for rep in f["reports"]}


def _on(reports: dict, kind: str, cow: Cow) -> bool:
    return any(c["cow_id"] == str(cow.id) for c in reports.get(kind, {}).get("cows", []))


def _row(reports: dict, kind: str, cow: Cow) -> dict:
    return next(c for c in reports[kind]["cows"] if c["cow_id"] == str(cow.id))


async def _heat(client, cow, day=TODAY):
    return await client.post("/checks/heat", json={
        "cow_id": str(cow.id), "check_date": day.isoformat(),
        "heat_detected": True, "bleeding_event": False,
    })


async def _breed(client, cow):
    return await client.post("/inseminations/", json={
        "cow_id": str(cow.id), "bull_name": "Mogul", "semen_type": "conventional",
        "date": datetime.combine(TODAY, time(9, 30)).isoformat(),
    })


# ── row 4: a Cull cow keeps her days in milk ─────────────────────────

async def test_a_cull_cow_is_still_in_milk(db, farm, api, tech):
    cow = await _cow(db, farm)
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/cows/{cow.id}/cull", json={"reason": "Low yield"})
        assert r.status_code == 200, r.text
        got = (await client.get(f"/cows/{cow.id}")).json()
    assert got["status"] == "cull"
    assert got["is_milking"] is True


async def test_a_cow_dried_off_before_she_was_culled_is_not(db, farm, api, tech):
    cow = await _cow(db, farm, status=CowStatus.dry, dry_date=TODAY - timedelta(days=20),
                     due_date=TODAY + timedelta(days=40))
    async with api("technician", user_id=tech.id) as client:
        await client.post(f"/cows/{cow.id}/cull", json={"reason": "Injury"})
        got = (await client.get(f"/cows/{cow.id}")).json()
    assert got["is_milking"] is False


async def test_the_dashboards_milking_count_agrees_with_her(db, farm, api, tech):
    await _cow(db, farm, status=CowStatus.cull)
    await _cow(db, farm, status=CowStatus.cull, dry_date=TODAY - timedelta(days=5))
    async with api("admin") as client:
        (row,) = (await client.get("/reports/herd-summary",
                                   params={"farm_id": str(farm.id)})).json()
    assert row["milking"] == 1


# ── rows 5, 6, 64: Do Not Breed is a status; Do Not Inseminate is gone ─

async def test_marking_an_open_cow_makes_her_dnb(db, farm, api, tech):
    cow = await _cow(db, farm)
    async with api("technician", user_id=tech.id) as client:
        r = await client.patch(f"/cows/{cow.id}", json={"do_not_breed": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dnb"


async def test_row_64_a_marked_heifer_leaves_the_insemination_program(db, farm, api, tech):
    heifer = await _cow(db, farm, lactation_number=0, last_calving_date=None,
                        current_program="Insemination",
                        date_of_birth=TODAY - timedelta(days=420))
    async with api("technician", user_id=tech.id) as client:
        assert _on(await _reports(client, farm), "insemination", heifer)
        r = await client.patch(f"/cows/{heifer.id}", json={"do_not_breed": True})
        assert r.status_code == 200, r.text
        reports = await _reports(client, farm)
    assert not _on(reports, "insemination", heifer)
    assert _on(reports, "do-not-breed", heifer)
    # Her page said "Current Program: Insemination" with the list ticked.
    assert r.json()["current_program"] is None


async def test_taking_her_off_the_list_puts_her_back(db, farm, api, tech):
    cow = await _cow(db, farm, status=CowStatus.dnb, do_not_breed=True)
    heifer = await _cow(db, farm, status=CowStatus.dnb, do_not_breed=True,
                        lactation_number=0, last_calving_date=None)
    async with api("technician", user_id=tech.id) as client:
        one = await client.patch(f"/cows/{cow.id}", json={"do_not_breed": False})
        two = await client.patch(f"/cows/{heifer.id}", json={"do_not_breed": False})
    assert (one.json()["status"], one.json()["current_program"]) == ("open", None)
    # A breeding-age heifer goes where the sweep would have put her.
    assert (two.json()["status"], two.json()["current_program"]) == ("open", "Insemination")


async def test_a_cow_on_a_protocol_stops_it(db, api, tech, make_cow):
    cow = await make_cow(steps=[(7, 0, "2cc PGF", False, False)])
    async with api("technician", user_id=tech.id) as client:
        r = await client.patch(f"/cows/{cow.id}", json={"do_not_breed": True})
    assert r.json()["status"] == "dnb"
    assert cow.enrollment.status == EnrollmentStatus.cancelled


@pytest.mark.parametrize("status,fields", [
    (CowStatus.fresh, {"last_calving_date": TODAY - timedelta(days=20)}),
    (CowStatus.inseminated, {"last_insemination_date": TODAY - timedelta(days=10)}),
    (CowStatus.pregnant, {"due_date": TODAY + timedelta(days=200)}),
    (CowStatus.dry, {"due_date": TODAY + timedelta(days=30)}),
    (CowStatus.heifer, {"lactation_number": 0, "last_calving_date": None,
                        "date_of_birth": TODAY - timedelta(days=200)}),
])
async def test_a_cow_with_work_still_coming_keeps_her_status(db, farm, api, tech, status, fields):
    """DNB takes over from Open. A pregnant cow has a calf coming, and marking
    her must not lose her due date; she is DNB when she would go Open."""
    cow = await _cow(db, farm, status=status, **fields)
    async with api("technician", user_id=tech.id) as client:
        r = await client.patch(f"/cows/{cow.id}", json={"do_not_breed": True})
    assert r.json()["status"] == status.value
    assert r.json()["do_not_breed"] is True


async def test_a_marked_cow_goes_to_dnb_at_day_70_not_open(db, farm):
    calved = status_engine.adjust_to_breeding_day(TODAY) - timedelta(days=70)
    cow = await _cow(db, farm, status=CowStatus.fresh, do_not_breed=True, last_calving_date=calved)
    await _sweep(db, farm, today=status_engine.adjust_to_breeding_day(TODAY))
    assert cow.status == CowStatus.dnb


async def test_a_marked_heifer_goes_to_dnb_at_breeding_age(db, farm):
    heifer = await _cow(db, farm, status=CowStatus.heifer, do_not_breed=True, lactation_number=0,
                        last_calving_date=None, date_of_birth=TODAY - timedelta(days=400))
    await _sweep(db, farm)
    assert heifer.status == CowStatus.dnb
    assert heifer.current_program is None
    notes = (await db.execute(
        select(Notification).where(Notification.cow_id == heifer.id)
    )).scalars().all()
    assert notes == [], "told the farm she is ready for the Insemination Program"


async def test_a_marked_cow_goes_to_dnb_when_a_check_finds_her_open(db, farm, api, tech):
    cow = await _cow(db, farm, status=CowStatus.inseminated, do_not_breed=True,
                     last_insemination_date=TODAY - timedelta(days=35))
    ai = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=cow.last_insemination_date,
                      attempt_number=1)
    db.add(ai)
    await db.flush()
    cow.last_insemination_id = ai.id
    await db.flush()
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/checks/pregnancy", json={
            "cow_id": str(cow.id), "insemination_id": str(ai.id),
            "check_date": TODAY.isoformat(), "result": "not_pregnant",
            "has_infection": False, "has_cysts": False,
        })
    assert r.status_code == 201, r.text
    assert cow.status == CowStatus.dnb


async def test_a_heat_on_a_dnb_cow_is_recorded_and_changes_nothing(db, farm, api, tech):
    cow = await _cow(db, farm, status=CowStatus.dnb, do_not_breed=True)
    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow)
        assert r.status_code == 201, r.text
        reports = await _reports(client, farm)
    assert r.json()["on_breed_report"] is False
    assert r.json()["can_overrule"] is False
    assert "Do Not Breed" in r.json()["not_bred_because"]
    assert not _on(reports, "breed-today", cow)
    assert cow.status == CowStatus.dnb


async def test_cows_marked_before_dnb_existed_are_moved_by_the_sweep(db, farm, make_cow):
    """Migration 0023 leaves them: the build it replaces cannot read the value."""
    open_cow = await _cow(db, farm, do_not_breed=True)
    on_protocol = await make_cow(steps=[(7, 0, "2cc PGF", False, False)], do_not_breed=True)
    culled = await _cow(db, farm, do_not_breed=True, status=CowStatus.cull)

    await _sweep(db, farm)

    assert open_cow.status == CowStatus.dnb
    assert on_protocol.status == CowStatus.dnb
    assert on_protocol.enrollment.status == EnrollmentStatus.cancelled
    assert culled.status == CowStatus.cull


async def test_dnb_is_not_a_dead_end(db, farm, api, tech):
    culled = await _cow(db, farm, status=CowStatus.dnb, do_not_breed=True)
    calved = await _cow(db, farm, status=CowStatus.dnb, do_not_breed=True)
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/cows/{culled.id}/cull", json={"reason": "Age"})
        assert r.status_code == 200, r.text
        r = await client.post("/calving/", json={
            "cow_id": str(calved.id), "calving_date": TODAY.isoformat(),
            "live_birth": True, "still_birth": False, "calf_sex": "male",
        })
        assert r.status_code == 201, r.text
    assert culled.status == CowStatus.cull
    assert calved.status == CowStatus.fresh


async def test_a_dnb_cow_still_owes_her_vaccine(db, farm, api, tech):
    cow = await _cow(db, farm, status=CowStatus.dnb, do_not_breed=True,
                     last_calving_date=TODAY - timedelta(days=45),
                     created_at=datetime.now(timezone.utc) - timedelta(days=90))
    async with api("technician", user_id=tech.id) as client:
        assert _on(await _reports(client, farm), "post-calving", cow)


async def test_dnb_has_its_own_count_and_is_not_in_the_breeding_pool(db, farm, api, tech):
    await _cow(db, farm, status=CowStatus.dnb, do_not_breed=True)
    async with api("admin") as client:
        (row,) = (await client.get("/reports/herd-summary",
                                   params={"farm_id": str(farm.id)})).json()
    assert row["dnb"] == 1 and row["open"] == 0

    start = TODAY - timedelta(days=10)
    cow = kpis.CowRec(id=uuid.uuid4(), status="dnb", last_calving_date=TODAY - timedelta(days=200))
    herd = kpis._Herd(kpis.HerdRecords(cows=[cow]), TODAY)
    assert herd.eligible_at(cow, start) is False


async def test_a_dnb_cow_still_counts_in_the_farms_herd(db, farm, api):
    await _cow(db, farm, status=CowStatus.dnb, do_not_breed=True)
    async with api("admin") as client:
        got = (await client.get(f"/farms/{farm.id}")).json()
    assert got["cow_count"] == 1


async def test_a_csv_row_with_status_dnb_is_marked(db, api, farm):
    csv = f"ear_tag,status\nCSV-1,DNB\nCSV-2,do not breed\n".encode()
    async with api("admin") as client:
        r = await client.post(f"/imports/cows?farm_id={farm.id}",
                              files={"file": ("herd.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 200, r.text
    cows = (await db.execute(select(Cow).where(Cow.farm_id == farm.id))).scalars().all()
    assert {(c.status, c.do_not_breed) for c in cows} == {(CowStatus.dnb, True)}


async def test_do_not_inseminate_is_gone(db, farm, api, tech):
    cow = await _cow(db, farm)
    async with api("technician", user_id=tech.id) as client:
        got = (await client.get(f"/cows/{cow.id}")).json()
        # An old build still sends it; it is ignored, not an error.
        r = await client.patch(f"/cows/{cow.id}", json={"do_not_inseminate": True})
        reports = await _reports(client, farm)
    assert "do_not_inseminate" not in got
    assert r.status_code == 200
    assert "do-not-inseminate" not in reports
    assert cow.status == CowStatus.open


# ── row 7: the farmer may overrule the 60-day rule ───────────────────

def _under_60(**kw) -> dict:
    return {"status": CowStatus.fresh, "last_calving_date": TODAY - timedelta(days=55), **kw}


async def test_a_refused_heat_offers_the_overrule(db, farm, api, tech):
    cow = await _cow(db, farm, **_under_60())
    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow)
        reports = await _reports(client, farm)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["on_breed_report"] is False
    assert body["can_overrule"] is True
    assert "60 days" in body["not_bred_because"]
    # Saying no, or nothing, leaves her off.
    assert not _on(reports, "breed-today", cow)


async def test_overruled_she_is_on_the_report_and_can_be_bred(db, farm, api, tech):
    cow = await _cow(db, farm, **_under_60())
    async with api("technician", user_id=tech.id) as client:
        heat = (await _heat(client, cow)).json()
        r = await client.post(f"/checks/heat/{heat['id']}/overrule")
        assert r.status_code == 200, r.text
        assert r.json()["on_breed_report"] is True
        reports = await _reports(client, farm)
        assert _on(reports, "breed-today", cow)
        assert "farmer" in _row(reports, "breed-today", cow)["detail"]

        r = await _breed(client, cow)
        assert r.status_code == 201, r.text
    assert cow.status == CowStatus.inseminated


async def test_overruled_and_not_bred_she_is_open_the_next_day(db, farm):
    """His rule stands: in heat and not bred that day is Open the next."""
    cow = await _cow(db, farm, **_under_60())
    db.add(HeatCheck(id=uuid.uuid4(), cow_id=cow.id, check_date=YESTERDAY, heat_detected=True,
                     bleeding_event=False, breed_anyway=True,
                     created_at=datetime.combine(YESTERDAY, time(8), tzinfo=timezone.utc)))
    await db.flush()
    await _sweep(db, farm)
    assert cow.status == CowStatus.open


@pytest.mark.parametrize("fields", [
    {"status": CowStatus.fresh, "last_calving_date": TODAY - timedelta(days=55),
     "do_not_breed": True},
    {"status": CowStatus.heifer, "lactation_number": 0, "last_calving_date": None,
     "date_of_birth": TODAY - timedelta(days=300)},
    {"status": CowStatus.open, "last_calving_date": TODAY - timedelta(days=120)},
])
async def test_only_the_60_day_rule_can_be_overruled(db, farm, api, tech, fields):
    cow = await _cow(db, farm, **fields)
    async with api("technician", user_id=tech.id) as client:
        heat = (await _heat(client, cow)).json()
        assert heat["can_overrule"] is False
        r = await client.post(f"/checks/heat/{heat['id']}/overrule")
    assert r.status_code == 409


async def test_a_heat_from_yesterday_cannot_be_overruled(db, farm, api, tech):
    cow = await _cow(db, farm, **_under_60())
    async with api("technician", user_id=tech.id) as client:
        heat = (await _heat(client, cow, day=YESTERDAY)).json()
        assert heat["can_overrule"] is False
        r = await client.post(f"/checks/heat/{heat['id']}/overrule")
    assert r.status_code == 409


async def test_a_check_that_found_no_heat_cannot_be_overruled(db, farm, api, tech):
    cow = await _cow(db, farm, status=CowStatus.inseminated, last_insemination_date=TODAY - timedelta(days=20),
                     last_calving_date=TODAY - timedelta(days=55))
    ai = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=cow.last_insemination_date, attempt_number=1)
    db.add(ai)
    await db.flush()
    cow.last_insemination_id = ai.id
    await db.flush()
    async with api("technician", user_id=tech.id) as client:
        heat = await client.post("/checks/heat", json={
            "cow_id": str(cow.id), "insemination_id": str(ai.id), "check_date": TODAY.isoformat(),
            "heat_detected": False, "bleeding_event": False,
        })
        assert heat.status_code == 201, heat.text
        r = await client.post(f"/checks/heat/{heat.json()['id']}/overrule")
    assert r.status_code == 409


async def test_overruling_twice_tells_the_farm_once(db, farm, api, tech):
    cow = await _cow(db, farm, **_under_60())
    async with api("technician", user_id=tech.id) as client:
        heat = (await _heat(client, cow)).json()
        for _ in range(2):
            r = await client.post(f"/checks/heat/{heat['id']}/overrule")
            assert r.status_code == 200, r.text
    notes = (await db.execute(select(Notification).where(
        Notification.cow_id == cow.id, Notification.type == "breeding_due"))).scalars().all()
    assert len(notes) == 1


async def test_a_vet_cannot_overrule(db, farm, api, tech):
    cow = await _cow(db, farm, **_under_60())
    async with api("technician", user_id=tech.id) as client:
        heat = (await _heat(client, cow)).json()
    async with api("vet") as client:
        r = await client.post(f"/checks/heat/{heat['id']}/overrule")
    assert r.status_code == 403


# ── row 11: her schedule ─────────────────────────────────────────────

async def test_her_history_carries_the_protocol_she_is_on(db, api, tech, make_cow):
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=[
        (1, -1, "2cc PGF", False, True),
        (2, 0, "Heat Observation", False, False),
        (3, 1, "Heat Examination", False, False),
    ])
    async with api("technician", user_id=tech.id) as client:
        got = (await client.get(f"/cows/{cow.id}/history")).json()
    protocol = got["active_protocol"]
    assert protocol["protocol"] == "prostaglandin_heat"
    steps = sorted(protocol["records"], key=lambda r: r["protocol_day"])
    assert [(s["protocol_day"], s["completed"]) for s in steps] == \
        [(1, True), (2, False), (3, False)]


async def test_a_cow_on_no_protocol_has_none(db, farm, api, tech, make_cow):
    finished = await make_cow(cow_status=CowStatus.open,
                              enrollment_status=EnrollmentStatus.cancelled,
                              steps=[(7, 0, "2cc PGF", False, False)])
    async with api("technician", user_id=tech.id) as client:
        got = (await client.get(f"/cows/{finished.id}/history")).json()
    assert got["active_protocol"] is None


# ── row 12: the Prostaglandin Report ─────────────────────────────────

def _pgf(day_today: int, done=()):
    """Prostaglandin Heat's steps, as of her being on `day_today`."""
    return [(s["day"], s["day"] - day_today, s["treatment"], bool(s.get("is_final")),
             s["day"] in done)
            for s in PROTOCOLS["prostaglandin_heat"]]


def test_days_2_to_5_are_heat_checks():
    assert [s["day"] for s in PROTOCOLS["prostaglandin_heat"]] == [1, 2, 3, 4, 5]


async def test_the_shot_is_needling_and_the_checks_are_prostaglandin(db, farm, api, tech, make_cow):
    shot = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=_pgf(1))
    check = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=_pgf(3, done={1, 2}))
    async with api("technician", user_id=tech.id) as client:
        reports = await _reports(client, farm)

    assert _on(reports, "needling", shot) and not _on(reports, "prostaglandin", shot)
    assert _on(reports, "prostaglandin", check) and not _on(reports, "needling", check)
    row = _row(reports, "prostaglandin", check)
    assert row["record_kind"] == "prostaglandin"
    assert row["protocol_day"] == 3
    assert row["needling_record_id"]
    assert reports["prostaglandin"]["title"] == "Prostaglandin Report"
    assert reports["prostaglandin"]["is_work_report"] is True


async def test_no_heat_to_look_for_until_the_shot_is_given(db, farm, api, tech, make_cow):
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=_pgf(2))
    async with api("technician", user_id=tech.id) as client:
        reports = await _reports(client, farm)
    assert _on(reports, "needling", cow)
    assert not _on(reports, "prostaglandin", cow)


async def test_a_no_clears_today_and_she_is_back_tomorrow(db, farm, api, tech, make_cow, records_of):
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=_pgf(3, done={1, 2}))
    async with api("technician", user_id=tech.id) as client:
        before = await _reports(client, farm)
        record_id = _row(before, "prostaglandin", cow)["needling_record_id"]
        r = await client.patch(f"/needling/records/{record_id}/complete",
                               json={"bleeding_event": False})
        assert r.status_code == 200, r.text
        after = await _reports(client, farm)
    assert not _on(after, "prostaglandin", cow)
    assert cow.status == CowStatus.needling

    # Tomorrow comes.
    for record in await records_of(cow):
        record.scheduled_date -= timedelta(days=1)
    await db.flush()
    async with api("technician", user_id=tech.id) as client:
        assert _row(await _reports(client, farm), "prostaglandin", cow)["protocol_day"] == 4


async def test_a_check_nobody_answered_is_not_asked_again(db, farm, api, tech, make_cow):
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=_pgf(4, done={1, 2}))
    async with api("technician", user_id=tech.id) as client:
        reports = await _reports(client, farm)
        (row,) = [c for c in reports["prostaglandin"]["cows"] if c["cow_id"] == str(cow.id)]
        assert row["protocol_day"] == 4
        r = await client.patch(f"/needling/records/{row['needling_record_id']}/complete",
                               json={"bleeding_event": False})
        assert r.status_code == 200, r.text
        # Day 3 was never answered, and must not take Day 4's place.
        assert not _on(await _reports(client, farm), "prostaglandin", cow)


async def test_no_heat_by_day_5_she_is_open(db, farm, api, tech, make_cow):
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=_pgf(5, done={1, 2, 3, 4}),
                         last_calving_date=TODAY - timedelta(days=100))
    async with api("technician", user_id=tech.id) as client:
        reports = await _reports(client, farm)
        row = _row(reports, "prostaglandin", cow)
        assert "last check" in row["detail"]
        r = await client.patch(f"/needling/records/{row['needling_record_id']}/complete",
                               json={"bleeding_event": False})
        assert r.status_code == 200, r.text
        after = await _reports(client, farm)
    assert cow.status == CowStatus.open
    assert cow.enrollment.status == EnrollmentStatus.completed
    assert _on(after, "open-report", cow)
    (note,) = (await db.execute(
        select(Notification).where(Notification.cow_id == cow.id)
    )).scalars().all()
    assert "prostaglandin_heat" not in note.message, "the raw enum reached the farm"


@pytest.mark.parametrize("day", [2, 3, 5])
async def test_in_heat_she_is_bred_from_the_report(db, farm, api, tech, make_cow, records_of, day):
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat,
                         steps=_pgf(day, done=set(range(1, day))),
                         last_calving_date=TODAY - timedelta(days=100))
    async with api("technician", user_id=tech.id) as client:
        r = await _heat(client, cow)
        assert r.status_code == 201, r.text
        assert r.json()["on_breed_report"] is True
        reports = await _reports(client, farm)
        # One job, not two: nobody is asked to check a cow already in heat.
        assert not _on(reports, "prostaglandin", cow)
        assert _on(reports, "breed-today", cow)
        # Day 5 is not the end of her while she is waiting to be bred.
        assert cow.status == CowStatus.needling

        r = await _breed(client, cow)
        assert r.status_code == 201, r.text

    assert cow.status == CowStatus.inseminated
    assert cow.enrollment.status == EnrollmentStatus.completed
    answered = next(r for r in await records_of(cow) if r.protocol_day == day)
    assert answered.completed is True and "In heat" in answered.notes


async def test_in_heat_and_not_bred_she_is_open_the_next_day(db, farm, make_cow):
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=_pgf(3, done={1, 2}))
    # Started before the heat: a protocol chosen after it is left alone.
    cow.enrollment.created_at = datetime.now(timezone.utc) - timedelta(days=5)
    db.add(HeatCheck(id=uuid.uuid4(), cow_id=cow.id, check_date=YESTERDAY, heat_detected=True,
                     bleeding_event=False,
                     created_at=datetime.combine(YESTERDAY, time(8), tzinfo=timezone.utc)))
    await db.flush()
    await _sweep(db, farm)
    assert cow.status == CowStatus.open
    assert cow.enrollment.status == EnrollmentStatus.cancelled


async def test_a_protocol_started_before_day_2_existed_still_works(db, farm, api, tech, make_cow):
    """Its records were written when the table had no Day 2."""
    steps = [s for s in _pgf(3, done={1}) if s[0] != 2]
    cow = await make_cow(protocol=ProtocolType.prostaglandin_heat, steps=steps)
    async with api("technician", user_id=tech.id) as client:
        assert _row(await _reports(client, farm), "prostaglandin", cow)["protocol_day"] == 3


async def test_enrolling_lays_out_day_2(db, farm, api, tech, records_of):
    cow = await _cow(db, farm)
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "prostaglandin_heat",
            "start_date": START.isoformat(),
        })
    assert r.status_code == 201, r.text
    assert [rec.protocol_day for rec in await records_of(cow)] == [1, 2, 3, 4, 5]


# ── row 31: Infections ───────────────────────────────────────────────

async def _bred_cow(db, farm) -> Cow:
    cow = await _cow(db, farm, status=CowStatus.inseminated,
                     last_insemination_date=TODAY - timedelta(days=40))
    ai = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=cow.last_insemination_date,
                      attempt_number=1)
    db.add(ai)
    await db.flush()
    cow.last_insemination_id = ai.id
    await db.flush()
    return cow


async def _preg_check(client, cow, **body):
    return await client.post("/checks/pregnancy", json={
        "cow_id": str(cow.id), "insemination_id": str(cow.last_insemination_id),
        "check_date": TODAY.isoformat(), "result": "pregnant",
        "has_infection": True, "has_cysts": False, **body,
    })


async def test_the_infection_is_in_her_history_with_its_name_and_date(db, farm, api, tech):
    cow = await _bred_cow(db, farm)
    async with api("technician", user_id=tech.id) as client:
        r = await _preg_check(client, cow, infection_detail="  Metritis ")
        assert r.status_code == 201, r.text
        (check,) = (await client.get(f"/cows/{cow.id}/history")).json()["pregnancy_checks"]
    assert check["has_infection"] is True
    assert check["infection_detail"] == "Metritis"
    assert check["check_date"] == TODAY.isoformat()


async def test_a_name_with_no_infection_is_not_kept(db, farm, api, tech):
    cow = await _bred_cow(db, farm)
    async with api("technician", user_id=tech.id) as client:
        r = await _preg_check(client, cow, has_infection=False, infection_detail="Metritis")
    assert r.json()["infection_detail"] is None


# ── row 50: enrolled by hand ─────────────────────────────────────────

async def test_a_fresh_cow_can_start_a_protocol_before_day_70(db, farm, api, tech):
    cow = await _cow(db, farm, status=CowStatus.fresh, last_calving_date=TODAY - timedelta(days=30))
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch", "start_date": START.isoformat(),
        })
    assert r.status_code == 201, r.text
    assert cow.status == CowStatus.needling


async def test_the_start_day_rule_still_stands(db, farm, api, tech):
    cow = await _cow(db, farm, status=CowStatus.fresh, last_calving_date=TODAY - timedelta(days=30))
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch", "start_date": OFF_DAY.isoformat(),
        })
    assert r.status_code == 422
    assert cow.status == CowStatus.fresh


async def test_a_cow_with_her_calving_still_to_record_cannot_be_moved_on(db, farm, api, tech):
    """Off Fresh, nothing offers Record Calving: it would be lost for good."""
    cow = await _cow(db, farm, status=CowStatus.fresh, calving_assumed=True)
    async with api("technician", user_id=tech.id) as client:
        one = await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch", "start_date": START.isoformat(),
        })
        two = await client.post(f"/cows/{cow.id}/insemination-program")
    assert (one.status_code, two.status_code) == (409, 409)
    assert "calving" in one.json()["detail"]


@pytest.mark.parametrize("fields", [
    {"status": CowStatus.fresh, "last_calving_date": TODAY - timedelta(days=30)},
    {"status": CowStatus.open},
    {"status": CowStatus.heifer, "lactation_number": 0, "last_calving_date": None,
     "date_of_birth": TODAY - timedelta(days=300)},
])
async def test_a_cow_can_be_put_on_the_insemination_program(db, farm, api, tech, fields):
    cow = await _cow(db, farm, **fields)
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/cows/{cow.id}/insemination-program")
        assert r.status_code == 200, r.text
        reports = await _reports(client, farm)
    assert _on(reports, "insemination", cow)
    assert not _on(reports, "open-report", cow)
    assert (cow.status, cow.current_program) == (CowStatus.open, "Insemination")


@pytest.mark.parametrize("fields,word", [
    ({"status": CowStatus.dnb, "do_not_breed": True}, "Do Not Breed"),
    ({"status": CowStatus.pregnant}, "pregnant"),
    ({"status": CowStatus.needling}, "needling"),
    ({"status": CowStatus.cull}, "cull"),
])
async def test_who_cannot_go_on_it(db, farm, api, tech, fields, word):
    cow = await _cow(db, farm, **fields)
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/cows/{cow.id}/insemination-program")
    assert r.status_code == 409
    assert word in r.json()["detail"]


async def test_a_vet_cannot_put_a_cow_on_it(db, farm, api):
    cow = await _cow(db, farm)
    async with api("vet") as client:
        r = await client.post(f"/cows/{cow.id}/insemination-program")
    assert r.status_code == 403


# ── row 67: the ID tells animals on one tag apart ────────────────────

def _new(farm, **kw) -> dict:
    return {"farm_id": str(farm.id), "ear_tag": "9066", **kw}


async def test_a_repeat_tag_takes_an_are_you_sure_and_an_id(db, farm, api, tech):
    await _cow(db, farm, ear_tag="9066", herd_id="90066")
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/cows/", json=_new(farm))
        assert r.status_code == 409
        # The app reads this as "ask if they are sure" by these words.
        assert r.json()["detail"].startswith("Ear tag")

        r = await client.post("/cows/", json=_new(farm, allow_shared_tag=True))
        assert r.status_code == 422
        assert "ID" in r.json()["detail"]

        r = await client.post("/cows/", json=_new(farm, allow_shared_tag=True, herd_id=" 90067 "))
        assert r.status_code == 201, r.text
    assert r.json()["herd_id"] == "90067"


async def test_an_id_already_on_the_farm_is_refused(db, farm, api, tech):
    await _cow(db, farm, ear_tag="A", herd_id="500")
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/cows/", json=_new(farm, ear_tag="B", herd_id="500"))
    assert r.status_code == 409
    assert r.json()["detail"].startswith("ID")


async def test_an_animal_with_no_id_can_be_given_one(db, farm, api, tech):
    cow = await _cow(db, farm)
    await _cow(db, farm, herd_id="501")
    async with api("technician", user_id=tech.id) as client:
        taken = await client.patch(f"/cows/{cow.id}", json={"herd_id": "501"})
        r = await client.patch(f"/cows/{cow.id}", json={"herd_id": "502"})
    assert taken.status_code == 409
    assert r.json()["herd_id"] == "502"


async def test_an_id_she_has_stays(db, farm, api, tech):
    cow = await _cow(db, farm, herd_id="503")
    async with api("technician", user_id=tech.id) as client:
        same = await client.patch(f"/cows/{cow.id}", json={"herd_id": "503", "breed": "Jersey"})
        blank = await client.patch(f"/cows/{cow.id}", json={"herd_id": None})
        changed = await client.patch(f"/cows/{cow.id}", json={"herd_id": "504"})
    assert same.status_code == 200 and same.json()["breed"] == "Jersey"
    assert blank.json()["herd_id"] == "503"
    assert changed.status_code == 409


async def test_a_report_says_which_of_two_animals_on_a_tag_it_means(db, farm, api, tech):
    one = await _cow(db, farm, ear_tag="9066", herd_id="90066", status=CowStatus.pregnant,
                     due_date=TODAY + timedelta(days=100))
    two = await _cow(db, farm, ear_tag="9066", herd_id="90067", status=CowStatus.pregnant,
                     due_date=TODAY + timedelta(days=100))
    async with api("technician", user_id=tech.id) as client:
        reports = await _reports(client, farm)
    assert _row(reports, "pregnant", one)["herd_id"] == "90066"
    assert _row(reports, "pregnant", two)["herd_id"] == "90067"
