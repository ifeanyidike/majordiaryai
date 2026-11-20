"""Josh's change requests (Nov 20), changes 1 to 6, and the farm KPI page.

1. Technicians get no farm notices (route changes stay, as Office Alerts).
2. Day 223 asks the farm "Moved to dry pen? Yes / No".
3. Day 293 with no calving asks the technician "Has she given birth?", once.
4. An alarm is acknowledged, and then leaves the technician's list.
5. A farm can send its technician a note, as well as an alarm.
6. A heat seen on an Inseminated cow counts on any day.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, Insemination, Message, Notification, PregnancyCheck, PregnancyResult,
    SemenType, User, UserRole,
)
from app.services import farm_kpis, notifications
from app.services.status_engine import run_lifecycle_transitions

TODAY = local_today()


@pytest.fixture
async def tech(db, farm, make_user):
    t = await make_user(UserRole.technician, "Route Tech")
    t.email = f"route-{uuid.uuid4().hex[:6]}@example.com"
    t.phone = "555-0101"
    farm.assigned_technician_id = t.id
    await db.flush()
    return t


@pytest.fixture
def emailed(monkeypatch):
    sent = []
    monkeypatch.setattr(notifications, "_schedule_email", lambda *a, **k: sent.append(a))
    return sent


async def _cow(db, farm, **kw) -> Cow:
    kw.setdefault("lactation_number", 2)
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag=f"Q-{uuid.uuid4().hex[:6]}", **kw)
    db.add(cow)
    await db.flush()
    return cow


async def _notices(db, cow, type_=None):
    stmt = select(Notification).where(Notification.cow_id == cow.id)
    if type_:
        stmt = stmt.where(Notification.type == type_)
    return (await db.execute(stmt.order_by(Notification.created_at))).scalars().all()


async def _sweep(db, today=TODAY):
    return await run_lifecycle_transitions(db, farm_ids=None, today=today)


def _yesterday_answer(notice, answer):
    notice.answer = answer
    notice.answered_at = datetime.now(timezone.utc) - timedelta(days=1)


# ── 1. who sees which notice ─────────────────────────────────────────

async def test_a_technician_sees_only_the_birth_check(db, api, farm, tech):
    cow = await _cow(db, farm, status=CowStatus.pregnant)
    for type_ in ("dry_pen", "calving", "preg_check", "open", "breeding_due", "birth_check"):
        db.add(Notification(farm_id=farm.id, cow_id=cow.id, type=type_, message=type_))
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        as_tech = {n["type"] for n in (await client.get("/notifications/")).json()}
    async with api("farm", farm_id=farm.id) as client:
        as_farm = {n["type"] for n in (await client.get("/notifications/")).json()}
    async with api("admin") as client:
        as_admin = {n["type"] for n in (await client.get(
            "/notifications/", params={"farm_id": str(farm.id)})).json()}

    assert as_tech == {"birth_check"}
    assert as_farm == {"dry_pen", "calving", "preg_check", "open", "breeding_due"}
    assert as_admin == as_farm | {"birth_check"}


# ── 2. Day 223: the dry pen question ─────────────────────────────────

async def test_day_223_asks_the_farm_and_yes_means_she_is_in_the_dry_pen(db, api, farm, tech):
    cow = await _cow(db, farm, status=CowStatus.pregnant, dry_date=TODAY)
    await _sweep(db)
    (notice,) = await _notices(db, cow, "dry_pen")
    assert notice.message == f"Cow {cow.label}: Day 223. Moved to dry pen?"

    async with api("farm", farm_id=farm.id) as client:
        (listed,) = [n for n in (await client.get("/notifications/")).json() if n["id"] == str(notice.id)]
        assert listed["asks"] is True
        r = await client.post(f"/notifications/{notice.id}/answer", json={"answer": "yes"})
        assert r.status_code == 200, r.text
        assert r.json()["answer"] == "yes" and r.json()["asks"] is False
        again = await client.post(f"/notifications/{notice.id}/answer", json={"answer": "no"})
    assert again.status_code == 409
    await db.refresh(cow)
    assert cow.dry_off_confirmed_date == TODAY


async def test_only_the_farm_or_admin_answers_the_dry_pen_question(db, api, farm, tech):
    cow = await _cow(db, farm, status=CowStatus.pregnant, dry_date=TODAY)
    await _sweep(db)
    (notice,) = await _notices(db, cow, "dry_pen")
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/notifications/{notice.id}/answer", json={"answer": "yes"})
    assert r.status_code == 403


async def test_a_no_is_recorded_and_not_asked_again(db, api, farm, tech):
    """Josh gives Yes / No and nothing more, so a No is only recorded."""
    cow = await _cow(db, farm, status=CowStatus.pregnant, dry_date=TODAY)
    await _sweep(db)
    (notice,) = await _notices(db, cow, "dry_pen")
    async with api("farm", farm_id=farm.id) as client:
        r = await client.post(f"/notifications/{notice.id}/answer", json={"answer": "no"})
    assert r.status_code == 200 and r.json()["answer"] == "no"
    await _sweep(db, TODAY + timedelta(days=1))
    assert len(await _notices(db, cow, "dry_pen")) == 1
    await db.refresh(cow)
    assert cow.dry_off_confirmed_date is None


async def test_the_technicians_dry_report_confirm_closes_the_farms_question(db, api, farm, tech):
    cow = await _cow(db, farm, status=CowStatus.pregnant, dry_date=TODAY)
    await _sweep(db)
    async with api("technician", user_id=tech.id) as client:
        assert (await client.post(f"/cows/{cow.id}/dry-off-confirm")).status_code == 200
    async with api("farm", farm_id=farm.id) as client:
        listed = (await client.get("/notifications/")).json()
    assert [n["asks"] for n in listed if n["cow_id"] == str(cow.id)] == [False]


# ── 3. Day 293: the birth check ──────────────────────────────────────

@pytest.mark.parametrize("days,asked", [(292, False), (293, True)])
async def test_day_293_with_no_calving_asks_the_technician(db, farm, emailed, days, asked):
    cow = await _cow(db, farm, status=CowStatus.dry,
                     last_insemination_date=TODAY - timedelta(days=days))
    await _sweep(db)
    found = await _notices(db, cow, "birth_check")
    assert len(found) == (1 if asked else 0)
    if asked:
        assert found[0].message == f"Has cow {cow.label} given birth?"
        assert emailed == []   # the farm is not asked, so not emailed


async def test_the_birth_check_is_asked_once_for_a_breeding(db, farm):
    cow = await _cow(db, farm, status=CowStatus.dry,
                     last_insemination_date=TODAY - timedelta(days=300))
    await _sweep(db)
    (first,) = await _notices(db, cow, "birth_check")
    _yesterday_answer(first, "no")
    await db.flush()
    await _sweep(db, TODAY + timedelta(days=1))
    assert len(await _notices(db, cow, "birth_check")) == 1


async def test_a_cow_that_has_calved_is_not_asked(db, farm):
    cow = await _cow(db, farm, status=CowStatus.fresh,
                     last_insemination_date=TODAY - timedelta(days=300),
                     last_calving_date=TODAY - timedelta(days=5))
    await _sweep(db)
    assert await _notices(db, cow, "birth_check") == []


async def test_the_technician_answers_the_birth_check(db, api, farm, tech):
    cow = await _cow(db, farm, status=CowStatus.dry,
                     last_insemination_date=TODAY - timedelta(days=295))
    await _sweep(db)
    (notice,) = await _notices(db, cow, "birth_check")
    async with api("farm", farm_id=farm.id) as client:
        farm_try = await client.post(f"/notifications/{notice.id}/answer", json={"answer": "yes"})
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/notifications/{notice.id}/answer", json={"answer": "yes"})
    assert farm_try.status_code == 403   # not the farm's to answer
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "yes"


# ── 4 and 5. alarms are acknowledged; notes ──────────────────────────

async def _alarm(client, **body):
    return await client.post("/messages/", json={"channel": "alarm", **body})


async def test_an_acknowledged_alarm_leaves_the_technicians_list(db, api, farm, tech, make_user):
    owner = await make_user(UserRole.farm, "Owner")
    async with api("farm", user_id=owner.id, farm_id=farm.id) as client:
        sent = (await _alarm(client, body="Cow down in pen 4.")).json()
    async with api("technician", user_id=tech.id) as client:
        assert (await client.get("/messages/unread-counts")).json()["alarm"] == 1
        # Opening it is not acknowledging it ("Not yet" keeps it).
        await client.patch(f"/messages/{sent['id']}/read")
        assert (await client.get("/messages/unread-counts")).json()["alarm"] == 1
        assert len((await client.get("/messages/", params={"channel": "alarm"})).json()) == 1

        r = await client.post(f"/messages/{sent['id']}/acknowledge")
        assert r.status_code == 200, r.text
        assert (await client.get("/messages/", params={"channel": "alarm"})).json() == []
        assert (await client.get("/messages/unread-counts")).json()["alarm"] == 0
    async with api("farm", user_id=owner.id, farm_id=farm.id) as client:
        (mine,) = (await client.get("/messages/", params={"channel": "alarm"})).json()
    assert mine["acknowledged_at"] is not None   # the farm sees it was acknowledged


async def test_only_the_recipient_acknowledges(db, api, farm, tech, make_user):
    other = await make_user(UserRole.technician)
    async with api("farm", farm_id=farm.id) as client:
        sent = (await _alarm(client, body="Gate open.")).json()
        by_sender = await client.post(f"/messages/{sent['id']}/acknowledge")
    async with api("technician", user_id=other.id) as client:
        by_other = await client.post(f"/messages/{sent['id']}/acknowledge")
    assert by_sender.status_code == by_other.status_code == 404


async def test_a_farm_sends_a_note_that_does_not_ring_like_an_alarm(db, api, farm, tech, sent_pushes):
    async with api("farm", farm_id=farm.id) as client:
        r = await _alarm(client, body="Feed truck comes Friday.", kind="note")
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "note" and r.json()["recipient_id"] == str(tech.id)
    ((_user, title, _body, _data, channel),) = sent_pushes
    assert title == f"Note · {farm.name}"
    assert channel == "office_alert"


async def test_the_farm_sees_its_technicians_contact_details(db, api, farm, tech):
    async with api("farm", farm_id=farm.id) as client:
        (mine,) = (await client.get("/farms/")).json()
    assert (mine["assigned_technician_name"], mine["assigned_technician_phone"],
            mine["assigned_technician_email"]) == (tech.name, tech.phone, tech.email)


# ── 6. seen in heat, any day after breeding ──────────────────────────

async def test_a_heat_seen_two_days_after_breeding_puts_her_on_todays_report(db, api, farm, tech):
    cow = await _cow(db, farm, status=CowStatus.inseminated,
                     last_insemination_date=TODAY - timedelta(days=2))
    ai = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=cow.last_insemination_date,
                      attempt_number=1)
    db.add(ai)
    await db.flush()
    cow.last_insemination_id = ai.id
    await db.flush()
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/checks/heat", json={
            "cow_id": str(cow.id), "insemination_id": str(ai.id), "check_date": TODAY.isoformat(),
            "heat_detected": True, "bleeding_event": False,
        })
    assert r.status_code == 201, r.text
    assert r.json()["on_breed_report"] is True


async def test_blood_alone_right_after_breeding_is_still_not_a_heat(db, api, farm, tech):
    cow = await _cow(db, farm, status=CowStatus.inseminated,
                     last_insemination_date=TODAY - timedelta(days=2))
    ai = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=cow.last_insemination_date,
                      attempt_number=1)
    db.add(ai)
    await db.flush()
    cow.last_insemination_id = ai.id
    await db.flush()
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/checks/heat", json={
            "cow_id": str(cow.id), "insemination_id": str(ai.id), "check_date": TODAY.isoformat(),
            "heat_detected": False, "bleeding_event": True,
        })
    assert r.status_code == 201, r.text
    await db.refresh(cow)
    assert cow.status == CowStatus.inseminated


# ── the farm KPI page ────────────────────────────────────────────────

def test_the_kpi_page_numbers_follow_joshs_formulas():
    """Conception Rate = Confirmed Pregnancies / Total Inseminations; a
    confirmed pregnancy is an insemination with a positive pregnancy check."""
    today = date(2026, 11, 20)
    ids = [uuid.uuid4() for _ in range(6)]
    breedings = [
        farm_kpis.Breeding(ids[0], date(2026, 6, 1), "sexed"),
        farm_kpis.Breeding(ids[1], date(2026, 6, 2), "sexed"),
        farm_kpis.Breeding(ids[2], date(2026, 7, 1), "conventional"),
        farm_kpis.Breeding(ids[3], date(2026, 7, 2), "conventional"),
        farm_kpis.Breeding(ids[4], date(2026, 11, 10), "conventional"),   # no check yet
        farm_kpis.Breeding(ids[5], date(2026, 8, 1), None),
    ]
    checks = [
        farm_kpis.Check(ids[0], date(2026, 7, 5), "pregnant"),
        farm_kpis.Check(ids[1], date(2026, 7, 5), "not_pregnant"),
        farm_kpis.Check(ids[2], date(2026, 8, 3), "not_pregnant"),
        farm_kpis.Check(ids[2], date(2026, 9, 20), "pregnant"),
        farm_kpis.Check(ids[3], date(2026, 9, 3), "pregnant"),
    ]
    out = farm_kpis.compute(breedings, checks, today)

    assert out["conception"] == {"inseminated": 6, "pregnant": 3, "rate": 50.0}
    assert out["pregnancies_by_month"] == [
        {"month": "2026-07", "pregnant": 1}, {"month": "2026-08", "pregnant": 0},
        {"month": "2026-09", "pregnant": 2}, {"month": "2026-10", "pregnant": 0},
        {"month": "2026-11", "pregnant": 0},
    ]
    # Josh's example order (Sexed Semen, then Conventional), no semen type last.
    assert out["by_semen"] == [
        {"semen_type": "sexed", "inseminated": 2, "pregnant": 1, "rate": 50.0},
        {"semen_type": "conventional", "inseminated": 3, "pregnant": 2, "rate": 66.7},
        {"semen_type": "not recorded", "inseminated": 1, "pregnant": 0, "rate": 0.0},
    ]


def test_a_farm_with_no_breedings_shows_no_rate():
    out = farm_kpis.compute([], [], date(2026, 11, 20))
    assert out == {"conception": {"inseminated": 0, "pregnant": 0, "rate": None},
                   "pregnancies_by_month": [], "by_semen": []}


async def test_the_kpi_page_through_the_api(db, api, farm, tech, make_user):
    cow = await _cow(db, farm, status=CowStatus.pregnant)
    ai = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=TODAY - timedelta(days=40),
                      attempt_number=1, semen_type=SemenType.sexed)
    db.add(ai)
    await db.flush()
    db.add(PregnancyCheck(cow_id=cow.id, insemination_id=ai.id,
                          check_date=TODAY - timedelta(days=5), result=PregnancyResult.pregnant))
    await db.flush()
    stranger = await make_user(UserRole.technician)

    async with api("farm", farm_id=farm.id) as client:
        r = await client.get("/reports/farm-kpis", params={"farm_id": str(farm.id)})
    async with api("technician", user_id=stranger.id) as client:
        other = await client.get("/reports/farm-kpis", params={"farm_id": str(farm.id)})
    assert r.status_code == 200, r.text
    assert r.json()["conception"]["rate"] == 100.0
    assert r.json()["by_semen"][0]["semen_type"] == "sexed"
    assert other.status_code == 404


async def test_an_old_dry_off_notice_does_not_ask(db, api, farm, tech):
    """Before Nov 20 the Day 223 notice told the farm to move her and asked
    nothing; 94 live dry cows have one. It must not sprout Yes / No."""
    cow = await _cow(db, farm, status=CowStatus.dry)
    db.add(Notification(farm_id=farm.id, cow_id=cow.id, type="dry_off",
                        message="has reached day 223 and is now Dry — stop milking her"))
    await db.flush()
    async with api("farm", farm_id=farm.id) as client:
        (listed,) = (await client.get("/notifications/")).json()
    assert listed["asks"] is False


async def test_from_the_profile_a_farm_writes_to_its_own_technician_only(db, api, farm, tech, make_user):
    other = await make_user(UserRole.technician)
    async with api("farm", farm_id=farm.id) as client:
        mine = await _alarm(client, body="Note for you.", kind="note", recipient_id=str(tech.id))
        theirs = await _alarm(client, body="Note for you.", kind="note", recipient_id=str(other.id))
    assert mine.status_code == 201, mine.text
    assert mine.json()["recipient_id"] == str(tech.id)
    assert theirs.status_code == 422


async def test_the_profile_reaches_the_named_technician_on_a_covered_day(db, api, farm, tech, make_user):
    """'Send them a note': on a day someone else covers the farm, a note
    written from the profile still goes to the technician it names, and the
    farm cannot name the cover (no screen does)."""
    from app.models.models import FarmVisitAssignment
    cover = await make_user(UserRole.technician)
    db.add(FarmVisitAssignment(farm_id=farm.id, visit_date=TODAY, assigned_technician_id=cover.id))
    await db.flush()
    async with api("farm", farm_id=farm.id) as client:
        named = await _alarm(client, body="For you.", kind="note", recipient_id=str(tech.id))
        to_cover = await _alarm(client, body="For whoever is here.")
        naming_cover = await _alarm(client, body="For you.", recipient_id=str(cover.id))
    assert named.json()["recipient_id"] == str(tech.id)
    assert to_cover.json()["recipient_id"] == str(cover.id)
    assert naming_cover.status_code == 422


async def test_the_admin_does_not_answer_the_farms_or_technicians_question(db, api, farm, tech):
    """Josh asks the farm (Day 223) and the technician (Day 293); no one else."""
    dry = await _cow(db, farm, status=CowStatus.pregnant, dry_date=TODAY)
    due = await _cow(db, farm, status=CowStatus.dry,
                     last_insemination_date=TODAY - timedelta(days=295))
    await _sweep(db)
    (pen,) = await _notices(db, dry, "dry_pen")
    (birth,) = await _notices(db, due, "birth_check")
    async with api("admin") as client:
        listed = {n["id"]: n for n in (await client.get(
            "/notifications/", params={"farm_id": str(farm.id)})).json()}
        r1 = await client.post(f"/notifications/{pen.id}/answer", json={"answer": "yes"})
        r2 = await client.post(f"/notifications/{birth.id}/answer", json={"answer": "yes"})
    assert (r1.status_code, r2.status_code) == (403, 403)
    assert not listed[str(pen.id)]["can_answer"] and not listed[str(birth.id)]["can_answer"]
    await db.refresh(dry)
    assert dry.dry_off_confirmed_date is None


async def test_each_question_says_who_can_answer_it(db, api, farm, tech):
    dry = await _cow(db, farm, status=CowStatus.pregnant, dry_date=TODAY)
    due = await _cow(db, farm, status=CowStatus.dry,
                     last_insemination_date=TODAY - timedelta(days=295))
    await _sweep(db)
    async with api("farm", farm_id=farm.id) as client:
        as_farm = {n["type"]: n["can_answer"] for n in (await client.get("/notifications/")).json()
                   if n["cow_id"] in (str(dry.id), str(due.id))}
    async with api("technician", user_id=tech.id) as client:
        as_tech = {n["type"]: n["can_answer"] for n in (await client.get("/notifications/")).json()
                   if n["cow_id"] in (str(dry.id), str(due.id))}
    assert as_farm == {"dry_pen": True}          # the farm never sees the birth check
    assert as_tech == {"birth_check": True}      # the technician never sees the dry pen


async def test_answering_a_question_marks_it_read(db, api, farm, tech):
    cow = await _cow(db, farm, status=CowStatus.pregnant, dry_date=TODAY)
    await _sweep(db)
    (notice,) = await _notices(db, cow, "dry_pen")
    owner = uuid.uuid4()
    db.add(User(id=owner, name="Owner", email=f"{owner.hex[:8]}@test.local", role=UserRole.farm))
    await db.flush()
    async with api("farm", user_id=owner, farm_id=farm.id) as client:
        await client.post(f"/notifications/{notice.id}/answer", json={"answer": "no"})
        (listed,) = [n for n in (await client.get("/notifications/")).json() if n["id"] == str(notice.id)]
    assert listed["read"] is True


async def test_a_new_pregnancy_gets_its_own_birth_check(db, farm):
    """The one-per-breeding rule must not stop the next pregnancy's question."""
    cow = await _cow(db, farm, status=CowStatus.dry,
                     last_insemination_date=TODAY - timedelta(days=300))
    old = Notification(farm_id=farm.id, cow_id=cow.id, type="birth_check", message="earlier",
                       created_at=datetime.now(timezone.utc) - timedelta(days=400))
    db.add(old)
    await db.flush()
    await _sweep(db)
    assert len(await _notices(db, cow, "birth_check")) == 2


async def test_only_an_alarm_or_note_is_acknowledged(db, api, farm, tech):
    async with api("admin") as client:
        sent = (await client.post("/messages/", json={
            "channel": "office_alert", "body": "Start at Cedar Lane.",
            "recipient_id": str(tech.id)})).json()
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/messages/{sent['id']}/acknowledge")
    assert r.status_code == 422
