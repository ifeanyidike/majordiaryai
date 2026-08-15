from pydantic import BaseModel, ConfigDict, model_validator
from typing import Optional
from uuid import UUID
from datetime import date, datetime
from app.models.models import SemenType


class InseminationCreate(BaseModel):
    """The spec's insemination form: bull, semen type, dose ID, date and time.

    Bull and semen type were optional, so a breeding could be recorded against
    no sire and no straw type at all. That is the one record the whole herd's
    genetics and every sexed/conventional/beef split is read back from, and
    once the technician has moved on it cannot be reconstructed. Dose ID stays
    optional — it is not always printed on the straw.
    """

    # attempt_number is computed server-side; extra="forbid" rejects any
    # client-supplied value with a 422.
    model_config = ConfigDict(extra="forbid")

    cow_id: UUID
    date: datetime  # date AND time of the insemination
    bull_name: Optional[str] = None
    # Set when the technician picked from the farm's bull list; bull_name still
    # carries the text so a straw that is not on the list is still recordable.
    bull_id: Optional[UUID] = None
    dose_id: Optional[str] = None
    insemination_code: Optional[str] = None
    semen_type: SemenType
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _requires_a_sire(self) -> "InseminationCreate":
        if self.bull_id is None and not (self.bull_name or "").strip():
            raise ValueError("Record which bull was used (pick one, or type the name)")
        return self


class InseminationOut(BaseModel):
    id: UUID
    cow_id: UUID
    date: date
    inseminated_at: Optional[datetime] = None
    bull_name: Optional[str] = None
    bull_id: Optional[UUID] = None
    dose_id: Optional[str] = None
    insemination_code: Optional[str] = None
    semen_type: Optional[str] = None
    technician_id: Optional[UUID] = None
    attempt_number: int
    notes: Optional[str] = None
    created_at: datetime
