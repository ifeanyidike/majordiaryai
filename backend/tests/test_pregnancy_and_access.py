"""Pregnancy outcomes, the dates they set, and who gets to see a farm.

Three things the suite never covered:

  * the +283 due date and +223 dry-off, which every calving and dry-off report
    is built from and which nothing asserted;
  * the infection/cysts matrix, where "infection" and "cysts" pull in opposite
    directions and the branch order decides the cow's status;
  * the relief technician's access grant, which is the one place a normal user
    can widen their own farm access.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, Farm, FarmVisitAssignment, PregnancyResult, User, UserRole,
)
from app.services import status_engine
from app.services.access import RELIEF_ACCESS_GRACE_DAYS, get_allowed_farm_ids

TODAY = local_today()


# ── The two dates a confirmed pregnancy sets ─────────────────────────

async def test_confirming_a_pregnancy_sets_the_spec_dates(db, make_cow):
    """Spec: due at +283 days, dry off at +223. Nothing asserted either, and
    every calving-due and dry-off report is computed from them."""
    bred_on = TODAY - timedelta(days=40)
    cow = await make_cow(cow_status=CowStatus.inseminated,
                         last_insemination_date=bred_on)

    await status_engine.on_pregnancy_confirmed(cow, bred_on, db)
    await db.flush()

    assert cow.status == CowStatus.pregnant
    assert cow.due_date == bred_on + timedelta(days=283)
    assert cow.dry_date == bred_on + timedelta(days=223)
    # Dry-off comes 60 days before she calves — the spec's dry period.
    assert (cow.due_date - cow.dry_date).days == 60


def test_the_date_helpers_are_the_single_source_of_those_offsets():
    d = TODAY
    assert status_engine.compute_due_date(d) == d + timedelta(days=status_engine.GESTATION_DAYS)
    assert status_engine.compute_dry_date(d) == d + timedelta(days=status_engine.DRY_OFF_DAY)
    assert status_engine.GESTATION_DAYS == 283
    assert status_engine.DRY_OFF_DAY == 223


async def test_dates_are_computed_from_the_breeding_not_from_today(db, make_cow):
    """Recording a check late must not push the whole gestation out. Using
    today's date here would have moved the due date by however many days the
    vet's paperwork lagged."""
    bred_on = TODAY - timedelta(days=45)
    cow = await make_cow(cow_status=CowStatus.inseminated,
                         last_insemination_date=bred_on)

    await status_engine.on_pregnancy_confirmed(cow, bred_on, db)
    await db.flush()

    assert cow.due_date == bred_on + timedelta(days=283)
    assert cow.due_date != TODAY + timedelta(days=283)


# ── Infection / cysts matrix ─────────────────────────────────────────
# "Infection" does not by itself change the outcome; "cysts" sends her back to
# Open regardless of the result. The branch ORDER is what makes that true, so
# the combination of the two is worth pinning down.

@pytest.mark.parametrize("result,infection,cysts,expected", [
    (PregnancyResult.pregnant,     False, False, CowStatus.pregnant),
    (PregnancyResult.pregnant,     True,  False, CowStatus.pregnant),   # infection alone
    (PregnancyResult.pregnant,     False, True,  CowStatus.open),       # cysts override
    (PregnancyResult.pregnant,     True,  True,  CowStatus.open),
    (PregnancyResult.not_pregnant, False, False, CowStatus.open),
    (PregnancyResult.not_pregnant, True,  False, CowStatus.open),
    (PregnancyResult.not_pregnant, False, True,  CowStatus.open),
    (PregnancyResult.not_pregnant, True,  True,  CowStatus.open),
])
async def test_infection_and_cysts_matrix(db, api, farm, result, infection, cysts, expected):
    bred_on = TODAY - timedelta(days=35)
    cow = Cow(farm_id=farm.id, ear_tag=f"M-{result.value}-{infection}-{cysts}",
              status=CowStatus.inseminated, lactation_number=1,
              last_insemination_date=bred_on)
    db.add(cow)
    await db.flush()

    async with api(role="admin") as client:
        ai = await client.post("/inseminations/", json={
            "cow_id": str(cow.id), "date": f"{bred_on}T09:00:00",
            "bull_name": "Mogul", "semen_type": "conventional",
        })
        assert ai.status_code == 201, ai.text
        # The insemination reset her AI date to `bred_on`; check 35 days later.
        resp = await client.post("/checks/pregnancy", json={
            "cow_id": str(cow.id),
            "insemination_id": ai.json()["id"],
            "check_date": str(TODAY),
            "result": result.value,
            "has_infection": infection,
            "has_cysts": cysts,
        })
    assert resp.status_code == 201, resp.text

    await db.refresh(cow)
    assert cow.status == expected


async def test_a_pregnancy_check_must_state_a_result(db, api, farm):
    """A null result with no cysts wrote a check row and moved the cow
    nowhere: she stayed inseminated, stayed on the Pregnancy Check report
    forever, and the record made it look like the vet had been."""
    bred_on = TODAY - timedelta(days=35)
    cow = Cow(farm_id=farm.id, ear_tag="M-noresult", status=CowStatus.inseminated,
              lactation_number=1, last_insemination_date=bred_on)
    db.add(cow)
    await db.flush()

    async with api(role="admin") as client:
        ai = await client.post("/inseminations/", json={
            "cow_id": str(cow.id), "date": f"{bred_on}T09:00:00",
            "bull_name": "Mogul", "semen_type": "conventional",
        })
        resp = await client.post("/checks/pregnancy", json={
            "cow_id": str(cow.id),
            "insemination_id": ai.json()["id"],
            "check_date": str(TODAY),
        })
    assert resp.status_code == 422, resp.text


# ── The relief technician's access grant ─────────────────────────────

async def _relief_setup(db, visit_offset_days):
    """A farm owned by one technician, with a visit assigned to another."""
    # users.id mirrors the Supabase auth id, so there is no server default.
    owner = User(id=uuid.uuid4(), name="Owner Tech",
                 email=f"o{visit_offset_days}@t.test", role=UserRole.technician)
    relief = User(id=uuid.uuid4(), name="Relief Tech",
                  email=f"r{visit_offset_days}@t.test", role=UserRole.technician)
    db.add_all([owner, relief])
    await db.flush()

    farm = Farm(name=f"Relief Farm {visit_offset_days}", owner_name="O",
                herd_size=1, assigned_technician_id=owner.id,
                visit_weekdays=[0, 1, 2, 3, 4, 5])
    db.add(farm)
    await db.flush()

    db.add(FarmVisitAssignment(
        farm_id=farm.id,
        visit_date=TODAY + timedelta(days=visit_offset_days),
        assigned_technician_id=relief.id,
    ))
    await db.flush()
    return farm, relief


async def _may_access(db, user, farm) -> bool:
    allowed = await get_allowed_farm_ids(db, {"id": user.id, "role": "technician",
                                              "farm_id": None})
    if allowed is None:
        return True
    ids = (await db.execute(select(Farm.id).where(Farm.id.in_(allowed)))).scalars().all()
    return farm.id in ids


@pytest.mark.parametrize("offset,granted", [
    (0, True),                                  # the day of the visit
    (-1, True),                                 # yesterday's visit
    (-RELIEF_ACCESS_GRACE_DAYS, True),          # last day of the grace period
    (-RELIEF_ACCESS_GRACE_DAYS - 1, False),     # expired — this is revocation
    (1, False),                                 # tomorrow's visit, not yet
    (400, False),                               # the self-grant that used to work
])
async def test_relief_access_is_bounded_on_both_sides(db, offset, granted):
    """The grant was unbounded forward and could never expire, so a visit
    dated far ahead handed the creator indefinite access to any farm — and a
    relief technician kept a farm they covered once, forever."""
    farm, relief = await _relief_setup(db, offset)
    assert await _may_access(db, relief, farm) is granted


async def test_the_standing_technician_keeps_access_regardless(db):
    """Bounding the relief grant must not touch the farm's own technician."""
    farm, _relief = await _relief_setup(db, 0)
    owner = await db.get(User, farm.assigned_technician_id)
    assert await _may_access(db, owner, farm) is True


# ── Calving must not reverse a cull ──────────────────────────────────

async def test_calving_is_refused_on_a_culled_cow(db, api, farm):
    """The gate blocked calf/sold/dead but not cull, and on_calving wrote
    `fresh` directly — past the guard that forbids cull -> fresh. Recording a
    calving therefore un-culled the cow, with nothing recording that the cull
    decision had been reversed."""
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="CULLED-1",
              status=CowStatus.cull, lactation_number=2)
    db.add(cow)
    await db.flush()

    async with api(role="admin") as client:
        resp = await client.post("/calving/", json={
            "cow_id": str(cow.id), "calving_date": str(TODAY),
            "live_birth": True, "still_birth": False, "calf_sex": "female",
        })
    assert resp.status_code == 409, resp.text

    await db.refresh(cow)
    assert cow.status == CowStatus.cull, "a calving silently un-culled her"


@pytest.mark.parametrize("status", [CowStatus.sold, CowStatus.dead, CowStatus.calf])
async def test_calving_is_refused_on_the_other_terminal_statuses(db, api, farm, status):
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag=f"T-{status.value}",
              status=status, lactation_number=1)
    db.add(cow)
    await db.flush()

    async with api(role="admin") as client:
        resp = await client.post("/calving/", json={
            "cow_id": str(cow.id), "calving_date": str(TODAY),
            "live_birth": True, "still_birth": False, "calf_sex": "female",
        })
    assert resp.status_code == 409, resp.text


@pytest.mark.parametrize("status", [
    CowStatus.pregnant, CowStatus.dry, CowStatus.inseminated,
    CowStatus.heifer, CowStatus.open, CowStatus.needling,
])
async def test_calving_is_still_accepted_from_every_live_status(db, api, farm, status):
    """Calving is event-triggered: a cow can calve while the system believes
    she is only inseminated (nobody recorded the check) or still a heifer.
    Tightening the terminal gate must not re-break that."""
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag=f"L-{status.value}",
              status=status, lactation_number=1)
    db.add(cow)
    await db.flush()

    async with api(role="admin") as client:
        resp = await client.post("/calving/", json={
            "cow_id": str(cow.id), "calving_date": str(TODAY),
            "live_birth": True, "still_birth": False, "calf_sex": "male",
        })
    assert resp.status_code == 201, resp.text

    await db.refresh(cow)
    assert cow.status == CowStatus.fresh
