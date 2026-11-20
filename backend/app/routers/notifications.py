from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.core.timeutils import local_today
from app.models.models import Cow, Notification, NotificationRead
from app.schemas.notifications import NotificationAnswer, NotificationOut
from app.services import questions
from app.services.access import get_cow_scoped
from app.services.notifications import visible_types_filter
from app.services.access import check_farm_access, scope_to_farms
from typing import List, Optional
import uuid

router = APIRouter()


def _out(notification: Notification, read: bool, cow: Optional[Cow] = None,
         role: Optional[str] = None) -> dict:
    d = {c.key: getattr(notification, c.key)
         for c in notification.__table__.columns}
    d["read"] = read
    d["asks"] = questions.is_open(notification, cow)
    d["can_answer"] = role is not None and questions.can_answer(notification, cow, role)
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
        select(Notification, receipt, Cow)
        .outerjoin(
            NotificationRead,
            (NotificationRead.notification_id == Notification.id)
            & (NotificationRead.user_id == current_user["id"]),
        )
        .outerjoin(Cow, Cow.id == Notification.cow_id)
        .order_by(Notification.created_at.desc())
    )
    stmt = scope_to_farms(stmt, current_user, farm_id, col=Notification.farm_id)
    # Josh's change requests (Nov 20): a technician sees no farm notices, only
    # the birth check; the farm does not see the technician's birth check.
    shown = visible_types_filter(current_user["role"], Notification.type)
    if shown is not None:
        stmt = stmt.where(shown)
    if unread_only:
        stmt = stmt.where(receipt.is_(None))
    stmt = stmt.limit(max(1, min(limit, 500)))
    rows = (await db.execute(stmt)).all()
    return [_out(n, read_id is not None, cow, current_user["role"]) for n, read_id, cow in rows]


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


@router.post("/{notification_id}/answer", response_model=NotificationOut)
async def answer(
    notification_id: uuid.UUID,
    body: NotificationAnswer,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Answer a Yes / No notice (Josh's change requests, Nov 20).

    Day 223, the farm: Yes means she is in the dry pen, the same as the
    technician's confirm on the Dry Report. Day 293, the technician: Yes opens
    the calving form in the app; nothing changes here until the calving is
    recorded. A No is recorded, and nothing more.
    """
    notice = await db.get(Notification, notification_id, with_for_update=True)
    if not notice or not await check_farm_access(db, current_user, notice.farm_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    if current_user["role"] not in questions.ANSWERERS.get(notice.type, ()):
        raise HTTPException(status_code=403, detail="This notice is not yours to answer")
    cow = (await get_cow_scoped(db, current_user, notice.cow_id, for_update=True)
           if notice.cow_id else None)
    if not questions.is_open(notice, cow):
        raise HTTPException(status_code=409, detail="This has already been answered or done")

    questions.record_answer(notice, body.answer, current_user["id"])
    if notice.type == "dry_pen" and body.answer == "yes":
        questions.mark_moved_to_dry_pen(cow, local_today())
    await db.execute(
        pg_insert(NotificationRead)
        .values(notification_id=notice.id, user_id=current_user["id"])
        .on_conflict_do_nothing()
    )
    await db.commit()
    await db.refresh(notice)
    if cow is not None:
        await db.refresh(cow)
    return _out(notice, True, cow, current_user["role"])
