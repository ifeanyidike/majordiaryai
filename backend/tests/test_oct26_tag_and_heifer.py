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
from app.services.status_engine import BREEDING_WEEKDAYS, DRY_OFF_DAY

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


# ── what rehearsing Josh's checklist on his live farm found (Oct 26) ──

def _first_day(pred):
    d = TODAY
    while not pred(d):
        d += timedelta(days=1)
    return d


async def test_a_protocol_only_starts_on_a_monday_tuesday_or_saturday(db, farm, api):
    """Josh: "protocol can only start on a Monday, Tuesday or Saturday". The
    app only warned, and the API took any day."""
    off = _first_day(lambda d: d.weekday() not in BREEDING_WEEKDAYS)
    on = _first_day(lambda d: d.weekday() in BREEDING_WEEKDAYS)
    cow = _cow(farm, ear_tag="P-1")
    db.add(cow)
    await db.flush()
    async with api("admin") as client:
        r = await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch", "start_date": off.isoformat()})
        assert r.status_code == 422, r.text
        assert "Monday, Tuesday or Saturday" in r.json()["detail"]
        r = await client.post("/needling/enroll", json={
            "cow_id": str(cow.id), "protocol": "ovsynch", "start_date": on.isoformat()})
        assert r.status_code == 201, r.text


async def test_the_automatic_restart_after_bleeding_starts_on_a_breeding_day(db, farm):
    from sqlalchemy import select

    from app.models.models import NeedlingEnrollment
    from app.services import status_engine

    cow = _cow(farm, ear_tag="P-2", status=CowStatus.needling)
    db.add(cow)
    await db.flush()
    await status_engine.on_bleeding_before_insemination(cow, db)
    enrollment = (await db.execute(select(NeedlingEnrollment).where(
        NeedlingEnrollment.cow_id == cow.id))).scalar_one()
    assert enrollment.start_date == status_engine.adjust_to_breeding_day(TODAY)
    assert enrollment.start_date.weekday() in BREEDING_WEEKDAYS


async def test_the_cull_list_says_when_and_why(db, farm, api):
    """It printed the sold/dead fields, so every culled cow read "Exited —"
    and the reason the technician typed was nowhere."""
    cow = _cow(farm, ear_tag="C-1")
    db.add(cow)
    await db.flush()
    async with api("admin") as client:
        r = await client.post(f"/cows/{cow.id}/cull", json={
            "cull_date": TODAY.isoformat(), "reason": "Low yield", "notes": None})
        assert r.status_code == 200, r.text
        wl = (await client.get("/reports/worklist", params={"farm_id": str(farm.id)})).json()
    culls = next(rp for rp in wl["farms"][0]["reports"] if rp["type"] == "cull")["cows"]
    assert [c["detail"] for c in culls] == [f"Culled {TODAY.isoformat()} · Low yield"]


@pytest.mark.parametrize("kind", ["sold", "dead"])
async def test_sold_and_dead_take_the_date_given(db, farm, api, kind):
    """A field called `date` annotated `date` resolved to its own default, so
    only None was accepted: sending any date was a 422."""
    cow = _cow(farm, ear_tag=f"X-{kind}", status=CowStatus.cull)
    db.add(cow)
    await db.flush()
    when = TODAY - timedelta(days=2)
    async with api("admin") as client:
        r = await client.post(f"/cows/{cow.id}/mark-{kind}",
                              json={"date": when.isoformat(), "reason": "test"})
    assert r.status_code == 200, r.text
    await db.refresh(cow)
    assert cow.exit_date == when
