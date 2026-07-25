from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import date, datetime
from app.models.models import PregnancyResult


class HeatCheckCreate(BaseModel):
    # days_since_insemination is computed server-side from the cow's last
    # insemination — any client-supplied value is ignored.
    cow_id: UUID
    insemination_id: UUID
    check_date: date
    heat_detected: Optional[bool] = None
    bleeding_event: bool = False
    notes: Optional[str] = None


class HeatCheckOut(BaseModel):
    id: UUID
    cow_id: UUID
    insemination_id: UUID
    check_date: date
    days_since_insemination: int
    heat_detected: Optional[bool] = None
    bleeding_event: bool
    technician_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime


class PregnancyCheckCreate(BaseModel):
    cow_id: UUID
    insemination_id: UUID
    check_date: date
    result: Optional[PregnancyResult] = None
    has_infection: bool = False
    has_cysts: bool = False
    notes: Optional[str] = None


class PregnancyCheckOut(BaseModel):
    id: UUID
    cow_id: UUID
    insemination_id: UUID
    check_date: date
    vet_id: Optional[UUID] = None
    performed_by_id: Optional[UUID] = None
    result: Optional[str] = None
    has_infection: bool
    has_cysts: bool
    notes: Optional[str] = None
    created_at: datetime
