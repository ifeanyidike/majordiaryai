"""The timed status transitions themselves.

test_scheduler.py proves the loop runs; it monkeypatches the sweep out, so
none of these rules was ever executed by a test. They are the ones that move a
cow between reports with nobody touching the app:

    pregnant + dry_date reached       -> dry   (+ "change pen" email)
    fresh + day 70, next Mon/Tue/Sat  -> open
    calf + day 60                     -> heifer
    heifer + day 395                  -> open  (breeding-eligible)

A silent break here does not raise anything. It just means a cow is never
dried off, or never becomes breedable, and no report ever mentions her again.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.timeutils import local_today
from app.models.models import Cow, CowStatus, Notification
from app.services import status_engine
from app.services.status_engine import (
    CALF_TO_HEIFER_DAY, FRESH_TO_OPEN_DAY, HEIFER_BREEDING_DAY,
    run_lifecycle_transitions,
)

TODAY = local_today()


async def _cow(db, farm, **kw) -> Cow:
    kw.setdefault("lactation_number", 1)
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id,
              ear_tag=f"S-{uuid.uuid4().hex[:8]}", **kw)
    db.add(cow)
    await db.flush()
    return cow


async def _sweep(db, today=None) -> int:
    return await run_lifecycle_transitions(db, farm_ids=None, today=today or TODAY)


# ── pregnant -> dry at the dry date ──────────────────────────────────

@pytest.mark.parametrize("offset,expected", [
    (-1, CowStatus.dry),        # dry date passed
    (0, CowStatus.dry),         # dry date is today
    (1, CowStatus.pregnant),    # not yet
])
async def test_dry_off_happens_on_the_dry_date(db, farm, offset, expected):
    cow = await _cow(db, farm, status=CowStatus.pregnant,
                     dry_date=TODAY + timedelta(days=offset))
    await _sweep(db)
    await db.refresh(cow)
    assert cow.status == expected


async def test_dry_off_notifies_the_farm_to_change_pen(db, farm):
    """The spec's day-223 action is a pen change, and the farmer is told by
    email. If the transition stops firing the email stops with it."""
    cow = await _cow(db, farm, status=CowStatus.pregnant,
                     dry_date=TODAY - timedelta(days=1))
    await _sweep(db)

    notes = (await db.execute(
        select(Notification).where(Notification.cow_id == cow.id)
    )).scalars().all()
    assert [n.type for n in notes] == ["dry_off"]
    assert "change pen" in notes[0].message.lower()


async def test_a_pregnant_cow_with_no_dry_date_is_left_alone(db, farm):
    cow = await _cow(db, farm, status=CowStatus.pregnant, dry_date=None)
    assert await _sweep(db) == 0
    await db.refresh(cow)
    assert cow.status == CowStatus.pregnant


async def test_dry_off_is_not_repeated_on_the_next_sweep(db, farm):
    """The sweep runs every six hours and on every report request, so a
    transition that re-fired would email the farmer four times a day."""
    await _cow(db, farm, status=CowStatus.pregnant,
               dry_date=TODAY - timedelta(days=1))
    assert await _sweep(db) == 1
    assert await _sweep(db) == 0


# ── fresh -> open at day 70, pushed to a breeding day ────────────────

async def test_fresh_to_open_lands_on_a_breeding_day(db, farm):
    """Day 70 is the earliest; the spec only starts cows on Mon/Tue/Sat, so
    the entry date is pushed forward to the next one. Sweeping on raw day 70
    would put a cow into Open on a day nobody breeds."""
    calved = TODAY - timedelta(days=FRESH_TO_OPEN_DAY)
    entry = status_engine.adjust_to_breeding_day(
        calved + timedelta(days=FRESH_TO_OPEN_DAY)
    )
    cow = await _cow(db, farm, status=CowStatus.fresh, last_calving_date=calved)

    await _sweep(db)
    await db.refresh(cow)
    assert cow.status == (CowStatus.open if entry <= TODAY else CowStatus.fresh)


@pytest.mark.parametrize("weekday", range(7))
async def test_fresh_to_open_from_every_weekday_of_calving(db, farm, weekday):
    """All seven cases. The push-forward is arithmetic on the calving date, so
    a cow calving on any given weekday must still reach Open — none of them may
    stall in `fresh` forever."""
    # A calving date whose day-70 mark falls on the target weekday.
    calved = TODAY - timedelta(days=400)
    calved -= timedelta(days=((calved + timedelta(days=FRESH_TO_OPEN_DAY)).weekday() - weekday) % 7)
    cow = await _cow(db, farm, status=CowStatus.fresh, last_calving_date=calved)

    await _sweep(db)
    await db.refresh(cow)
    assert cow.status == CowStatus.open

    entry = status_engine.adjust_to_breeding_day(calved + timedelta(days=FRESH_TO_OPEN_DAY))
    assert entry.weekday() in status_engine.BREEDING_WEEKDAYS


async def test_a_fresh_cow_before_day_70_stays_fresh(db, farm):
    cow = await _cow(db, farm, status=CowStatus.fresh,
                     last_calving_date=TODAY - timedelta(days=FRESH_TO_OPEN_DAY - 10))
    await _sweep(db)
    await db.refresh(cow)
    assert cow.status == CowStatus.fresh


# ── calf -> heifer -> open ───────────────────────────────────────────

@pytest.mark.parametrize("age,expected", [
    (CALF_TO_HEIFER_DAY - 1, CowStatus.calf),
    (CALF_TO_HEIFER_DAY, CowStatus.heifer),
    (HEIFER_BREEDING_DAY - 1, CowStatus.heifer),
    (HEIFER_BREEDING_DAY, CowStatus.open),
])
async def test_a_calf_ages_into_a_heifer_and_then_into_the_breeding_herd(
    db, farm, age, expected,
):
    cow = await _cow(db, farm, status=CowStatus.calf, lactation_number=0,
                     date_of_birth=TODAY - timedelta(days=age))
    await _sweep(db)
    await db.refresh(cow)
    assert cow.status == expected


async def test_a_very_old_calf_reaches_breeding_age_in_one_sweep(db, farm):
    """Imported history can produce a 'calf' that is years old. The sweep falls
    through calf -> heifer -> open in a single pass rather than needing two
    runs, or she sits a whole cycle in the wrong status."""
    cow = await _cow(db, farm, status=CowStatus.calf, lactation_number=0,
                     date_of_birth=TODAY - timedelta(days=HEIFER_BREEDING_DAY + 100))
    await _sweep(db)
    await db.refresh(cow)
    assert cow.status == CowStatus.open
    # Master Structure: month-13 heifers go straight to the Insemination
    # Program, not to the Open report's protocol choice.
    assert cow.current_program == "Insemination"


async def test_an_animal_with_no_birth_date_is_never_aged(db, farm):
    cow = await _cow(db, farm, status=CowStatus.calf, lactation_number=0,
                     date_of_birth=None)
    assert await _sweep(db) == 0
    await db.refresh(cow)
    assert cow.status == CowStatus.calf


# ── scoping and isolation ────────────────────────────────────────────

async def test_the_sweep_can_be_limited_to_one_farm(db, farm):
    """Report endpoints sweep only the caller's farms. Scoping that wrongly
    would advance statuses on herds the caller cannot even see."""
    from app.models.models import Farm

    other = Farm(id=uuid.uuid4(), name=f"Other {uuid.uuid4().hex[:6]}",
                 owner_name="O", herd_size=0)
    db.add(other)
    await db.flush()

    mine = await _cow(db, farm, status=CowStatus.pregnant,
                      dry_date=TODAY - timedelta(days=1))
    theirs = await _cow(db, other, status=CowStatus.pregnant,
                        dry_date=TODAY - timedelta(days=1))

    changed = await run_lifecycle_transitions(db, farm_ids=[farm.id], today=TODAY)
    await db.refresh(mine)
    await db.refresh(theirs)

    assert changed == 1
    assert mine.status == CowStatus.dry
    assert theirs.status == CowStatus.pregnant


@pytest.mark.parametrize("status", [
    CowStatus.open, CowStatus.needling, CowStatus.inseminated,
    CowStatus.dry, CowStatus.cull, CowStatus.sold, CowStatus.dead,
])
async def test_statuses_the_sweep_must_never_touch(db, farm, status):
    """Only pregnant/fresh/calf/heifer are time-driven. A widened query here
    would, for instance, resurrect a sold cow on a stale date field."""
    cow = await _cow(db, farm, status=status,
                     dry_date=TODAY - timedelta(days=400),
                     last_calving_date=TODAY - timedelta(days=400),
                     date_of_birth=TODAY - timedelta(days=1000))
    await _sweep(db)
    await db.refresh(cow)
    assert cow.status == status
