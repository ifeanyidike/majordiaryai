from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.auth import require_roles
from app.services.status_engine import run_lifecycle_transitions

router = APIRouter()


@router.post("/run-transitions")
async def run_transitions(
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Apply all timed lifecycle transitions across every farm (dry at day 223,
    fresh→open at day 70, calf→heifer at day 60, heifer→breeding-eligible)."""
    changed = await run_lifecycle_transitions(db, farm_ids=None)
    return {"transitions_applied": changed}
