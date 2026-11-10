"""Admin, Technicians and Routes (feature notes, Nov 10).

Technicians: a list of all technicians, each one's profile editable, and a new
one can be added. Routes: open a technician, check farms, Reassign, pick the
technician who takes them; one message to each of the two.
"""

import json
import logging
import types
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.models.models import Farm, Message, MessageChannel, User, UserRole
from app.services import auth_admin


@pytest.fixture
def logins(monkeypatch):
    """Supabase Auth, recorded instead of called."""
    calls = {"created": [], "deleted": [], "emails": [], "taken": False}

    async def create_login(email, password):
        if calls["taken"]:
            raise auth_admin.LoginError("email_exists", taken=True)
        login_id = uuid.uuid4()
        calls["created"].append((login_id, email, password))
        return login_id

    async def delete_login(user_id):
        calls["deleted"].append(user_id)

    async def change_email(user_id, email):
        calls["emails"].append((user_id, email))

    monkeypatch.setattr(auth_admin, "create_login", create_login)
    monkeypatch.setattr(auth_admin, "delete_login", delete_login)
    monkeypatch.setattr(auth_admin, "change_email", change_email)
    return calls


def _new_tech(**kw) -> dict:
    return {"name": "Sam Carter", "email": f"sam-{uuid.uuid4().hex[:6]}@example.com",
            "password": "first-pass-1", "phone": "555-0100", "employee_id": "T-7",
            "region": "North", **kw}


# ── Technicians ──────────────────────────────────────────────────────

async def test_an_admin_adds_a_technician_who_can_sign_in_at_once(api, db, logins):
    body = _new_tech(email="Sam.Carter@Example.com")
    async with api("admin") as client:
        r = await client.post("/users/technicians", json=body)
        assert r.status_code == 201, r.text
        listed = (await client.get("/users/", params={"role": "technician"})).json()

    out = r.json()
    (login_id, email, password) = logins["created"][0]
    assert out["id"] == str(login_id)  # the profile is the login's
    assert email == "sam.carter@example.com" and password == "first-pass-1"
    assert out["role"] == "technician" and out["is_active"] is True
    assert (out["phone"], out["employee_id"], out["region"]) == ("555-0100", "T-7", "North")
    assert any(u["id"] == out["id"] for u in listed)


async def test_an_email_already_on_an_account_is_refused_before_any_login_is_made(
        api, db, logins, make_user):
    existing = await make_user(UserRole.technician)
    existing.email = f"taken-{uuid.uuid4().hex[:6]}@example.com"
    await db.flush()
    async with api("admin") as client:
        r = await client.post("/users/technicians", json=_new_tech(email=existing.email.upper()))
    assert r.status_code == 409, r.text
    assert logins["created"] == []


async def test_an_email_the_sign_in_service_already_has_is_refused(api, db, logins):
    logins["taken"] = True
    async with api("admin") as client:
        r = await client.post("/users/technicians", json=_new_tech())
    assert r.status_code == 409, r.text
    assert "already exists" in r.json()["detail"]


async def test_a_login_whose_profile_cannot_be_saved_is_removed(api, db, logins, monkeypatch):
    from app.routers import users as users_router

    clash = User(id=uuid.uuid4(), name="Clash", email=f"clash-{uuid.uuid4().hex[:6]}@example.com",
                 role=UserRole.technician)
    db.add(clash)
    await db.commit()

    async def never_in_use(*a, **k):
        return False  # the moment between the check and the save

    monkeypatch.setattr(users_router, "_email_in_use", never_in_use)
    async with api("admin") as client:
        r = await client.post("/users/technicians", json=_new_tech(email=clash.email))
    assert r.status_code == 409, r.text
    assert logins["deleted"] == [logins["created"][0][0]]


@pytest.mark.parametrize("role", ["technician", "farm", "vet"])
async def test_only_an_admin_adds_technicians(api, db, logins, role):
    async with api(role) as client:
        r = await client.post("/users/technicians", json=_new_tech())
    assert r.status_code == 403
    assert logins["created"] == []


async def test_a_test_login_can_be_added_and_edited(api, db, logins, make_user):
    # Every test account is @majordairy.test, a reserved domain.
    tech = await make_user(UserRole.technician)
    tech.email = f"tech-{uuid.uuid4().hex[:6]}@majordairy.test"
    await db.flush()
    async with api("admin") as client:
        added = await client.post("/users/technicians",
                                  json=_new_tech(email=f"t2-{uuid.uuid4().hex[:6]}@majordairy.test"))
        edited = await client.patch(f"/users/{tech.id}", json={"email": tech.email, "phone": "555-0101"})
        bad = await client.patch(f"/users/{tech.id}", json={"email": "not-an-email"})
    assert added.status_code == 201, added.text
    assert edited.status_code == 200, edited.text
    assert bad.status_code == 422
    assert logins["emails"] == []  # an unchanged email never touches the login


async def test_a_first_password_needs_eight_characters(api, db, logins):
    async with api("admin") as client:
        r = await client.post("/users/technicians", json=_new_tech(password="short"))
    assert r.status_code == 422


async def test_an_admin_edits_a_technician_including_their_sign_in_email(api, db, logins, make_user):
    tech = await make_user(UserRole.technician, "Old Name")
    async with api("admin") as client:
        r = await client.patch(f"/users/{tech.id}", json={
            "name": "New Name", "email": "New.Address@Example.com", "phone": "555-0199",
            "employee_id": "T-9", "region": "South",
        })
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["name"], out["email"], out["phone"], out["employee_id"], out["region"]) == \
        ("New Name", "new.address@example.com", "555-0199", "T-9", "South")
    assert logins["emails"] == [(tech.id, "new.address@example.com")]


async def test_an_email_someone_else_has_is_refused_and_their_login_is_untouched(
        api, db, logins, make_user):
    tech = await make_user(UserRole.technician)
    other = await make_user(UserRole.technician)
    other.email = f"other-{uuid.uuid4().hex[:6]}@example.com"
    await db.flush()
    async with api("admin") as client:
        r = await client.patch(f"/users/{tech.id}", json={"email": other.email})
    assert r.status_code == 409, r.text
    assert logins["emails"] == []


async def test_saving_the_same_email_does_not_touch_their_login(api, db, logins, make_user):
    tech = await make_user(UserRole.technician)
    tech.email = f"same-{uuid.uuid4().hex[:6]}@example.com"
    await db.flush()
    async with api("admin") as client:
        r = await client.patch(f"/users/{tech.id}", json={"email": tech.email.upper(), "name": "Same"})
    assert r.status_code == 200, r.text
    assert logins["emails"] == []


# ── The sign-in service itself ───────────────────────────────────────

def _supabase(monkeypatch, handler):
    """auth_admin's own HTTP calls, answered by `handler` (the test client is left alone)."""
    fake = types.SimpleNamespace(
        HTTPError=httpx.HTTPError, Response=httpx.Response,
        AsyncClient=lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(auth_admin, "httpx", fake)


async def test_a_sign_in_service_that_cannot_be_reached_is_try_again_not_a_crash(
        api, db, monkeypatch):
    def down(request):
        raise httpx.ConnectTimeout("no answer")
    _supabase(monkeypatch, down)
    async with api("admin") as client:
        r = await client.post("/users/technicians", json=_new_tech())
    assert r.status_code == 502, r.text
    assert "Try again" in r.json()["detail"]


async def test_supabase_saying_the_email_exists_is_read_as_taken(api, db, monkeypatch):
    def exists(request):
        return httpx.Response(422, json={
            "code": 422, "error_code": "email_exists",
            "msg": "A user with this email address has already been registered"})
    _supabase(monkeypatch, exists)
    async with api("admin") as client:
        r = await client.post("/users/technicians", json=_new_tech())
    assert r.status_code == 409, r.text


async def test_a_new_login_is_made_confirmed_with_the_service_key(api, db, monkeypatch):
    seen = []
    new_id = uuid.uuid4()
    def ok(request):
        seen.append(request)
        return httpx.Response(200, json={"id": str(new_id)})
    _supabase(monkeypatch, ok)
    async with api("admin") as client:
        r = await client.post("/users/technicians", json=_new_tech(email="new@example.com"))
    assert r.status_code == 201, r.text
    assert r.json()["id"] == str(new_id)
    (req,) = seen
    assert req.method == "POST" and req.url.path == "/auth/v1/admin/users"
    assert req.headers["apikey"] == auth_admin.settings.supabase_service_key
    assert json.loads(req.content) == {
        "email": "new@example.com", "password": "first-pass-1", "email_confirm": True}


async def test_an_unknown_farm_is_refused_before_the_login_email_changes(
        api, db, logins, make_user):
    manager = await make_user(UserRole.farm)
    async with api("admin") as client:
        r = await client.patch(f"/users/{manager.id}", json={
            "email": f"n-{uuid.uuid4().hex[:6]}@example.com", "farm_id": str(uuid.uuid4())})
    assert r.status_code == 422, r.text  # was a 500 from the foreign key
    assert logins["emails"] == []  # the login was never touched


async def test_a_failed_undo_is_logged_and_the_admin_still_hears_the_real_problem(
        api, db, logins, make_user, monkeypatch, caplog):
    from app.routers import users as users_router
    tech = await make_user(UserRole.technician)
    other = await make_user(UserRole.technician)
    other.email = f"other-{uuid.uuid4().hex[:6]}@example.com"
    await db.flush()

    async def never_in_use(*a, **k):
        return False  # someone took the email between the check and the save

    async def change_email(user_id, email):
        logins["emails"].append((user_id, email))
        if len(logins["emails"]) > 1:
            raise auth_admin.LoginError("service down")

    monkeypatch.setattr(users_router, "_email_in_use", never_in_use)
    monkeypatch.setattr(auth_admin, "change_email", change_email)
    with caplog.at_level(logging.ERROR, logger="app.auth_admin"):
        async with api("admin") as client:
            r = await client.patch(f"/users/{tech.id}", json={"email": other.email})
    assert r.status_code == 409, r.text
    assert str(tech.id) in caplog.text and "put the old email back" in caplog.text


# ── Routes ───────────────────────────────────────────────────────────

async def _farms(db, tech, *names):
    out = []
    for name in names:
        f = Farm(id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:4]}", owner_name="Owner",
                 herd_size=0, assigned_technician_id=tech.id if tech else None)
        db.add(f)
        out.append(f)
    await db.flush()
    return out


async def _office_alerts(db, *recipients):
    return (await db.execute(select(Message).where(
        Message.channel == MessageChannel.office_alert,
        Message.recipient_id.in_([r.id for r in recipients]),
    ))).scalars().all()


def _move(farms, src, dst) -> dict:
    return {"farm_ids": [str(f.id) for f in farms],
            "from_technician_id": str(src.id), "to_technician_id": str(dst.id)}


async def test_checked_farms_move_and_each_technician_gets_one_message(
        api, db, make_user, sent_pushes):
    giver = await make_user(UserRole.technician, "Giver")
    taker = await make_user(UserRole.technician, "Taker")
    one, kept, two = await _farms(db, giver, "Alder", "Birch", "Cedar")

    async with api("admin") as client:
        r = await client.post("/farms/reassign", json=_move([one, two], giver, taker))
    assert r.status_code == 200, r.text
    assert {f["id"] for f in r.json()} == {str(one.id), str(two.id)}

    for f in (one, kept, two):
        await db.refresh(f)
    assert (one.assigned_technician_id, two.assigned_technician_id) == (taker.id, taker.id)
    assert kept.assigned_technician_id == giver.id  # not checked, not moved

    alerts = await _office_alerts(db, giver, taker)
    by = {m.recipient_id: m for m in alerts}
    assert len(alerts) == 2 and set(by) == {giver.id, taker.id}
    assert by[giver.id].body == f"{one.name} and {two.name} are no longer on your route."
    assert by[taker.id].body == f"{one.name} and {two.name} have been added to your route."
    assert by[giver.id].farm_id is None  # two farms: nothing single to open
    assert len(sent_pushes) == 2


async def test_one_farm_moved_links_the_message_to_it(api, db, make_user):
    giver = await make_user(UserRole.technician)
    taker = await make_user(UserRole.technician)
    (only,) = await _farms(db, giver, "Dairy")
    async with api("admin") as client:
        r = await client.post("/farms/reassign", json=_move([only], giver, taker))
    assert r.status_code == 200, r.text
    alerts = await _office_alerts(db, giver, taker)
    assert {m.farm_id for m in alerts} == {only.id}
    assert {m.body for m in alerts} == {
        f"{only.name} is no longer on your route.", f"{only.name} has been added to your route."}


async def test_the_taker_can_open_the_farm_and_the_giver_cannot(api, db, make_user):
    giver = await make_user(UserRole.technician)
    taker = await make_user(UserRole.technician)
    (moved,) = await _farms(db, giver, "Elm")
    async with api("admin") as client:
        assert (await client.post("/farms/reassign", json=_move([moved], giver, taker))).status_code == 200
    async with api("technician", user_id=taker.id) as client:
        assert (await client.get(f"/farms/{moved.id}")).status_code == 200
    async with api("technician", user_id=giver.id) as client:
        assert (await client.get(f"/farms/{moved.id}")).status_code == 404


async def test_a_farm_that_left_the_route_since_the_page_opened_stops_the_move(api, db, make_user):
    giver = await make_user(UserRole.technician)
    taker = await make_user(UserRole.technician)
    someone = await make_user(UserRole.technician)
    still, gone = await _farms(db, giver, "Fir", "Gum")
    gone.assigned_technician_id = someone.id
    await db.flush()

    async with api("admin") as client:
        r = await client.post("/farms/reassign", json=_move([still, gone], giver, taker))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == f"{gone.name} is no longer on this route. Reload and try again."
    await db.refresh(still)
    assert still.assigned_technician_id == giver.id  # nothing moved
    assert await _office_alerts(db, giver, taker) == []


async def test_who_cannot_receive_farms(api, db, make_user):
    giver = await make_user(UserRole.technician)
    vet = await make_user(UserRole.vet)
    pending = await make_user(UserRole.technician, "Pending")
    pending.is_active = False
    await db.flush()
    (f,) = await _farms(db, giver, "Hazel")
    async with api("admin") as client:
        same = await client.post("/farms/reassign", json=_move([f], giver, giver))
        not_a_tech = await client.post("/farms/reassign", json=_move([f], giver, vet))
        waiting = await client.post("/farms/reassign", json=_move([f], giver, pending))
    assert same.status_code == 422
    assert not_a_tech.status_code == 422
    assert waiting.status_code == 422 and "approval" in waiting.json()["detail"]
    await db.refresh(f)
    assert f.assigned_technician_id == giver.id


async def test_an_unknown_farm_moves_nothing(api, db, make_user):
    giver = await make_user(UserRole.technician)
    taker = await make_user(UserRole.technician)
    (f,) = await _farms(db, giver, "Ivy")
    body = _move([f], giver, taker)
    body["farm_ids"].append(str(uuid.uuid4()))
    async with api("admin") as client:
        r = await client.post("/farms/reassign", json=body)
    assert r.status_code == 404
    await db.refresh(f)
    assert f.assigned_technician_id == giver.id


@pytest.mark.parametrize("role", ["technician", "farm", "vet"])
async def test_only_an_admin_reassigns(api, db, make_user, role):
    giver = await make_user(UserRole.technician)
    taker = await make_user(UserRole.technician)
    (f,) = await _farms(db, giver, "Juniper")
    async with api(role, user_id=giver.id if role == "technician" else None) as client:
        r = await client.post("/farms/reassign", json=_move([f], giver, taker))
    assert r.status_code == 403
