from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from app.core.timeutils import local_today
from app.models.models import CalfSex, CowStatus, HealthStatus
from app.schemas.calving import CalvingOut
from app.schemas.checks import HeatCheckOut, PregnancyCheckOut
from app.schemas.inseminations import InseminationOut
from app.schemas.needling import NeedlingRecordOut
from app.schemas.vaccinations import VaccinationOut


class CowCreate(BaseModel):
    # Either will do, but not neither. Some farms tag, some name, some do
    # both; the database enforces the same rule (ck_cows_has_an_identifier),
    # and catching it here turns a 500 on the constraint into a 422 that says
    # what is wrong.
    ear_tag: Optional[str] = None
    name: Optional[str] = None
    farm_id: UUID
    breed: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: CalfSex = CalfSex.female
    lactation_number: int = Field(default=0, ge=0)
    notes: Optional[str] = None

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_future(cls, v):
        if v is not None and v > local_today():
            raise ValueError("date_of_birth cannot be in the future")
        return v

    @model_validator(mode="after")
    def needs_an_identifier(self):
        if not (self.ear_tag or "").strip() and not (self.name or "").strip():
            raise ValueError("Give the cow an ear tag, a name, or both")
        return self


class CowUpdate(BaseModel):
    name: Optional[str] = None
    breed: Optional[str] = None
    date_of_birth: Optional[date] = None
    lactation_number: Optional[int] = Field(default=None, ge=0)
    status: Optional[CowStatus] = None
    notes: Optional[str] = None

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_future(cls, v):
        if v is not None and v > local_today():
            raise ValueError("date_of_birth cannot be in the future")
        return v


class CowOut(BaseModel):
    # Derived: in milk from calving until dry-off (Master Structure, Milk Cycle)
    is_milking: bool = False
    id: UUID
    ear_tag: Optional[str] = None
    name: Optional[str] = None
    # "Bluebell (CA 124 578 1042)", or just the tag when she has no name —
    # computed once here so every screen names her the same way.
    label: Optional[str] = None
    farm_id: UUID
    breed: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: str
    lactation_number: int
    status: str
    health_status: Optional[str] = None
    recheck_due_date: Optional[date] = None
    current_program: Optional[str] = None
    last_calving_date: Optional[date] = None
    last_insemination_date: Optional[date] = None
    last_insemination_id: Optional[UUID] = None
    due_date: Optional[date] = None
    dry_date: Optional[date] = None
    exit_date: Optional[date] = None
    exit_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    farm_name: Optional[str] = None


class CowHealthBody(BaseModel):
    health_status: HealthStatus
    notes: Optional[str] = None


class CullBody(BaseModel):
    cull_date: Optional[date] = None  # defaults to today (farm-local)
    reason: Optional[str] = None
    notes: Optional[str] = None


class ExitBody(BaseModel):
    """Body for marking a cow sold or dead."""
    date: Optional[date] = None  # defaults to today (farm-local)
    reason: Optional[str] = None


class CowHistory(BaseModel):
    inseminations: List[InseminationOut] = []
    heat_checks: List[HeatCheckOut] = []
    pregnancy_checks: List[PregnancyCheckOut] = []
    calvings: List[CalvingOut] = []
    needling_records: List[NeedlingRecordOut] = []
    vaccinations: List[VaccinationOut] = []
