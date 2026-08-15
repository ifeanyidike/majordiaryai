"""Spreadsheet parsing: what the importer refuses rather than guesses.

Every case here used to be a silent fallback. An unreadable date became None,
an unknown status became `open`, an unmatched farm name became whichever farm
the upload was started from — and the import reported the row as a success.
That is worse than refusing it: nobody goes looking for a problem the importer
said it did not have.

These drive the real parsing helpers, which are pure and need no database.
"""

from datetime import date

import pytest

from app.models.models import CowStatus
from app.routers.imports import (
    RowError, _extract_cow_fields, _parse_date, _parse_status, _resolve_row_farm,
    _supplied_fields,
)

import uuid

FARM_A = uuid.uuid4()
FARM_B = uuid.uuid4()


# ── Dates ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("2024-03-04", date(2024, 3, 4)),          # ISO always wins
    ("2024-03-04 08:30:00", date(2024, 3, 4)),
    ("2024-03-04T08:30:00", date(2024, 3, 4)),
    ("2024/03/04", date(2024, 3, 4)),
    ("4 Mar 2024", date(2024, 3, 4)),
    ("4 March 2024", date(2024, 3, 4)),
])
def test_unambiguous_date_spellings(text, expected):
    assert _parse_date(text, "last_calving_date") == expected


def test_slash_dates_are_read_month_first():
    """03/04/2024 is March 4th to a US herd and April 3rd to a European one.

    Day-first used to be tried first, so every unambiguous US date moved by
    months — and this column drives the +283 due date and the +223 dry-off, so
    a misread calving date puts a cow on the wrong worklist for a gestation.
    The client is a US operation, so month-first wins the tie.
    """
    assert _parse_date("03/04/2024", "last_calving_date") == date(2024, 3, 4)
    assert _parse_date("03-04-2024", "last_calving_date") == date(2024, 3, 4)


def test_a_date_that_can_only_be_day_first_still_parses():
    """13 is not a month, so there is no ambiguity left to resolve."""
    assert _parse_date("13/04/2024", "last_calving_date") == date(2024, 4, 13)


def test_blank_dates_are_simply_absent():
    for blank in (None, "", "   "):
        assert _parse_date(blank, "due_date") is None


@pytest.mark.parametrize("text", ["not a date", "2024-13-45", "03/2024", "??"])
def test_unreadable_dates_are_refused_not_dropped(text):
    """Returning None here erased the basis for the due date, the dry-off date
    and the post-calving report, and still counted the row a success."""
    with pytest.raises(RowError) as exc:
        _parse_date(text, "last_calving_date")
    assert "last_calving_date" in str(exc.value)


def test_real_date_objects_pass_through():
    """openpyxl hands back real dates for properly typed cells."""
    assert _parse_date(date(2024, 3, 4), "due_date") == date(2024, 3, 4)


# ── Statuses ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("open", CowStatus.open),
    ("Pregnant", CowStatus.pregnant),
    ("IN CALF", CowStatus.pregnant),
    ("bred", CowStatus.inseminated),
    ("Dried off", CowStatus.dry),
    ("milking", CowStatus.fresh),
    ("on program", CowStatus.needling),
    ("culled", CowStatus.cull),
    ("deceased", CowStatus.dead),
])
def test_statuses_a_herd_manager_actually_types(text, expected):
    assert _parse_status(text) is expected


def test_blank_status_means_open_for_a_new_cow_only():
    """This default is for CREATE. On an update a blank cell must leave the
    stored status alone — otherwise re-importing a sheet with the column empty
    downgrades the whole herd to open. `_supplied_fields` is what enforces
    that, and test_import_upload.py holds it to it end-to-end."""
    assert _parse_status("") is CowStatus.open
    assert _parse_status(None) is CowStatus.open
    assert "status" not in _supplied_fields({"status": ""})
    assert "status" in _supplied_fields({"status": "dry"})


@pytest.mark.parametrize("text", ["Pregnant 60d", "sold?", "gone", "n/a"])
def test_unrecognized_status_is_refused_not_defaulted(text):
    """Defaulting to `open` put sold animals and cows carrying a calf onto the
    technician's breeding list."""
    with pytest.raises(RowError) as exc:
        _parse_status(text)
    assert "status" in str(exc.value)


def test_a_bad_status_fails_the_whole_row_not_just_the_field():
    with pytest.raises(RowError):
        _extract_cow_fields({"ear_tag": "A1", "status": "who knows"})


# ── Per-row farm override ────────────────────────────────────────────

def _row_farm(value, by_name=None):
    return _resolve_row_farm(
        ["A1", value], 1, {FARM_A: object()}, by_name or {"green acres": FARM_A}, FARM_B,
    )


def test_blank_farm_cell_uses_the_farm_being_imported_into():
    assert _row_farm("") == FARM_B
    assert _row_farm(None) == FARM_B


def test_no_farm_column_at_all_uses_the_default():
    assert _resolve_row_farm(["A1"], None, {}, {}, FARM_B) == FARM_B


def test_a_matching_farm_name_wins():
    assert _row_farm("Green Acres") == FARM_A


def test_a_farm_id_the_caller_can_access_wins():
    assert _row_farm(str(FARM_A)) == FARM_A


@pytest.mark.parametrize("value", ["Greeen Acres", str(uuid.uuid4()), "Someone Else's Farm"])
def test_an_unmatched_farm_is_refused_not_filed_under_the_default(value):
    """Falling through to the default farm filed those cows onto a herd they
    do not belong to — reported as imported, and only discoverable by someone
    noticing extra ear tags."""
    with pytest.raises(RowError) as exc:
        _row_farm(value)
    assert "farm" in str(exc.value)
