"""Josh's test herd, Oct 26: the tag on her ear, and heifers never dry off.

* The TAG is the number the app shows and searches; the herd software's ID is
  kept as herd_id. The ID is what is unique: imported herds reuse tags, so the
  database allows a shared tag, and the app still refuses one when an animal
  is ADDED in it (migration 0022).
* A heifer -- never calved, however old -- has no dry date. Correcting her
  lactation number gives her one, or takes it away.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import local_today
from app.models.models import Cow, CowStatus
from app.services.status_engine import DRY_OFF_DAY

TODAY = local_today()


def _cow(farm, **kw) -> Cow:
    kw.setdefault("lactation_number", 2)
    kw.setdefault("status", CowStatus.open)
    return Cow(id=uuid.uuid4(), farm_id=farm.id, **kw)


async def test_an_imported_herd_may_share_a_tag_but_not_an_id(db, farm):
    db.add_all([_cow(farm, ear_tag="9066", herd_id="90066"),
                _cow(farm, ear_tag="9066", herd_id="90067", lactation_number=0)])
    await db.flush()

    db.add(_cow(farm, ear_tag="9999", herd_id="90066"))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_a_cow_added_in_the_app_cannot_take_a_tag_already_on_the_farm(db, farm, api):
    db.add(_cow(farm, ear_tag="9066", herd_id="90066"))
    await db.flush()
    async with api("admin") as client:
        r = await client.post("/cows/", json={"farm_id": str(farm.id), "ear_tag": "9066"})
        assert r.status_code == 409, r.text
        assert "9066" in r.json()["detail"]

        r = await client.post("/cows/", json={"farm_id": str(farm.id), "ear_tag": "9067"})
        assert r.status_code == 201, r.text
        assert r.json()["herd_id"] is None  # only an import gives one


async def test_a_newborn_cannot_take_a_tag_already_on_the_farm(db, farm, api):
    db.add(_cow(farm, ear_tag="C-7"))
    mother = _cow(farm, ear_tag="M-1", status=CowStatus.dry)
    db.add(mother)
    await db.flush()
    async with api("admin") as client:
        r = await client.post("/calving/", json={
            "cow_id": str(mother.id), "calving_date": TODAY.isoformat(),
            "live_birth": True, "still_birth": False,
            "calf_sex": "female", "calf_ear_tag": "C-7",
        })
    assert r.status_code == 409, r.text
    await db.refresh(mother)
    assert mother.status == CowStatus.dry  # nothing was recorded


async def test_the_herd_id_comes_back_with_the_cow(db, farm, api):
    cow = _cow(farm, ear_tag="9068", herd_id="77001")
    db.add(cow)
    await db.flush()
    async with api("admin") as client:
        r = await client.get(f"/cows/{cow.id}")
    assert r.status_code == 200, r.text
    assert (r.json()["ear_tag"], r.json()["herd_id"]) == ("9068", "77001")


async def test_correcting_her_lactation_gives_or_takes_her_dry_date(db, farm, api):
    bred = TODAY - timedelta(days=100)
    cow = _cow(farm, ear_tag="H-1", status=CowStatus.pregnant, lactation_number=0,
               last_insemination_date=bred, due_date=bred + timedelta(days=283))
    db.add(cow)
    await db.flush()
    async with api("admin") as client:
        r = await client.patch(f"/cows/{cow.id}", json={"lactation_number": 1})
        assert r.status_code == 200, r.text
        assert r.json()["dry_date"] == (bred + timedelta(days=DRY_OFF_DAY)).isoformat()

        r = await client.patch(f"/cows/{cow.id}", json={"lactation_number": 0})
        assert r.json()["dry_date"] is None
