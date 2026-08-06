"""Farm visit scheduling — the technician's General To-Do list (layer 1).

Spec (Technician To-Do List System):
  · the list shows the farms a technician visits TODAY, not every farm he owns
  · schedules are rotations, not daily: "some farms are on a 5-day rotation,
    others 6-day, so the list will vary day to day"
  · a farm can be reassigned for the day to a Relief Technician or another
    technician, and then shows on his list as "Reassigned — Skip"

Two pieces of data drive that: the rotation on `farms` (interval + anchor) says
WHEN a farm is due, and a `farm_visit_assignments` row says WHO covers a
specific date when it isn't the standing technician.
"""

from datetime import date
from enum import Enum
from typing import Optional
from uuid import UUID

from app.models.models import Farm, FarmVisitAssignment


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


def is_visit_due(farm: Farm, on: date) -> bool:
    """True when `on` lands on this farm's rotation.

    A farm with no anchor date has never had a rotation configured; treat it as
    due every day rather than invisible — a missing schedule must not silently
    hide real work from the technician.
    """
    interval = farm.visit_interval_days or 0
    if interval <= 0 or farm.visit_anchor_date is None:
        return True
    delta = (on - farm.visit_anchor_date).days
    if delta < 0:
        return False  # rotation hasn't started yet
    return delta % interval == 0


def next_visit_date(farm: Farm, on: date) -> Optional[date]:
    """The first rotation date strictly after `on` (None when unscheduled)."""
    from datetime import timedelta

    interval = farm.visit_interval_days or 0
    if interval <= 0 or farm.visit_anchor_date is None:
        return None
    if farm.visit_anchor_date > on:
        return farm.visit_anchor_date
    elapsed = (on - farm.visit_anchor_date).days
    return farm.visit_anchor_date + timedelta(days=((elapsed // interval) + 1) * interval)


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
