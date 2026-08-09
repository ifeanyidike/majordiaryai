"""Farmer notifications: an in-app record plus a best-effort SendGrid email."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
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


async def _record_outcome(
    notification_id: uuid.UUID, status: str, error: Optional[str] = None
) -> None:
    """Stamp the delivery result on the notification row.

    Written from the background task in its own session, after the request's
    transaction is long committed. Best-effort: if this write fails we have
    still sent (or not sent) the mail, and losing the audit line must not raise
    into the task.
    """
    from app.core.database import SessionLocal
    from app.models.models import Notification

    try:
        async with SessionLocal() as session:
            row = await session.get(Notification, notification_id)
            if row is None:
                return
            row.email_status = status
            row.emailed_at = datetime.now(timezone.utc)
            row.email_error = (error or None) and error[:500]
            await session.commit()
    except Exception:
        logger.exception("Could not record email outcome for notification %s", notification_id)


async def _email_notification(
    notification_id: uuid.UUID, farm_id: uuid.UUID, type_: str, message: str
) -> None:
    """Look up the farm's contact email in a fresh session, send, record result."""
    # Imported here to avoid a circular import (database -> models -> ...).
    from app.core.database import SessionLocal
    from app.models.models import Farm

    try:
        async with SessionLocal() as session:
            farm = await session.get(Farm, farm_id)
        if not farm or not farm.email:
            # A farm with no address is a real gap in the farmer's coverage —
            # record it so it can be found, rather than silently doing nothing.
            await _record_outcome(notification_id, "no_email")
            logger.warning("Farm %s has no email; notification not delivered", farm_id)
            return
        title = type_.replace("_", " ").title()
        ok = await send_email(
            to=farm.email,
            subject=f"Major Dairy AI — {title}",
            html=f"<p>{message}</p>",
            text=message,
        )
        await _record_outcome(notification_id, "sent" if ok else "failed",
                              None if ok else "provider rejected the message")
    except Exception as exc:
        logger.exception("Failed to email notification for farm %s", farm_id)
        await _record_outcome(notification_id, "failed", str(exc))


def _schedule_email(
    notification_id: uuid.UUID, farm_id: uuid.UUID, type_: str, message: str
) -> None:
    """Fire-and-forget the notification email (no-op if SendGrid isn't set up).

    Scheduled on the running event loop so it never blocks the request; failures
    are logged and recorded on the row.
    """
    if not is_configured():
        # Not an error — sending is simply switched off — but the row should say
        # so, otherwise "no email arrived" is indistinguishable from a failure.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(_record_outcome(notification_id, "disabled"))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no running loop (e.g. a sync script) — skip email
    task = loop.create_task(_email_notification(notification_id, farm_id, type_, message))
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
    for notification_id, farm_id, type_, message in session.info.pop(_PENDING_EMAILS_KEY, []):
        _schedule_email(notification_id, farm_id, type_, message)


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
    # id is assigned client-side so the queued email can reference the row
    # without needing a flush before commit.
    notification = Notification(
        id=uuid.uuid4(), farm_id=farm_id, cow_id=cow_id, type=type, message=message
    )
    db.add(notification)
    db.sync_session.info.setdefault(_PENDING_EMAILS_KEY, []).append(
        (notification.id, farm_id, type, message)
    )
    return notification
