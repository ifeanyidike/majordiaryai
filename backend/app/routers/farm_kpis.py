"""GET /reports/farm-kpis: one farm's KPI page (services/farm_kpis.py)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.timeutils import local_today
from app.models.models import Cow, Insemination, PregnancyCheck
from app.schemas.farm_kpis import FarmKpis
from app.services import farm_kpis
from app.services.access import check_farm_access

router = APIRouter()


@router.get("/farm-kpis", response_model=FarmKpis)
async def farm_kpi_page(
    farm_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await check_farm_access(db, current_user, farm_id):
        raise HTTPException(status_code=404, detail="Farm not found")
    cows = select(Cow.id).where(Cow.farm_id == farm_id)
    breedings = (await db.execute(
        select(Insemination.id, Insemination.date, Insemination.semen_type)
        .where(Insemination.cow_id.in_(cows))
    )).all()
    checks = (await db.execute(
        select(PregnancyCheck.insemination_id, PregnancyCheck.check_date, PregnancyCheck.result)
        .where(PregnancyCheck.cow_id.in_(cows))
    )).all()
    val = lambda e: e.value if e is not None else None  # noqa: E731
    return farm_kpis.compute(
        [farm_kpis.Breeding(id=i, date=d, semen_type=val(s)) for i, d, s in breedings],
        [farm_kpis.Check(insemination_id=i, check_date=d, result=val(r)) for i, d, r in checks],
        local_today(),
    )
