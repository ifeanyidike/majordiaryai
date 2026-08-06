from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from app.models.models import ProtocolType


class NeedlingEnrollmentCreate(BaseModel):
    cow_id: UUID
    protocol: ProtocolType  # unknown protocol name → 422
    start_date: date


class NeedlingRecordOut(BaseModel):
    id: UUID
    protocol_day: int
    scheduled_date: date
    completed_date: Optional[date] = None
    treatment: str
    is_final: bool
    completed: bool
    bleeding_event: bool
    notes: Optional[str] = None


class NeedlingEnrollmentOut(BaseModel):
    id: UUID
    cow_id: UUID
    protocol: str
    start_date: date
    current_day: int
    status: str
    created_at: datetime
    records: List[NeedlingRecordOut] = []


class CompleteRecordBody(BaseModel):
    bleeding_event: bool = False
    notes: Optional[str] = None


class BleedingEventBody(BaseModel):
    """A bleeding event, recordable on any day — with or without a scheduled
    record to complete (spec: "bleeding events can be recorded on any day")."""
    notes: Optional[str] = None
