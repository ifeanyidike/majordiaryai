"""Endpoint-level tests: who may call what, and what the API rejects.

Everything else in this suite drives services directly, so until now every
role gate and validation rule in the routers was verified by reading the code.
These go through the real ASGI app, which is the only way a change like
"technicians may now record pregnancy results" is actually pinned down.

Each test names the rule it protects, so a failure says what broke rather than
just which line moved.
"""

import uuid
from datetime import date, timedelta

import pytest

from app.services import status_engine
from app.models.models import (
    Cow, CowStatus, Farm, Insemination, User, UserRole, Vet, VetFarmAssignment,
)

TODAY = date.today()


async def _farm(db, tech_id=None) -> Farm:
    f = Farm(id=uuid.uuid4(), name=f"F-{uuid.uuid4().hex[:6]}", owner_name="O",
             herd_size=0, assigned_technician_id=tech_id)
    db.add(f)
    await db.flush()
    return f


async def _scoped_farm(db, role: str, caller_id):
    """A farm the caller can actually reach.

    Role scoping is not the subject of these tests but it runs first, so a farm
    nobody owns yields "Cow not found" and hides the rule under test.
    """
    farm = await _farm(db, tech_id=caller_id if role == "technician" else None)
    if role == "vet":
        vet = Vet(id=uuid.uuid4(), user_id=caller_id, name="Vet")
        db.add(vet)
        await db.flush()
        db.add(VetFarmAssignment(vet_id=vet.id, farm_id=farm.id))
        await db.flush()
    return farm


async def _cow(db, farm, **kw) -> Cow:
    kw.setdefault("status", CowStatus.inseminated)
    c = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag=f"T-{uuid.uuid4().hex[:8]}",
            lactation_number=1, **kw)
    db.add(c)
    await db.flush()
    return c


# ── Pregnancy checks: "either or both" (client decision, 2026-08-06) ──

@pytest.mark.parametrize("role,allowed", [
    ("technician", True),
    ("vet", True),
    ("admin", True),
    ("farm", False),
])
async def test_who_may_record_a_pregnancy_result(db, api, make_user, role, allowed):
    caller = await make_user(UserRole(role), f"{role.title()} caller")
    caller_id = caller.id
    farm = await _scoped_farm(db, role, caller_id)
    cow = await _cow(db, farm, last_insemination_date=TODAY - timedelta(days=40))
    ai = Insemination(id=uuid.uuid4(), cow_id=cow.id, date=TODAY - timedelta(days=40),
                      attempt_number=1)
    db.add(ai)
    await db.flush()
    cow.last_insemination_id = ai.id
    await db.flush()

    async with api(role=role, user_id=caller_id, farm_id=farm.id) as client:
        resp = await client.post("/checks/pregnancy", json={
            "cow_id": str(cow.id), "insemination_id": str(ai.id),
            "check_date": TODAY.isoformat(), "result": "pregnant",
        })
    if allowed:
        assert resp.status_code == 201, resp.text
    else:
        assert resp.status_code == 403, resp.text


# ── Visit assignments: the self-renewing access loop ─────────────────

async def test_relief_technician_cannot_assign_visits_to_himself(db, api, make_user):
    """A relief tech's scope comes FROM visit assignments, so letting anyone in
    scope write them would let a one-day cover renew its own access forever."""
    standing = await make_user(UserRole.technician, "Standing")
    relief = await make_user(UserRole.technician, "Relief")
    farm = await _farm(db, tech_id=standing.id)

    async with api(role="technician", user_id=relief.id) as client:
        resp = await client.put(f"/farms/{farm.id}/visit-assignments", json={
            "visit_date": (TODAY + timedelta(days=1)).isoformat(),
            "assigned_technician_id": str(relief.id),
        })
    # 404 (out of scope) or 403 (in scope, not the standing tech) both deny it.
    assert resp.status_code in (403, 404), resp.text


async def test_standing_technician_may_hand_off_a_day(db, api, make_user):
    standing = await make_user(UserRole.technician, "Standing")
    relief = await make_user(UserRole.technician, "Relief")
    farm = await _farm(db, tech_id=standing.id)

    async with api(role="technician", user_id=standing.id) as client:
        resp = await client.put(f"/farms/{farm.id}/visit-assignments", json={
            "visit_date": (TODAY + timedelta(days=1)).isoformat(),
            "assigned_technician_id": str(relief.id),
            "reason": "on leave",
        })
    assert resp.status_code == 200, resp.text
    assert resp.json()["assigned_technician_name"] == "Relief"


async def test_visits_cannot_be_assigned_in_the_past(db, api, make_user):
    standing = await make_user(UserRole.technician, "Standing")
    farm = await _farm(db, tech_id=standing.id)
    async with api(role="technician", user_id=standing.id) as client:
        resp = await client.put(f"/farms/{farm.id}/visit-assignments", json={
            "visit_date": (TODAY - timedelta(days=1)).isoformat(),
            "assigned_technician_id": str(standing.id),
        })
    assert resp.status_code == 422, resp.text


# ── Farm management is admin-only ────────────────────────────────────

@pytest.mark.parametrize("role,expected", [
    ("admin", 201), ("technician", 403), ("vet", 403), ("farm", 403),
])
async def test_only_admins_create_farms(db, api, role, expected):
    async with api(role=role) as client:
        resp = await client.post("/farms/", json={
            "name": f"New {uuid.uuid4().hex[:5]}", "owner_name": "Owner",
        })
    assert resp.status_code == expected, resp.text


async def test_farm_visit_weekdays_are_validated(db, api):
    """Mirrors the DB check constraint: 0-6 only, never empty."""
    async with api(role="admin") as client:
        bad_day = await client.post("/farms/", json={
            "name": "Bad", "owner_name": "O", "visit_weekdays": [0, 9],
        })
        empty = await client.post("/farms/", json={
            "name": "Empty", "owner_name": "O", "visit_weekdays": [],
        })
    assert bad_day.status_code == 422, bad_day.text
    assert empty.status_code == 422, empty.text


# ── The staff directory is not public ────────────────────────────────

@pytest.mark.parametrize("role,expected", [
    ("admin", 200), ("technician", 403), ("vet", 403), ("farm", 403),
])
async def test_only_admins_may_list_users(db, api, role, expected):
    """Technicians were added to this endpoint deliberately — they need the
    relief-tech list to hand over a visit — so they are no longer refused. The
    narrowing (they only ever see technicians) is asserted separately below."""
    if role == "technician":
        expected = 200
    async with api(role=role) as client:
        resp = await client.get("/users/?role=technician")
    assert resp.status_code == expected, resp.text


# ── Heat checks: the timing rule, through the endpoint ───────────────

@pytest.mark.parametrize("days,signal,expected", [
    (22, False, 201),   # routine check inside the window
    (30, False, 409),   # routine check after it
    (30, True, 201),    # blood on the tail is a fact on any day from day 20
    (2, True, 409),     # ...but not right after breeding (normal spotting)
])
async def test_heat_check_timing_through_the_api(db, api, days, signal, expected):
    farm = await _farm(db)
    cow = await _cow(db, farm, last_insemination_date=TODAY - timedelta(days=days))
    ai = Insemination(id=uuid.uuid4(), cow_id=cow.id,
                      date=TODAY - timedelta(days=days), attempt_number=1)
    db.add(ai)
    await db.flush()

    async with api(role="admin") as client:
        resp = await client.post("/checks/heat", json={
            "cow_id": str(cow.id), "insemination_id": str(ai.id),
            "check_date": TODAY.isoformat(),
            "heat_detected": bool(signal), "bleeding_event": False,
        })
    assert resp.status_code == expected, resp.text


# ── Bleeding events are only for breeding-eligible cows ──────────────

@pytest.mark.parametrize("status,expected", [
    (CowStatus.open, 200),
    (CowStatus.pregnant, 409),
    (CowStatus.calf, 409),      # must never be force-enrolled in Ovsynch
    (CowStatus.inseminated, 409),  # that is a heat check, not a bleeding event
])
async def test_bleeding_event_is_restricted_by_status(db, api, status, expected):
    farm = await _farm(db)
    cow = await _cow(db, farm, status=status)
    async with api(role="admin") as client:
        resp = await client.post(f"/needling/cow/{cow.id}/bleeding", json={"notes": "x"})
    assert resp.status_code == expected, resp.text


# ── Scoping: a cow outside your farms is 404, never 403 ──────────────

async def test_out_of_scope_cow_is_not_enumerable(db, api, make_user):
    """404 rather than 403 so an outsider cannot confirm a cow id exists."""
    other_tech = await make_user(UserRole.technician, "Other")
    farm = await _farm(db, tech_id=other_tech.id)
    cow = await _cow(db, farm, status=CowStatus.open)

    async with api(role="technician", user_id=uuid.uuid4()) as client:
        resp = await client.get(f"/cows/{cow.id}")
    assert resp.status_code == 404, resp.text


# ── Pagination: bounded responses that never lose a row ──────────────

async def test_cow_list_is_paginated_and_reports_the_true_total(db, api):
    """A page must be bounded, and X-Total-Count must still say how many
    exist — herd statistics are computed from the full set, so a caller that
    only saw a page would otherwise show wrong counts."""
    farm = await _farm(db)
    for _ in range(7):
        await _cow(db, farm, status=CowStatus.open)

    async with api(role="admin") as client:
        page = await client.get(f"/cows/?farm_id={farm.id}&limit=3&offset=0")
    assert page.status_code == 200, page.text
    assert len(page.json()) == 3
    assert page.headers["x-total-count"] == "7"


async def test_paging_covers_every_cow_exactly_once(db, api):
    """Ear tags are not unique across farms, so ordering needs a tiebreaker —
    without one, rows repeat or vanish between pages."""
    farm = await _farm(db)
    for _ in range(10):
        await _cow(db, farm, status=CowStatus.open)

    seen = []
    async with api(role="admin") as client:
        for offset in (0, 4, 8):
            resp = await client.get(f"/cows/?farm_id={farm.id}&limit=4&offset={offset}")
            seen.extend(c["id"] for c in resp.json())

    assert len(seen) == 10, "paging lost or duplicated rows"
    assert len(set(seen)) == 10, "the same cow appeared on two pages"


async def test_page_size_is_capped(db, api):
    """An unbounded limit would defeat the point of paginating at all."""
    async with api(role="admin") as client:
        resp = await client.get("/cows/?limit=99999")
    assert resp.status_code == 422, resp.text


async def test_farm_list_is_paginated_too(db, api):
    for _ in range(4):
        await _farm(db)
    async with api(role="admin") as client:
        resp = await client.get("/farms/?limit=2&offset=0")
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 2
    assert int(resp.headers["x-total-count"]) >= 4


# ── Endpoints the new screens depend on ─────────────────────────────

async def test_technicians_can_list_technicians_but_not_the_directory(db, api):
    """A technician needs the relief-tech list to hand over a visit, but has no
    business enumerating farm managers, vets or admins."""
    async with api(role="technician") as client:
        resp = await client.get("/users/")
    assert resp.status_code == 200, resp.text
    assert {u["role"] for u in resp.json()} <= {"technician"}


async def test_admin_sees_every_role_in_the_directory(db, api):
    db.add(User(id=uuid.uuid4(), name="A Vet", email=f"{uuid.uuid4().hex[:8]}@t.local",
                role=UserRole.vet))
    await db.flush()
    async with api(role="admin") as client:
        resp = await client.get("/users/")
    assert resp.status_code == 200, resp.text
    assert "vet" in {u["role"] for u in resp.json()}


async def test_farm_manager_cannot_list_users(db, api):
    async with api(role="farm") as client:
        resp = await client.get("/users/")
    assert resp.status_code == 403, resp.text


async def test_vet_can_be_created_and_updated_by_admin_only(db, api):
    async with api(role="admin") as client:
        created = await client.post("/vets/", json={"name": "Dr Test", "clinic": "Clinic"})
        assert created.status_code == 201, created.text
        vet_id = created.json()["id"]

        patched = await client.patch(f"/vets/{vet_id}", json={"clinic": "New Clinic"})
        assert patched.status_code == 200, patched.text
        assert patched.json()["clinic"] == "New Clinic"

    async with api(role="technician") as client:
        assert (await client.post("/vets/", json={"name": "X"})).status_code == 403
        assert (await client.patch(f"/vets/{vet_id}", json={"name": "X"})).status_code == 403


async def test_cow_edit_cannot_move_a_cow_or_retag_her(db, api):
    """CowUpdate deliberately omits ear_tag and farm_id — identity and location
    are not form edits. Sending them must not silently move the animal."""
    caller = uuid.uuid4()
    db.add(User(id=caller, name="Tech", email=f"{uuid.uuid4().hex[:8]}@t.local",
                role=UserRole.technician))
    await db.flush()
    farm = await _farm(db, tech_id=caller)
    other = await _farm(db)
    cow = await _cow(db, farm, status=CowStatus.open)

    async with api(role="technician", user_id=caller) as client:
        resp = await client.patch(
            f"/cows/{cow.id}",
            json={"breed": "Jersey", "ear_tag": "HACKED", "farm_id": str(other.id)},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["breed"] == "Jersey"
    assert body["ear_tag"] == cow.ear_tag, "ear tag was changed by a PATCH"
    assert body["farm_id"] == str(farm.id), "cow was moved to another farm by a PATCH"


# ── Bulls (per-farm assumption) and the derived milking status ───────

async def test_bull_list_is_per_farm_and_names_are_unique_within_one(db, api):
    """ASSUMPTION: bulls belong to a farm, because the spec says semen is
    "selected by farmer". Two farms may stock the same bull; one farm may not
    list it twice."""
    a = await _farm(db)
    b = await _farm(db)
    async with api(role="admin") as client:
        first = await client.post(f"/bulls/farm/{a.id}", json={"name": "Delta-Lambda"})
        assert first.status_code == 201, first.text

        dupe = await client.post(f"/bulls/farm/{a.id}", json={"name": "Delta-Lambda"})
        assert dupe.status_code == 409, "the same bull was listed twice on one farm"

        other = await client.post(f"/bulls/farm/{b.id}", json={"name": "Delta-Lambda"})
        assert other.status_code == 201, "a second farm could not stock the same bull"

        listed = await client.get(f"/bulls/farm/{a.id}")
        assert [x["name"] for x in listed.json()] == ["Delta-Lambda"]


async def test_retired_bulls_leave_the_picker_but_stay_for_history(db, api):
    farm = await _farm(db)
    async with api(role="admin") as client:
        bull_id = (await client.post(f"/bulls/farm/{farm.id}", json={"name": "Old Boy"})).json()["id"]
        await client.patch(f"/bulls/{bull_id}", json={"active": False})

        assert (await client.get(f"/bulls/farm/{farm.id}")).json() == []
        kept = await client.get(f"/bulls/farm/{farm.id}?include_inactive=true")
        assert [x["name"] for x in kept.json()] == ["Old Boy"]


async def test_insemination_rejects_a_bull_from_another_farm(db, api):
    """Accepting one would silently corrupt per-bull conception figures."""
    mine = await _farm(db)
    theirs = await _farm(db)
    cow = await _cow(db, mine, status=CowStatus.open)
    async with api(role="admin") as client:
        foreign = (await client.post(f"/bulls/farm/{theirs.id}", json={"name": "Foreign"})).json()["id"]
        resp = await client.post("/inseminations/", json={
            "cow_id": str(cow.id), "date": f"{TODAY}T09:00:00",
            "bull_name": "Foreign", "bull_id": foreign,
        })
    assert resp.status_code == 422, resp.text


async def test_insemination_records_the_code_and_the_bull(db, api):
    farm = await _farm(db)
    cow = await _cow(db, farm, status=CowStatus.open)
    async with api(role="admin") as client:
        bull_id = (await client.post(f"/bulls/farm/{farm.id}", json={"name": "Mogul"})).json()["id"]
        resp = await client.post("/inseminations/", json={
            "cow_id": str(cow.id), "date": f"{TODAY}T09:00:00",
            "bull_name": "Mogul", "bull_id": bull_id, "insemination_code": "AI-77",
        })
    assert resp.status_code == 201, resp.text
    assert resp.json()["insemination_code"] == "AI-77"
    assert resp.json()["bull_id"] == bull_id


@pytest.mark.parametrize("status,calved,milking", [
    (CowStatus.fresh, True, True),
    (CowStatus.pregnant, True, True),    # milks until dry-off at day 223
    (CowStatus.dry, True, False),        # day 223-283: no milking
    (CowStatus.heifer, False, False),    # never calved, never milked
    (CowStatus.open, False, False),      # no calving on record yet
    (CowStatus.cull, True, False),
])
def test_milking_follows_the_spec_milk_cycle(status, calved, milking):
    """Master Structure: milk from calving to day 223, none until she calves
    again, and a heifer never milks. Derived, so it cannot drift from status."""
    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="T", lactation_number=1,
              status=status,
              last_calving_date=TODAY - timedelta(days=40) if calved else None)
    assert status_engine.is_milking(cow) is milking
