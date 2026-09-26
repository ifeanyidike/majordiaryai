"""Alarms and Office Alerts wake the recipient's phone.

Before this, both were in-app only: an owner raising "the cow in pen 4 is
down" reached the technician whenever he next opened the app. These tests pin
who gets woken, when (only after the message is really saved), and that the
device registry can't be abused or silted up with dead phones.
"""

import uuid

from sqlalchemy import select

from app.models.models import MessageChannel, PushToken, UserRole
from app.services import messaging, push

TOKEN_A = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaaaa]"
TOKEN_B = "ExponentPushToken[bbbbbbbbbbbbbbbbbbbbbb]"


# ── who is woken, and when ───────────────────────────────────────────

async def test_an_alarm_wakes_the_farms_technician(api, db, farm, make_user, sent_pushes):
    tech = await make_user(UserRole.technician)
    farm.assigned_technician_id = tech.id
    await db.flush()

    async with api("farm", farm_id=farm.id) as client:
        r = await client.post("/messages/", json={
            "channel": "alarm", "body": "Cow in pen 4 is down, come today."})
    assert r.status_code == 201, r.text

    assert len(sent_pushes) == 1
    user_id, title, body, data, channel = sent_pushes[0]
    assert user_id == tech.id
    assert title == f"Alarm · {farm.name}"
    assert "pen 4" in body
    assert channel == "alarm"
    # What the app needs to open the right feed when he taps it.
    assert data == {"channel": "alarm", "message_id": r.json()["id"]}


async def test_a_route_change_wakes_both_technicians(api, db, farm, make_user, sent_pushes):
    outgoing = await make_user(UserRole.technician, "Outgoing")
    incoming = await make_user(UserRole.technician, "Incoming")
    admin = await make_user(UserRole.admin)
    farm.assigned_technician_id = outgoing.id
    await db.flush()

    async with api("admin", user_id=admin.id) as client:
        r = await client.patch(f"/farms/{farm.id}",
                               json={"assigned_technician_id": str(incoming.id)})
    assert r.status_code == 200, r.text

    woken = {p[0] for p in sent_pushes}
    assert woken == {outgoing.id, incoming.id}
    assert all(p[4] == "office_alert" for p in sent_pushes)


async def test_a_message_that_rolls_back_wakes_nobody(db, farm, make_user, sent_pushes):
    """Queued on the session, sent only after COMMIT — a phone must never
    buzz for a message that does not exist."""
    tech = await make_user(UserRole.technician)
    admin = await make_user(UserRole.admin)

    await messaging.send(db, MessageChannel.office_alert, admin.id, tech.id, "never saved")
    await db.rollback()

    assert sent_pushes == []


async def test_a_refused_message_wakes_nobody(api, db, farm, make_user, sent_pushes):
    tech = await make_user(UserRole.technician)
    async with api("farm", farm_id=farm.id) as client:
        r = await client.post("/messages/", json={
            "channel": "office_alert", "body": "not allowed", "recipient_id": str(tech.id)})
    assert r.status_code == 403
    assert sent_pushes == []


# ── the device registry ──────────────────────────────────────────────

async def test_a_phone_registers_once_and_moves_with_the_person_signed_in(
    api, db, make_user,
):
    first = await make_user(UserRole.technician, "First")
    second = await make_user(UserRole.technician, "Second")

    async with api("technician", user_id=first.id) as client:
        assert (await client.post("/users/me/push-token",
                                  json={"token": TOKEN_A, "platform": "android"})).status_code == 204
        # Every app start re-registers; that must not duplicate the row.
        assert (await client.post("/users/me/push-token",
                                  json={"token": TOKEN_A, "platform": "android"})).status_code == 204

    async with api("technician", user_id=second.id) as client:
        assert (await client.post("/users/me/push-token",
                                  json={"token": TOKEN_A})).status_code == 204

    rows = (await db.execute(select(PushToken).where(PushToken.token == TOKEN_A))).scalars().all()
    assert len(rows) == 1
    # A handed-over phone stops waking its previous owner.
    assert rows[0].user_id == second.id


async def test_only_an_expo_token_is_accepted(api, db, make_user):
    """Anything else stored would make Expo reject the whole batch it rides in,
    taking other devices' alarms down with it."""
    tech = await make_user(UserRole.technician)
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/users/me/push-token", json={"token": "fcm:abcdefghijklmnop"})
    assert r.status_code == 422


async def test_nobody_can_unregister_someone_elses_phone(api, db, make_user):
    owner = await make_user(UserRole.technician)
    other = await make_user(UserRole.technician)
    db.add(PushToken(token=TOKEN_B, user_id=owner.id))
    await db.flush()

    async with api("technician", user_id=other.id) as client:
        r = await client.request("DELETE", "/users/me/push-token", json={"token": TOKEN_B})
    assert r.status_code == 204

    still = (await db.execute(select(PushToken).where(PushToken.token == TOKEN_B))).scalar_one()
    assert still.user_id == owner.id


# ── what goes to Expo ────────────────────────────────────────────────

def test_an_alarm_rings_at_high_priority_on_its_own_channel():
    [payload] = push.build_payloads([TOKEN_A], "Alarm · Green Valley", "Cow down",
                                    {"channel": "alarm"}, "alarm")
    assert payload["to"] == TOKEN_A
    assert payload["priority"] == "high"
    assert payload["channelId"] == "alarms"
    assert payload["sound"] == "default"


def test_an_office_alert_uses_the_quieter_channel():
    [payload] = push.build_payloads([TOKEN_A], "Office Alert", "Route change", {}, "office_alert")
    assert payload["channelId"] == "office-alerts"


def test_a_malformed_token_is_never_sent():
    payloads = push.build_payloads([TOKEN_A, "garbage", ""], "t", "b", {}, "alarm")
    assert [p["to"] for p in payloads] == [TOKEN_A]


def test_a_long_message_is_trimmed_for_the_lock_screen():
    [payload] = push.build_payloads([TOKEN_A], "t", "x" * 500, {}, "alarm")
    assert len(payload["body"]) <= 180


def test_a_phone_that_no_longer_exists_is_pruned():
    sent = [{"to": TOKEN_A}, {"to": TOKEN_B}]
    tickets = [
        {"status": "ok", "id": "1"},
        {"status": "error", "details": {"error": "DeviceNotRegistered"}},
    ]
    assert push.dead_tokens(sent, tickets) == [TOKEN_B]


def test_a_transient_error_does_not_prune():
    """Rate limits and outages are Expo's problem, not proof the phone is gone."""
    sent = [{"to": TOKEN_A}]
    tickets = [{"status": "error", "details": {"error": "MessageRateExceeded"}}]
    assert push.dead_tokens(sent, tickets) == []
