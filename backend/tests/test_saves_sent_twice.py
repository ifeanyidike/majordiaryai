"""Offline mode: a save sent again with its one-time code happens once.

Josh's Part A platform tests: "Pending records sync automatically when the
connection returns, with no duplicates" and "Losing signal mid-save leaves no
half-saved record". The phone resends an outcome with the same code until it
gets an answer, so the server must record it once however often it arrives.
"""

import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, HeatCheck, IdempotencyKey, Insemination, UserRole,
)

TODAY = local_today()


async def _open_cow(db, farm, tech):
    farm.assigned_technician_id = tech.id
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag=f"I-{uuid.uuid4().hex[:6]}",
              status=CowStatus.open, lactation_number=2)
    db.add(cow)
    await db.flush()
    return cow


def _heat(cow, seen=True):
    return {"cow_id": str(cow.id), "check_date": TODAY.isoformat(),
            "heat_detected": seen, "bleeding_event": False}


async def _count(db, model, cow):
    return await db.scalar(select(func.count()).select_from(model).where(model.cow_id == cow.id))


async def test_the_same_save_sent_twice_is_recorded_once(db, api, farm, make_user):
    tech = await make_user(UserRole.technician)
    cow = await _open_cow(db, farm, tech)
    code = {"Idempotency-Key": str(uuid.uuid4())}
    async with api("technician", user_id=tech.id) as client:
        first = await client.post("/checks/heat", json=_heat(cow), headers=code)
        again = await client.post("/checks/heat", json=_heat(cow), headers=code)
    assert first.status_code == 201, first.text
    assert again.status_code == 200 and again.json() == {"already_recorded": True}
    assert again.headers["Idempotent-Replayed"] == "true"
    assert await _count(db, HeatCheck, cow) == 1


async def test_an_insemination_resent_after_a_lost_answer_is_not_doubled(db, api, farm, make_user):
    tech = await make_user(UserRole.technician)
    cow = await _open_cow(db, farm, tech)
    body = {"cow_id": str(cow.id), "date": f"{TODAY.isoformat()}T09:00:00",
            "bull_name": "Bull 7", "semen_type": "sexed"}
    code = {"Idempotency-Key": str(uuid.uuid4())}
    async with api("technician", user_id=tech.id) as client:
        assert (await client.post("/inseminations/", json=body, headers=code)).status_code == 201
        assert (await client.post("/inseminations/", json=body, headers=code)).status_code == 200
    assert await _count(db, Insemination, cow) == 1


async def test_a_refused_save_can_be_sent_again_with_its_code(db, api, farm, make_user):
    """A refusal saves nothing, so the code is not used up."""
    tech = await make_user(UserRole.technician)
    cow = await _open_cow(db, farm, tech)
    await db.commit()   # the setup stays; the refused request's work does not
    code = {"Idempotency-Key": str(uuid.uuid4())}
    seen = _heat(cow)
    async with api("technician", user_id=tech.id) as client:
        refused = await client.post("/checks/heat", json=_heat(cow, seen=False), headers=code)
        assert refused.status_code == 422
        # In production each request has its own session, closed without a
        # commit after a refusal; the tests share one, so undo it by hand.
        await db.rollback()
        ok = await client.post("/checks/heat", json=seen, headers=code)
    assert ok.status_code == 201, ok.text
    assert await db.scalar(select(func.count()).select_from(IdempotencyKey).where(
        IdempotencyKey.key == code["Idempotency-Key"])) == 1


async def test_without_a_code_nothing_changes(db, api, farm, make_user):
    tech = await make_user(UserRole.technician)
    cow = await _open_cow(db, farm, tech)
    async with api("technician", user_id=tech.id) as client:
        await client.post("/checks/heat", json=_heat(cow))
        cow.status = CowStatus.open
        await db.flush()
        await client.post("/checks/heat", json=_heat(cow))
    assert await _count(db, HeatCheck, cow) == 2


async def test_two_people_may_use_the_same_code(db, api, farm, make_user):
    one = await make_user(UserRole.technician)
    two = await make_user(UserRole.admin)
    cow = await _open_cow(db, farm, one)
    code = {"Idempotency-Key": "same-code"}
    async with api("technician", user_id=one.id) as client:
        assert (await client.post("/checks/heat", json=_heat(cow), headers=code)).status_code == 201
    cow.status = CowStatus.open
    await db.flush()
    async with api("admin", user_id=two.id) as client:
        assert (await client.post("/checks/heat", json=_heat(cow), headers=code)).status_code == 201
    assert await _count(db, HeatCheck, cow) == 2


# ── the day it happened, not the day it reached the server ───────────

from datetime import datetime, timezone   # noqa: E402

from app.core import timeutils   # noqa: E402
from app.models.models import CullRecord   # noqa: E402


def _at(days_ago: int) -> dict:
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {"Recorded-At": when.isoformat()}


async def _cull(db, api, farm, tech, headers):
    cow = await _open_cow(db, farm, tech)
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/cows/{cow.id}/cull", json={"reason": "lame"},
                              headers={"Idempotency-Key": str(uuid.uuid4()), **headers})
    assert r.status_code == 200, r.text
    return await db.scalar(select(CullRecord.cull_date).where(CullRecord.cow_id == cow.id))


async def test_a_cull_sent_a_day_late_keeps_the_day_it_happened(db, api, farm, make_user):
    tech = await make_user(UserRole.technician)
    culled_on = await _cull(db, api, farm, tech, _at(1))
    assert culled_on == TODAY - timedelta(days=1)
    # Only for that request: the server's own today afterwards.
    assert timeutils.local_today() == TODAY


async def test_a_move_to_the_dry_pen_sent_late_keeps_its_day(db, api, farm, make_user):
    tech = await make_user(UserRole.technician)
    farm.assigned_technician_id = tech.id
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag=f"D-{uuid.uuid4().hex[:6]}",
              status=CowStatus.dry, lactation_number=2)
    db.add(cow)
    await db.flush()
    async with api("technician", user_id=tech.id) as client:
        r = await client.post(f"/cows/{cow.id}/dry-off-confirm",
                              headers={"Idempotency-Key": str(uuid.uuid4()), **_at(2)})
    assert r.status_code == 200, r.text
    await db.refresh(cow)
    assert cow.dry_off_confirmed_date == TODAY - timedelta(days=2)


async def test_a_wrong_phone_clock_is_not_believed(db, api, farm, make_user):
    tech = await make_user(UserRole.technician)
    future = await _cull(db, api, farm, tech, _at(-2))     # two days ahead
    ancient = await _cull(db, api, farm, tech, _at(45))    # older than a month
    garbled = await _cull(db, api, farm, tech, {"Recorded-At": "yesterday"})
    assert future == ancient == garbled == TODAY


async def test_two_copies_at_the_same_moment_make_one_record(engine, make_user, db):
    """The second waits on the first; once the first commits, it is a repeat.
    Two real sessions, as two requests would have."""
    import asyncio
    from types import SimpleNamespace
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from app.core.idempotency import AlreadyRecorded, once

    tech = await make_user(UserRole.technician)
    await db.commit()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    request = SimpleNamespace(method="POST", headers={"Idempotency-Key": "same-moment"},
                              url=SimpleNamespace(path="/checks/heat"))
    user = {"id": tech.id}

    async with maker() as first, maker() as second:
        gen_a = once(request, first, user)
        await gen_a.__anext__()                      # first holds the code, uncommitted
        gen_b = once(request, second, user)
        waiting = asyncio.ensure_future(gen_b.__anext__())
        await asyncio.sleep(0.3)
        assert not waiting.done()                    # the second waits on the first
        await first.commit()                         # the first's save goes in
        try:
            await waiting
            outcome = "ran twice"
        except AlreadyRecorded:
            outcome = "recognised"
        assert outcome == "recognised"
        await second.rollback()
    async with maker() as check:
        n = await check.scalar(select(func.count()).select_from(IdempotencyKey).where(
            IdempotencyKey.key == "same-moment"))
        assert n == 1
        await check.execute(IdempotencyKey.__table__.delete().where(IdempotencyKey.key == "same-moment"))
        await check.commit()
