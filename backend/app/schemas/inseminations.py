from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import date, datetime
from app.models.models import SemenType


class InseminationCreate(BaseModel):
    # attempt_number is computed server-side; extra="forbid" rejects any
    # client-supplied value with a 422.
    model_config = ConfigDict(extra="forbid")

    cow_id: UUID
    date: datetime  # date AND time of the insemination
    bull_name: Optional[str] = None
    dose_id: Optional[str] = None
    semen_type: Optional[SemenType] = None
    notes: Optional[str] = None


class InseminationOut(BaseModel):
    id: UUID
    cow_id: UUID
    date: date
    inseminated_at: Optional[datetime] = None
    bull_name: Optional[str] = None
    dose_id: Optional[str] = None
    semen_type: Optional[str] = None
    technician_id: Optional[UUID] = None
    attempt_number: int
    notes: Optional[str] = None
    created_at: datetime
