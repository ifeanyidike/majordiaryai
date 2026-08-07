from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime


def _clean_weekdays(days: Optional[List[int]]) -> Optional[List[int]]:
    """Sorted, de-duplicated, 0-6 only. Mirrors the DB check constraint so a
    bad value is a 422 rather than an IntegrityError."""
    if days is None:
        return None
    cleaned = sorted(set(days))
    if not cleaned:
        raise ValueError("visit_weekdays cannot be empty — a farm needs at least one visit day")
    if any(d < 0 or d > 6 for d in cleaned):
        raise ValueError("visit_weekdays must be 0-6 (Mon=0 … Sun=6)")
    return cleaned


class FarmCreate(BaseModel):
    name: str
    owner_name: str
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    herd_size: int = Field(default=0, ge=0)  # owner-reported figure
    assigned_technician_id: Optional[UUID] = None
    # Visit weekdays, Mon=0 … Sun=6. "5-day farm" = Mon–Fri [0-4];
    # "6-day farm" = Mon–Sat [0-5], which is the default.
    visit_weekdays: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    notes: Optional[str] = None

    _check_weekdays = field_validator("visit_weekdays")(_clean_weekdays)


class FarmUpdate(BaseModel):
    name: Optional[str] = None
    owner_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    herd_size: Optional[int] = Field(default=None, ge=0)
    assigned_technician_id: Optional[UUID] = None
    visit_weekdays: Optional[List[int]] = None
    notes: Optional[str] = None

    _check_weekdays = field_validator("visit_weekdays")(_clean_weekdays)


class FarmOut(BaseModel):
    id: UUID
    name: str
    owner_name: str
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    herd_size: int  # owner-reported — distinct from the computed cow_count below
    assigned_technician_id: Optional[UUID] = None
    # resolved name of the assigned technician (for display; id above is the FK)
    assigned_technician_name: Optional[str] = None
    visit_weekdays: List[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    # Human label for the schedule, e.g. "Mon–Sat"
    visit_schedule_label: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    # computed counts (populated via JOIN)
    cow_count: Optional[int] = None
    pregnant_count: Optional[int] = None
    open_count: Optional[int] = None


class VisitAssignmentBody(BaseModel):
    """Hand one day's visit to a relief/another technician (or nobody)."""
    visit_date: date
    # None = the visit is explicitly skipped that day.
    assigned_technician_id: Optional[UUID] = None
    reason: Optional[str] = None


class VisitAssignmentOut(BaseModel):
    id: UUID
    farm_id: UUID
    visit_date: date
    assigned_technician_id: Optional[UUID] = None
    assigned_technician_name: Optional[str] = None
    reason: Optional[str] = None
