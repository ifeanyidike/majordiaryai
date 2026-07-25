"""Farmer notifications: an in-app record plus a best-effort SendGrid email."""

import asyncio
import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification
from app.services.email import is_configured, send_email

logger = logging.getLogger("app.notifications")

# Keep strong references to fire-and-forget email tasks so they aren't GC'd
# mid-flight.
_bg_tasks: set = set()


async def _email_notification(farm_id: uuid.UUID, type_: str, message: str) -> None:
    """Look up the farm's contact email in a fresh session and send it."""
    # Imported here to avoid a circular import (database -> models -> ...).
    from app.core.database import SessionLocal
    from app.models.models import Farm

    try:
        async with SessionLocal() as session:
            farm = await session.get(Farm, farm_id)
        if not farm or not farm.email:
            return
        title = type_.replace("_", " ").title()
        await send_email(
            to=farm.email,
            subject=f"Major Dairy AI — {title}",
            html=f"<p>{message}</p>",
            text=message,
        )
    except Exception:
        logger.exception("Failed to email notification for farm %s", farm_id)


def send_notification_email(notification: Notification) -> None:
    """Fire-and-forget the notification email (no-op if SendGrid isn't set up).

    Scheduled on the running event loop so it never blocks the request; failures
    are logged and swallowed.
    """
    if not is_configured():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no running loop (e.g. a sync script) — skip email
    task = loop.create_task(
        _email_notification(notification.farm_id, notification.type, notification.message)
    )
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def create_notification(
    db: AsyncSession,
    farm_id: uuid.UUID,
    cow_id: Optional[uuid.UUID],
    type: str,
    message: str,
) -> Notification:
    """Add an in-app notification (committed by the caller) and email the farm."""
    notification = Notification(farm_id=farm_id, cow_id=cow_id, type=type, message=message)
    db.add(notification)
    send_notification_email(notification)
    return notification
