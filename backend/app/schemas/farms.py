from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID
from datetime import date, datetime


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
    # Visit rotation: 5-day, 6-day, ... A visit falls on anchor + k*interval.
    visit_interval_days: int = Field(default=7, ge=1, le=365)
    visit_anchor_date: Optional[date] = None
    notes: Optional[str] = None


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
    visit_interval_days: Optional[int] = Field(default=None, ge=1, le=365)
    visit_anchor_date: Optional[date] = None
    notes: Optional[str] = None


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
    visit_interval_days: int = 7
    visit_anchor_date: Optional[date] = None
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
