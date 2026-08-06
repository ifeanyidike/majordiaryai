"""Farmer notifications: an in-app record plus a best-effort SendGrid email."""

import asyncio
import logging
import uuid
from typing import Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

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


def _schedule_email(farm_id: uuid.UUID, type_: str, message: str) -> None:
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
    task = loop.create_task(_email_notification(farm_id, type_, message))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


# Emails are queued on the session and sent only after COMMIT — sending inside
# the transaction emailed the farmer about state changes that could still roll
# back (e.g. a dry-off notice for a transition that never persisted).
#
# Known limitation: the queue is transaction-scoped, not savepoint-scoped. A
# SAVEPOINT rollback (after_soft_rollback) discards its notification rows but
# leaves their queued emails, which then send if the outer transaction commits.
# No route uses savepoints today; if one ever does, the queue needs per-
# savepoint bookkeeping before that route calls create_notification.
_PENDING_EMAILS_KEY = "pending_notification_emails"


@event.listens_for(Session, "after_commit")
def _send_pending_emails(session: Session) -> None:
    for farm_id, type_, message in session.info.pop(_PENDING_EMAILS_KEY, []):
        _schedule_email(farm_id, type_, message)


@event.listens_for(Session, "after_rollback")
def _drop_pending_emails(session: Session) -> None:
    session.info.pop(_PENDING_EMAILS_KEY, None)


def create_notification(
    db: AsyncSession,
    farm_id: uuid.UUID,
    cow_id: Optional[uuid.UUID],
    type: str,
    message: str,
) -> Notification:
    """Add an in-app notification and queue the farm email for after commit."""
    notification = Notification(farm_id=farm_id, cow_id=cow_id, type=type, message=message)
    db.add(notification)
    db.sync_session.info.setdefault(_PENDING_EMAILS_KEY, []).append(
        (farm_id, type, message)
    )
    return notification
