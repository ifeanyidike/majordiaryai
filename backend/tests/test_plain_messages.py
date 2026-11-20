"""Error messages are shown in the app as they are, so they read as sentences."""

import uuid

from app.core.words import field_words, status_words
from app.models.models import CowStatus


async def test_a_missing_field_is_named_in_words(api):
    async with api("technician") as client:
        r = await client.post("/checks/heat", json={"cow_id": str(uuid.uuid4())})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str)
    assert "check date" in detail and "heat detected" in detail
    assert "_" not in detail and "loc" not in detail


def test_statuses_and_fields_in_words():
    assert status_words(CowStatus.dnb) == "marked Do Not Breed"
    assert status_words(CowStatus.needling) == "on a protocol"
    assert field_words(("body", "check_date")) == "check date"
    assert field_words(("body", "items", 2, "farm_id")) == "farm id"
