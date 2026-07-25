from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import date, datetime


class VaccinationOut(BaseModel):
    id: UUID
    cow_id: UUID
    calving_record_id: Optional[UUID] = None
    scheduled_date: date
    completed_date: Optional[date] = None
    administered_at: Optional[datetime] = None
    vaccine_name: Optional[str] = None
    lot_number: Optional[str] = None
    technician_id: Optional[UUID] = None
    completed: bool
    notes: Optional[str] = None
    created_at: datetime


class VaccinationDueRow(BaseModel):
    id: UUID
    cow_id: UUID
    ear_tag: str
    farm_id: UUID
    farm_name: Optional[str] = None
    scheduled_date: date
    last_calving_date: Optional[date] = None
    days_post_calving: Optional[int] = None


class VaccinationCompleteBody(BaseModel):
    vaccine_name: str
    lot_number: Optional[str] = None
    administered_at: Optional[datetime] = None  # defaults to now (farm-local)
    notes: Optional[str] = None
