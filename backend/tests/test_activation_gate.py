"""Signup is open, so a claimed role is a request until an admin grants it.

Anyone who can complete Supabase auth can POST /users/me and ask for
`technician`, `farm` or `vet`. Narrowing which role may be claimed does not
help: whichever one stays self-serve inherits the problem, and there is no role
a stranger should hold on a customer's herd system by virtue of finding the
sign-up screen.

What a self-registered technician actually reached, before this: the staff
directory and the whole vet directory with each vet's farm coverage — the
customer list. Herd data was already out of reach (farm access comes from
assignments they do not have), which is why this reads as a leak rather than a
breach, and why it survived three review rounds.
"""

import uuid

import pytest

from app.models.models import User, UserRole


async def _signup(api, *, role="technician", email=None):
    """Go through the real signup endpoint, as a new account would."""
    user_id = uuid.uuid4()
    email = email or f"{uuid.uuid4().hex[:8]}@new.example.com"
    # No users row yet: signup authenticates on the token alone.
    async with api(role=role, user_id=user_id, token_only_email=email) as client:
        # email is required by the schema but IGNORED — the endpoint uses the
        # verified token claim, so a client cannot register under someone
        # else's address.
        resp = await client.post("/users/me", json={
            "name": "New Person", "role": role, "email": "spoofed@elsewhere.example.com",
        })
    return user_id, resp


# ── What signup produces ─────────────────────────────────────────────

@pytest.mark.parametrize("role", ["technician", "farm", "vet"])
async def test_a_signed_up_account_starts_inactive(db, api, role):
    user_id, resp = await _signup(api, role=role)
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_active"] is False

    user = await db.get(User, user_id)
    assert user is not None and user.is_active is False


async def test_admin_still_cannot_be_claimed_at_signup(db, api):
    _, resp = await _signup(api, role="admin")
    assert resp.status_code == 403, resp.text


# ── What an inactive account can reach ───────────────────────────────

@pytest.mark.parametrize("path", [
    "/users/",       # the staff directory
    "/vets/",        # the customer list
    "/farms/",
    "/cows/",
    "/reports/worklist",
])
async def test_an_inactive_account_reaches_nothing(db, api, path):
    user_id = uuid.uuid4()
    db.add(User(id=user_id, name="Pending", email=f"{uuid.uuid4().hex[:8]}@p.test",
                role=UserRole.technician, is_active=False))
    await db.flush()

    async with api(role="technician", user_id=user_id, real_auth=True) as client:
        resp = await client.get(path)
    assert resp.status_code == 403, f"{path} answered {resp.status_code}"
    assert "approve" in resp.json()["detail"].lower()


async def test_an_inactive_account_can_still_read_its_own_profile(db, api):
    """GET /users/me is token-only on purpose: the app needs it to say "waiting
    for approval" rather than dropping the person into a system where every
    request fails with no explanation."""
    user_id = uuid.uuid4()
    db.add(User(id=user_id, name="Pending", email=f"{uuid.uuid4().hex[:8]}@p.test",
                role=UserRole.technician, is_active=False))
    await db.flush()

    async with api(role="technician", user_id=user_id, real_auth=True) as client:
        resp = await client.get("/users/me")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# ── Activation ───────────────────────────────────────────────────────

async def test_an_admin_activates_the_account_and_it_works(db, api):
    user_id = uuid.uuid4()
    db.add(User(id=user_id, name="Pending", email=f"{uuid.uuid4().hex[:8]}@p.test",
                role=UserRole.technician, is_active=False))
    await db.flush()

    async with api(role="admin") as client:
        resp = await client.patch(f"/users/{user_id}", json={"is_active": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is True

    async with api(role="technician", user_id=user_id, real_auth=True) as client:
        assert (await client.get("/farms/")).status_code == 200


async def test_only_an_admin_can_activate(db, api):
    user_id = uuid.uuid4()
    db.add(User(id=user_id, name="Pending", email=f"{uuid.uuid4().hex[:8]}@p.test",
                role=UserRole.technician, is_active=False))
    await db.flush()

    async with api(role="technician") as client:
        resp = await client.patch(f"/users/{user_id}", json={"is_active": True})
    assert resp.status_code == 403


async def test_an_admin_cannot_deactivate_themselves(db, api):
    """The last admin switching themselves off leaves nobody who can ever
    approve anyone again, including themselves."""
    admin_id = uuid.uuid4()
    db.add(User(id=admin_id, name="Boss", email=f"{uuid.uuid4().hex[:8]}@a.test",
                role=UserRole.admin))
    await db.flush()

    async with api(role="admin", user_id=admin_id, real_auth=True) as client:
        resp = await client.patch(f"/users/{admin_id}", json={"is_active": False})
    assert resp.status_code == 409, resp.text


async def test_existing_accounts_are_active_by_default(db, api):
    """The column defaults to true so the migration cannot lock out anyone who
    already had an account, and admin-created rows keep working."""
    user_id = uuid.uuid4()
    db.add(User(id=user_id, name="Existing", email=f"{uuid.uuid4().hex[:8]}@e.test",
                role=UserRole.technician))
    await db.flush()
    user = await db.get(User, user_id)
    assert user.is_active is True
