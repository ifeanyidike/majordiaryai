from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.models.models import Notification, NotificationRead
from app.schemas.notifications import NotificationOut
from app.services.access import check_farm_access, scope_to_farms
from typing import List, Optional
import uuid

router = APIRouter()


def _out(notification: Notification, read: bool) -> dict:
    d = {c.key: getattr(notification, c.key)
         for c in notification.__table__.columns}
    d["read"] = read
    return d


@router.get("/", response_model=List[NotificationOut])
async def list_notifications(
    farm_id: Optional[uuid.UUID] = None,
    unread_only: bool = False,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A farm's notifications, with `read` answered for THIS caller.

    A notification belongs to a farm and several people can see it, so read
    state hangs off the reader. It used to be one column on the shared row:
    the admin skimming the list marked a dry-off read for the farm manager who
    had never seen it, and their unread badge cleared on its own.
    """
    # Left join so an unread notification (no receipt row) still comes back.
    receipt = NotificationRead.notification_id
    stmt = (
        select(Notification, receipt)
        .outerjoin(
            NotificationRead,
            (NotificationRead.notification_id == Notification.id)
            & (NotificationRead.user_id == current_user["id"]),
        )
        .order_by(Notification.created_at.desc())
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Notification.farm_id)
    if unread_only:
        stmt = stmt.where(receipt.is_(None))
    stmt = stmt.limit(max(1, min(limit, 500)))
    rows = (await db.execute(stmt)).all()
    return [_out(n, read_id is not None) for n, read_id in rows]


@router.get("/undelivered", response_model=List[NotificationOut])
async def undelivered(
    limit: int = 100,
    current_user: dict = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Notifications whose email never reached the farmer.

    Delivery used to fail silently, so "the farmer was never told" was
    invisible. This is the query that surfaces it — a rejected send, a farm
    with no address on file, or sending switched off entirely.
    """
    stmt = (
        select(Notification)
        .where(Notification.email_status.in_(("failed", "no_email", "disabled")))
        .order_by(Notification.created_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    rows = (await db.execute(stmt)).scalars().all()
    # This list is about delivery, not about who has read what.
    return [_out(n, False) for n in rows]


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record that THIS user has read it. Idempotent."""
    notification = await db.get(Notification, notification_id)
    if not notification or not await check_farm_access(db, current_user, notification.farm_id):
        raise HTTPException(status_code=404, detail="Notification not found")

    # Tapping twice, or two devices at once, must not 500 on the primary key.
    await db.execute(
        pg_insert(NotificationRead)
        .values(notification_id=notification_id, user_id=current_user["id"])
        .on_conflict_do_nothing()
    )
    await db.commit()
    return _out(notification, True)
