"""Farm-local time helpers.

All routers/services must use local_today() instead of date.today() so that
"today" is computed in the farm's timezone, not the server's.
"""

from contextvars import ContextVar
from datetime import date, datetime
from typing import Optional, Union
from zoneinfo import ZoneInfo
from app.core.config import settings


def farm_tz() -> ZoneInfo:
    return ZoneInfo(settings.farm_timezone)


# When the phone recorded the save this request carries (offline mode): an
# outcome saved Monday with no signal and sent Tuesday happened on Monday.
# Set only for that one request (app/core/idempotency.py).
recorded_at: ContextVar[Optional[datetime]] = ContextVar("recorded_at", default=None)


def local_now() -> datetime:
    at = recorded_at.get()
    return at.astimezone(farm_tz()) if at is not None else datetime.now(farm_tz())


def local_today() -> date:
    return local_now().date()


def ensure_aware(value: datetime) -> datetime:
    """Attach the farm timezone to naive datetimes (asyncpg needs aware values
    for timestamptz columns)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=farm_tz())
    return value


def to_local_date(value: Union[date, datetime]) -> date:
    """Normalize a date or (naive/aware) datetime to a farm-local date."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(farm_tz())
        return value.date()
    return value
