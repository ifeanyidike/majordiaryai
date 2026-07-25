from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.models import Notification
from app.schemas.notifications import NotificationOut
from app.services.access import check_farm_access, scope_to_farms
from typing import List, Optional
import uuid

router = APIRouter()


@router.get("/", response_model=List[NotificationOut])
async def list_notifications(
    farm_id: Optional[uuid.UUID] = None,
    unread_only: bool = False,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Notification).order_by(Notification.created_at.desc())
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Notification.farm_id)
    if unread_only:
        stmt = stmt.where(Notification.read == False)
    stmt = stmt.limit(max(1, min(limit, 500)))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notification = await db.get(Notification, notification_id)
    if not notification or not await check_farm_access(db, current_user, notification.farm_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read = True
    await db.commit()
    await db.refresh(notification)
    return notification
