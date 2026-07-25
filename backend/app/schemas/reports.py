from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import date


class HerdSummary(BaseModel):
    farm_id: UUID
    farm_name: str
    total: int
    calf: int
    heifer: int
    fresh: int
    open: int
    needling: int
    inseminated: int
    pregnant: int
    dry: int
    cull: int
    sold: int
    dead: int
    # KPIs
    pregnancy_rate: Optional[float] = None
    conception_rate: Optional[float] = None
    services_per_conception: Optional[float] = None
    upcoming_calvings_30d: int = 0


class CowReportRow(BaseModel):
    id: UUID
    ear_tag: str
    farm_id: UUID
    farm_name: str
    breed: Optional[str] = None
    status: str
    health_status: Optional[str] = None
    recheck_due_date: Optional[date] = None
    lactation_number: int
    last_calving_date: Optional[date] = None
    last_insemination_date: Optional[date] = None
    due_date: Optional[date] = None
    dry_date: Optional[date] = None
    days_since_insemination: Optional[int] = None
    days_until_due: Optional[int] = None
    days_overdue: Optional[int] = None


class PregnancyCheckDueReport(BaseModel):
    # Next default pregnancy-check day: the next 1st or 14th of the month.
    next_check_date: date
    cows: List[CowReportRow] = []


class TimedBreedingRow(BaseModel):
    cow_id: UUID
    ear_tag: str
    farm_id: UUID
    farm_name: Optional[str] = None
    enrollment_id: UUID
    protocol: str
    protocol_day: int
    scheduled_date: date
    days_overdue: int = 0


class DailyTaskSummary(BaseModel):
    needling_due: int
    heat_checks_due: int
    vaccinations_due: int
