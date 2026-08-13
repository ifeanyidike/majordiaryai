from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

from app.models.models import SemenType


class BullCreate(BaseModel):
    name: str = Field(min_length=1)
    code: Optional[str] = None
    semen_type: Optional[SemenType] = None
    notes: Optional[str] = None


class BullUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    code: Optional[str] = None
    semen_type: Optional[SemenType] = None
    # false retires the bull: kept for history, hidden from the picker.
    active: Optional[bool] = None
    notes: Optional[str] = None


class BullOut(BaseModel):
    id: UUID
    farm_id: UUID
    name: str
    code: Optional[str] = None
    semen_type: Optional[SemenType] = None
    active: bool
    notes: Optional[str] = None
    created_at: datetime
