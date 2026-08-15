"""The bulk import, driven end-to-end through the endpoint.

test_import_parsing.py covers the pure helpers. These are the two behaviours
that only exist once a real database and a real transaction are involved, and
both were the most destructive bugs of their rounds:

  * a bad row must not take the good rows with it (SAVEPOINT isolation), and
    the counters must describe what actually persisted;
  * a blank cell must not overwrite stored data on a re-import.

Neither had a test. The first is the begin_nested/autoflush interplay most
likely to break silently under a SQLAlchemy upgrade; the second is the one a
client hits on their second upload.
"""

import io
import uuid

from sqlalchemy import select

from app.models.models import Cow, CowStatus


HEADER = "ear_tag,status,breed,last_calving_date,lactation_number"


def _csv(*rows: str) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


def _upload(content: bytes, name="herd.csv"):
    return {"file": (name, io.BytesIO(content), "text/csv")}


async def _tags(db, farm) -> dict:
    rows = (await db.execute(select(Cow).where(Cow.farm_id == farm.id))).scalars().all()
    return {c.ear_tag: c for c in rows}


# ── SAVEPOINT isolation ──────────────────────────────────────────────

async def test_one_bad_row_does_not_discard_the_good_ones(db, api, farm):
    """A plain rollback() here discarded every row staged so far while the
    counters kept counting: a 200-row file with one bad row at 150 persisted
    only the rows after it and still reported ~199 successes."""
    rows = [f"A{i},open,Holstein,,1" for i in range(1, 6)]
    rows.insert(3, "BAD,not-a-real-status,Holstein,,1")   # row 5 of the file
    rows += [f"B{i},open,Holstein,,1" for i in range(1, 6)]

    async with api(role="admin") as client:
        resp = await client.post(
            f"/imports/cows?farm_id={farm.id}", files=_upload(_csv(*rows)),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["created"] == 10
    assert body["skipped"] == 1
    assert body["total_rows"] == 11
    assert [e["ear_tag"] for e in body["errors"]] == ["BAD"]

    stored = await _tags(db, farm)
    # Every good row survived — the ones BEFORE the failure especially.
    assert {f"A{i}" for i in range(1, 6)} <= set(stored)
    assert {f"B{i}" for i in range(1, 6)} <= set(stored)
    assert "BAD" not in stored


async def test_counters_match_what_actually_persisted(db, api, farm):
    """The counters are what the user is shown; they must not be able to
    disagree with the database."""
    rows = ["C1,open,,,1", "C2,nonsense-status,,,1", "C3,open,,,1", ",open,,,1"]

    async with api(role="admin") as client:
        resp = await client.post(
            f"/imports/cows?farm_id={farm.id}", files=_upload(_csv(*rows)),
        )
    body = resp.json()
    stored = await _tags(db, farm)

    assert body["created"] == len(stored)
    assert body["created"] + body["skipped"] == body["total_rows"]


async def test_a_failed_row_leaves_no_partial_cow_behind(db, api, farm):
    """The SAVEPOINT must unwind the row's own writes, not just skip the rest
    of them."""
    async with api(role="admin") as client:
        resp = await client.post(
            f"/imports/cows?farm_id={farm.id}",
            files=_upload(_csv("D1,open,,,1", "D2,,,garbage-date,1")),
        )
    assert resp.json()["skipped"] == 1
    stored = await _tags(db, farm)
    assert "D2" not in stored
    assert "D1" in stored


# ── Blank cells on re-import ─────────────────────────────────────────

async def test_a_blank_status_cell_does_not_downgrade_a_pregnant_cow(db, api, farm):
    """The update path setattr'd every parsed field, and a blank status parses
    to `open`. So re-uploading a sheet with the status column left empty wrote
    `open` over `pregnant` for the whole herd — silently, reported as a
    successful update."""
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="E1",
              status=CowStatus.pregnant, lactation_number=3, breed="Holstein")
    db.add(cow)
    await db.flush()

    async with api(role="admin") as client:
        resp = await client.post(
            f"/imports/cows?farm_id={farm.id}",
            files=_upload(_csv("E1,,Jersey,,3")),   # status left blank
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 1

    await db.refresh(cow)
    assert cow.status == CowStatus.pregnant, "blank cell downgraded her to open"
    assert cow.breed == "Jersey", "a cell that WAS filled in must still apply"


async def test_a_blank_date_cell_does_not_erase_a_stored_date(db, api, farm):
    """last_calving_date drives days-in-milk, the post-calving shot and the
    fresh->open sweep. A blank cell wrote NULL over it."""
    from datetime import date

    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="E2",
              status=CowStatus.fresh, lactation_number=2,
              last_calving_date=date(2026, 1, 15))
    db.add(cow)
    await db.flush()

    async with api(role="admin") as client:
        await client.post(
            f"/imports/cows?farm_id={farm.id}",
            files=_upload(_csv("E2,fresh,Holstein,,2")),   # date left blank
        )

    await db.refresh(cow)
    assert cow.last_calving_date == date(2026, 1, 15)


async def test_a_blank_status_still_means_open_for_a_NEW_cow(db, api, farm):
    """Skipping blanks on update must not break create: a new cow with no
    status is open, which is what the template's own example row relies on."""
    async with api(role="admin") as client:
        resp = await client.post(
            f"/imports/cows?farm_id={farm.id}", files=_upload(_csv("E3,,Holstein,,0")),
        )
    assert resp.json()["created"] == 1
    stored = await _tags(db, farm)
    assert stored["E3"].status == CowStatus.open


async def test_a_filled_status_cell_still_updates(db, api, farm):
    """The fix must not make the status column read-only on re-import."""
    cow = Cow(id=uuid.uuid4(), farm_id=farm.id, ear_tag="E4",
              status=CowStatus.open, lactation_number=1)
    db.add(cow)
    await db.flush()

    async with api(role="admin") as client:
        await client.post(
            f"/imports/cows?farm_id={farm.id}", files=_upload(_csv("E4,dry,,,1")),
        )

    await db.refresh(cow)
    assert cow.status == CowStatus.dry
