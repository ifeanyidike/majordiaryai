"""Findings from the outside review of the Sept 17 work, each driven through
the shipped path — the endpoint a person actually uses — rather than the
engine function underneath it. The calving gap below survived a test that
called `on_calving` directly: the function worked, and the app offered no way
to reach it.
"""

import pathlib
import re
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import local_today
from app.models.models import (
    Cow, CowStatus, EnrollmentStatus, Farm, Message, MessageChannel,
    NeedlingEnrollment, NeedlingRecord, Notification, ProtocolType, UserRole,
)
from app.services import status_engine
from app.services.notifications import is_test_address
from app.services.report_catalog import WorklistContext, build_reports

TODAY = local_today()


# ── 1. never email a stranger ────────────────────────────────────────

def test_reserved_domains_are_never_sent_to():
    for address in ("office@greenvalleydairy.example", "a@example.com",
                    "b@mail.example.org", "c@farm.test", "d@x.invalid"):
        assert is_test_address(address), address


def test_a_real_domain_is_not_mistaken_for_a_test_one():
    """sunrisefarms.ca is a real business's Microsoft 365 domain; it received
    six alerts about cows that were not theirs. The guard must not be the
    thing that hides a real address — it only refuses reserved ones."""
    for address in ("david@sunrisefarms.ca", "farmer@gmail.com", "x@example.co"):
        assert not is_test_address(address), address


def test_the_seed_contains_no_deliverable_address():
    """The seed has run against production, where farm addresses are live.
    Every address it writes must be on a reserved domain."""
    seed = (pathlib.Path(__file__).parent.parent / "scripts" / "seed.py").read_text()
    addresses = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", seed)
    assert addresses, "no addresses found — has the seed changed shape?"
    live = [a for a in addresses if not is_test_address(a)]
    assert not live, f"seed would email real domains: {live}"


# ── 2. an assumed calving can still be recorded ──────────────────────

async def _dry_cow_due_today(db, farm, **extra) -> Cow:
    ai = TODAY - timedelta(days=status_engine.GESTATION_DAYS)
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag=f"AC-{uuid.uuid4().hex[:6]}",
              status=CowStatus.dry, lactation_number=3,
              last_insemination_date=ai,
              due_date=status_engine.compute_due_date(ai),
              dry_date=status_engine.compute_dry_date(ai), **extra)
    db.add(cow)
    await db.flush()
    return cow


async def test_the_real_calving_can_be_recorded_after_the_sweep(db, farm, api, make_user):
    """Through POST /calving/, as the app does it. The sweep made her Fresh on
    her due date; the calving that follows must still count the lactation,
    correct the date, and create the calf."""
    tech = await make_user(UserRole.technician)
    farm.assigned_technician_id = tech.id
    cow = await _dry_cow_due_today(db, farm)

    await status_engine.run_lifecycle_transitions(db, farm_ids=[farm.id], today=TODAY)
    assert cow.status is CowStatus.fresh
    assert cow.calving_assumed is True
    assert cow.lactation_number == 3

    real = TODAY - timedelta(days=1)
    async with api("technician", user_id=tech.id) as client:
        r = await client.post("/calving/", json={
            "cow_id": str(cow.id), "calving_date": real.isoformat(),
            "live_birth": True, "still_birth": False, "calf_sex": "female",
        })
    assert r.status_code == 201, r.text

    await db.refresh(cow)
    assert cow.lactation_number == 4
    assert cow.last_calving_date == real
    assert cow.calving_assumed is False
    calves = (await db.execute(
        select(Cow).where(Cow.farm_id == farm.id, Cow.status == CowStatus.calf)
    )).scalars().all()
    assert len(calves) == 1, "the calf was never created"


def test_the_fresh_report_asks_for_the_calving_while_it_is_assumed():
    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="AC-R",
              status=CowStatus.fresh, lactation_number=3,
              last_calving_date=TODAY - timedelta(days=40), calving_assumed=True)
    ctx = WorklistContext(today=TODAY, role="technician", cows=[cow])
    rows = {r["type"]: r for r in build_reports(ctx)}["fresh"]["cows"]

    # No age window: it stays until recorded, because the error does not age out.
    assert len(rows) == 1
    assert rows[0]["record_kind"] == "calving"
    assert "record the calving" in rows[0]["action"].lower()


def test_a_farm_manager_is_not_offered_a_form_the_api_refuses():
    cow = Cow(id=uuid.uuid4(), farm_id=uuid.uuid4(), ear_tag="AC-F",
              status=CowStatus.fresh, lactation_number=3,
              last_calving_date=TODAY, calving_assumed=True)
    ctx = WorklistContext(today=TODAY, role="farm", cows=[cow])
    rows = {r["type"]: r for r in build_reports(ctx)}["fresh"]["cows"]
    assert rows[0]["record_kind"] is None


# ── 4. the note reaches the farmer ───────────────────────────────────

async def test_the_note_is_sent_to_the_farm(db, farm, api, make_user):
    tech = await make_user(UserRole.technician)
    farm.assigned_technician_id = tech.id
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="NOTE-1", name="Bluebell",
              status=CowStatus.needling, lactation_number=1)
    db.add(cow)
    await db.flush()
    enr = NeedlingEnrollment(id=uuid.uuid4(), cow_id=cow.id, protocol=ProtocolType.ovsynch,
                             start_date=TODAY, current_day=1, status=EnrollmentStatus.active)
    db.add(enr)
    await db.flush()
    record = NeedlingRecord(id=uuid.uuid4(), enrollment_id=enr.id, cow_id=cow.id,
                            protocol_day=9, scheduled_date=TODAY + timedelta(days=1),
                            treatment="2cc GnRH", self_administered=True)
    db.add(record)
    await db.flush()

    async with api("technician", user_id=tech.id) as client:
        r = await client.patch(f"/needling/records/{record.id}/note",
                               json={"note": "Bluebell: 2cc GnRH tomorrow morning."})
    assert r.status_code == 200, r.text

    sent = (await db.execute(select(Notification).where(
        Notification.cow_id == cow.id, Notification.type == "self_inject"
    ))).scalars().all()
    assert len(sent) == 1
    assert "2cc GnRH tomorrow morning" in sent[0].message


# ── 5. a new farm on a technician's route is announced ───────────────

async def test_creating_a_farm_with_a_technician_tells_him(db, api, make_user):
    tech = await make_user(UserRole.technician)
    admin = await make_user(UserRole.admin)

    async with api("admin", user_id=admin.id) as client:
        r = await client.post("/farms/", json={
            "name": f"New Farm {uuid.uuid4().hex[:4]}", "owner_name": "O",
            "assigned_technician_id": str(tech.id),
        })
    assert r.status_code == 201, r.text

    alerts = (await db.execute(select(Message).where(
        Message.recipient_id == tech.id,
        Message.channel == MessageChannel.office_alert,
    ))).scalars().all()
    assert len(alerts) == 1
    assert "added to your route" in alerts[0].body


# ── 6. a late shot is not announced as a future one ──────────────────

async def test_a_caught_up_shot_says_it_is_late(db, farm):
    farm.self_inject_needling = True
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="LATE-1",
              status=CowStatus.needling, lactation_number=1)
    db.add(cow)
    await db.flush()
    start = TODAY - timedelta(days=10)
    enr = NeedlingEnrollment(id=uuid.uuid4(), cow_id=cow.id, protocol=ProtocolType.ovsynch,
                             start_date=start, current_day=10, status=EnrollmentStatus.active)
    db.add(enr)
    await db.flush()
    db.add(NeedlingRecord(id=uuid.uuid4(), enrollment_id=enr.id, cow_id=cow.id,
                          protocol_day=9, scheduled_date=TODAY - timedelta(days=2),
                          treatment="2cc GnRH", self_administered=True))
    await db.flush()

    await status_engine.run_lifecycle_transitions(db, farm_ids=[farm.id], today=TODAY)

    sent = (await db.execute(select(Notification).where(
        Notification.cow_id == cow.id, Notification.type == "self_inject"
    ))).scalars().all()
    assert len(sent) == 1
    assert "was due" in sent[0].message
    assert "needs 2cc GnRH on" not in sent[0].message


async def test_an_assumed_calving_is_not_moved_on_to_open(db, farm):
    """Day 70 used to carry her to Open on the sweep's guessed date, which took
    "Record Calving" away for good."""
    from app.core.timeutils import local_today
    today = local_today()
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="AC-70",
              status=CowStatus.fresh, lactation_number=3,
              last_calving_date=today - timedelta(days=120), calving_assumed=True)
    confirmed = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="RC-70",
                    status=CowStatus.fresh, lactation_number=3,
                    last_calving_date=today - timedelta(days=120))
    db.add_all([cow, confirmed])
    await db.flush()

    await status_engine.run_lifecycle_transitions(db, farm_ids=[farm.id], today=today)

    assert cow.status is CowStatus.fresh, "moved on from a calving nobody recorded"
    # The control: a recorded calving still moves on as it always has.
    assert confirmed.status is CowStatus.open
