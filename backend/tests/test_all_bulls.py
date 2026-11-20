"""Offline mode: the phone keeps every farm's bull list.

The bull is required on an insemination and picked from the farm's list
(Josh, Oct 4), so an insemination recorded with no signal needs the list on
the phone. GET /bulls/ hands over every farm's at once.
"""

import uuid

from app.models.models import Bull, Farm, UserRole


async def _farm(db, tech=None):
    f = Farm(id=uuid.uuid4(), name=f"B {uuid.uuid4().hex[:4]}", owner_name="O", herd_size=0,
             assigned_technician_id=tech.id if tech else None)
    db.add(f)
    await db.flush()
    return f


async def test_every_active_bull_on_the_callers_farms(db, api, make_user):
    tech = await make_user(UserRole.technician)
    mine, other = await _farm(db, tech), await _farm(db)
    db.add_all([
        Bull(farm_id=mine.id, name="Atlas", active=True),
        Bull(farm_id=mine.id, name="Retired", active=False),
        Bull(farm_id=other.id, name="Not yours", active=True),
    ])
    await db.flush()
    async with api("technician", user_id=tech.id) as client:
        r = await client.get("/bulls/")
    assert r.status_code == 200, r.text
    assert [(b["farm_id"], b["name"]) for b in r.json()] == [(str(mine.id), "Atlas")]
