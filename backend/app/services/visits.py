"""Farm visit scheduling — the technician's General To-Do list (layer 1).

Spec (Technician To-Do List System):
  · the list shows the farms a technician visits TODAY, not every farm he owns
  · a farm can be reassigned for the day to a Relief Technician or another
    technician, and then shows on his list as "Reassigned — Skip"

The schedule is a set of WEEKDAYS, not an every-N-days cycle. Per the client:
a "5-day farm" is Monday–Friday and a "6-day farm" is Monday–Saturday, with
Sunday off in both — which is also why the breeding-day rule (Mon/Tue/Sat)
never lands on a day nobody works.

Two pieces of data drive the list: `farms.visit_weekdays` says WHEN a farm is
due, and a `farm_visit_assignments` row says WHO covers a specific date when it
isn't the standing technician.
"""

from datetime import date, timedelta
from enum import Enum
from typing import Optional, Sequence
from uuid import UUID

from app.models.models import Farm, FarmVisitAssignment

# Mon=0 … Sun=6, matching date.weekday().
WEEKDAYS_MON_FRI = (0, 1, 2, 3, 4)      # "5-day" farm
WEEKDAYS_MON_SAT = (0, 1, 2, 3, 4, 5)   # "6-day" farm — the default
DEFAULT_VISIT_WEEKDAYS = WEEKDAYS_MON_SAT

WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def weekdays_for(days_per_week: int) -> Sequence[int]:
    """The weekday set for a "5-day"/"6-day" farm, as the client describes them."""
    return WEEKDAYS_MON_FRI if days_per_week == 5 else WEEKDAYS_MON_SAT


def describe_weekdays(weekdays: Optional[Sequence[int]]) -> str:
    """Short human label, e.g. "Mon–Fri" or "Mon, Thu"."""
    days = sorted(set(weekdays or DEFAULT_VISIT_WEEKDAYS))
    if not days:
        return "No scheduled visits"
    # Contiguous runs read better as a range than a list.
    if days == list(range(days[0], days[-1] + 1)) and len(days) > 2:
        return f"{WEEKDAY_NAMES[days[0]]}–{WEEKDAY_NAMES[days[-1]]}"
    return ", ".join(WEEKDAY_NAMES[d] for d in days)


class VisitStatus(str, Enum):
    """Why a farm is (or isn't) on this technician's list today."""

    visit_today = "visit_today"
    # Standing assignment is this technician, but the day was handed to someone
    # else. Shown on his list, flagged to skip — per the spec's example table.
    reassigned = "reassigned"
    # Picked up from another technician's rotation for this date.
    covering = "covering"
    # Explicitly cancelled for the day (assignment row with no technician).
    skipped = "skipped"
    # In scope but off-rotation today. Route screens hide these; herd views
    # (vet/farm/admin dashboards, farm profiles) still need the farm's data —
    # a cow's pregnancy status doesn't blink out because no visit is due.
    not_due = "not_due"


def visit_weekdays(farm: Farm) -> Sequence[int]:
    """This farm's visit weekdays, falling back to the Mon–Sat default.

    An unconfigured farm defaults to the busiest schedule rather than to
    "never" — a missing setting must not silently hide real work.
    """
    return farm.visit_weekdays or DEFAULT_VISIT_WEEKDAYS


def is_visit_due(farm: Farm, on: date) -> bool:
    """True when `on` is one of this farm's visit weekdays."""
    return on.weekday() in set(visit_weekdays(farm))


def next_visit_date(farm: Farm, on: date) -> Optional[date]:
    """The next visit date strictly after `on` (None when nothing is scheduled)."""
    days = set(visit_weekdays(farm))
    if not days:
        return None
    for ahead in range(1, 8):
        candidate = on + timedelta(days=ahead)
        if candidate.weekday() in days:
            return candidate
    return None


def resolve_visit(
    farm: Farm,
    override: Optional[FarmVisitAssignment],
    viewer_id: UUID,
    is_admin: bool = False,
) -> Optional[VisitStatus]:
    """How this farm appears on `viewer_id`'s list for the override's date.

    Returns None when the farm doesn't belong on their list at all. Assumes the
    date is already known to be due (`is_visit_due`).
    """
    standing = farm.assigned_technician_id
    covered_by = override.assigned_technician_id if override is not None else standing

    if is_admin:
        if override is not None and override.assigned_technician_id is None:
            return VisitStatus.skipped
        return VisitStatus.visit_today

    if covered_by == viewer_id:
        # Covering someone else's farm only when it isn't already yours.
        return VisitStatus.covering if standing != viewer_id else VisitStatus.visit_today

    if standing == viewer_id:
        # Yours on paper, someone else's today — surface it, flagged to skip, so
        # the technician knows why a familiar farm is missing rather than
        # wondering. `skipped` when nobody picked it up.
        return VisitStatus.skipped if covered_by is None else VisitStatus.reassigned

    return None


def visit_label(status: VisitStatus, covering_name: Optional[str]) -> str:
    """The Schedule column text from the spec's example table."""
    if status is VisitStatus.visit_today:
        return "Visit Today"
    if status is VisitStatus.covering:
        return "Covering Today"
    if status is VisitStatus.reassigned:
        return f"Reassigned to {covering_name or 'another technician'} — Skip"
    if status is VisitStatus.not_due:
        return "Not on today's rotation"
    return "Visit skipped today"
