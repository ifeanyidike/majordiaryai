from typing import List, Optional

from pydantic import BaseModel


class ConceptionKpi(BaseModel):
    inseminated: int
    pregnant: int
    rate: Optional[float] = None


class MonthCount(BaseModel):
    month: str          # YYYY-MM
    pregnant: int


class SemenKpi(BaseModel):
    semen_type: str
    inseminated: int
    pregnant: int
    rate: Optional[float] = None


class FarmKpis(BaseModel):
    """One farm's KPI page (services/farm_kpis.py)."""
    conception: ConceptionKpi
    pregnancies_by_month: List[MonthCount]
    by_semen: List[SemenKpi]
