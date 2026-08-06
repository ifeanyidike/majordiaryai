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
    # Final-day injection, folded in per the same-day overlap rule
    treatment: Optional[str] = None
    needling_record_id: Optional[UUID] = None
    needling_completed: bool = False
    scheduled_date: date
    days_overdue: int = 0


class DailyTaskSummary(BaseModel):
    needling_due: int
    heat_checks_due: int
    vaccinations_due: int


# ── Worklist (the technician's three layers in one payload) ──────────

class WorklistCow(BaseModel):
    cow_id: UUID
    ear_tag: str
    farm_id: UUID
    status: str
    # The imperative instruction for today ("Action Required" in the spec).
    action: str
    detail: str
    lactation_number: int = 0
    days_in_milk: Optional[int] = None
    days_post_ai: Optional[int] = None
    last_insemination_id: Optional[UUID] = None
    last_insemination_date: Optional[date] = None
    last_calving_date: Optional[date] = None
    health_status: Optional[str] = None
    # Which inline form records the outcome; None when this caller may not.
    record_kind: Optional[str] = None
    treatment: Optional[str] = None
    protocol: Optional[str] = None
    protocol_day: Optional[int] = None
    needling_record_id: Optional[UUID] = None
    needling_completed: bool = False
    overdue: bool = False
    # Timed Breeding: shots the overlap rule hid that were never given.
    missed_shots: int = 0
    # Needling: pending injections beyond the one shown.
    also_pending: int = 0


class WorklistReport(BaseModel):
    type: str
    title: str
    icon: str
    status_key: str
    is_work_report: bool
    count: int
    subtitle: str
    can_record: bool
    cows: List[WorklistCow] = []


class WorklistFarm(BaseModel):
    farm_id: UUID
    farm_name: str
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    phone: Optional[str] = None
    # visit_today | covering | reassigned | skipped
    schedule: str
    schedule_label: str
    covering_technician: Optional[str] = None
    reassign_reason: Optional[str] = None
    visit_interval_days: int = 0
    next_visit_date: Optional[date] = None
    total_cows: int = 0
    reports: List[WorklistReport] = []


class Worklist(BaseModel):
    date: date
    farms: List[WorklistFarm] = []
