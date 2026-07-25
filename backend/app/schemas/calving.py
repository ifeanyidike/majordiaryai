from pydantic import BaseModel, model_validator
from typing import Optional
from uuid import UUID
from datetime import date, datetime
from app.models.models import CalfSex


class CalvingCreate(BaseModel):
    cow_id: UUID
    calving_date: date
    live_birth: bool = True
    still_birth: bool = False
    calf_sex: Optional[CalfSex] = None
    calf_ear_tag: Optional[str] = None
    # For male calves (no herd record) — sale/outcome details
    calf_sale_info: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def live_still_mutually_exclusive(self):
        if self.live_birth == self.still_birth:
            raise ValueError("Exactly one of live_birth / still_birth must be true")
        return self


class CalvingOut(BaseModel):
    id: UUID
    cow_id: UUID
    calving_date: date
    live_birth: bool
    still_birth: bool
    calf_sex: Optional[str] = None
    calf_ear_tag: Optional[str] = None
    calf_sale_info: Optional[str] = None
    calf_id: Optional[UUID] = None
    technician_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
