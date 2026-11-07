from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from uuid import UUID
from datetime import date, datetime
from app.models.models import CalfSex


class CalvingCreate(BaseModel):
    cow_id: UUID
    calving_date: date
    # Required, no default (Josh, Oct 4): every report question is answered,
    # never assumed. Every app build already sends it.
    live_birth: bool
    still_birth: bool
    calf_sex: Optional[CalfSex] = None
    calf_ear_tag: Optional[str] = None
    # The ID that tells her from an animal on the same tag, and the answer to
    # "Are you sure?" when that tag is already on the farm.
    calf_herd_id: Optional[str] = None
    allow_shared_tag: bool = False
    # For male calves (no herd record) — sale/outcome details
    calf_sale_info: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("calf_herd_id")
    @classmethod
    def blank_id_is_no_id(cls, v):
        return (v or "").strip() or None

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
