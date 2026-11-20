"""Saves sent with a one-time code (Idempotency-Key header) happen once.

Offline mode (Josh's Part A platform tests): "Pending records sync
automatically when the connection returns, with no duplicates" and "Losing
signal mid-save leaves no half-saved record". The phone gives every outcome
a code and sends it again with the same code until it gets an answer.

The code is added to the request's own session before the route runs, so it
is committed together with the save or not at all. A second request with a
committed code stops here with 200 "already recorded". A second request while
the first is still running waits on the key's unique index, then sees which
way the first went.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.timeutils import recorded_at
from app.models.models import IdempotencyKey

logger = logging.getLogger("app.idempotency")

HEADER = "Idempotency-Key"
RECORDED_AT = "Recorded-At"
# A save waiting this long on a phone is still believed; older, or in the
# future (a wrong phone clock), and the server's own time is used.
_OLDEST = timedelta(days=30)
_CLOCK_SLACK = timedelta(minutes=10)


def _when_recorded(request: Request) -> Optional[datetime]:
    raw = (request.headers.get(RECORDED_AT) or "").strip()
    if not raw:
        return None
    try:
        at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if at.tzinfo is None:
        return None
    now = datetime.now(timezone.utc)
    return at if now - _OLDEST <= at <= now + _CLOCK_SLACK else None
_WRITES = {"POST", "PUT", "PATCH", "DELETE"}


class AlreadyRecorded(Exception):
    """This code's save is already in the database."""


async def once(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """A dependency with a yield: the recorded time (below) holds for exactly
    this request, and is cleared after it."""
    if request.method not in _WRITES:
        yield
        return
    # The day it happened, not the day it reached us: dates the server stamps
    # itself (a shot given, a cull, a move to the dry pen) follow the phone.
    token = recorded_at.set(_when_recorded(request))
    try:
        key = (request.headers.get(HEADER) or "").strip()[:100]
        if key:
            await _claim(db, key, request, current_user)
        yield
    finally:
        recorded_at.reset(token)


async def _claim(db: AsyncSession, key: str, request: Request, current_user: dict) -> None:
    try:
        # A savepoint, so a repeat undoes only this insert and leaves the
        # session usable.
        async with db.begin_nested():
            db.add(IdempotencyKey(
                user_id=uuid.UUID(str(current_user["id"])), key=key,
                method=request.method, path=request.url.path,
            ))
    except IntegrityError:
        # Seen in the logs as the phones resending after a lost answer.
        logger.info("save already recorded: user %s %s %s", current_user["id"],
                    request.method, request.url.path)
        raise AlreadyRecorded()
