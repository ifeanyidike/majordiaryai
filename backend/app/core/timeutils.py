"""Farm-local time helpers.

All routers/services must use local_today() instead of date.today() so that
"today" is computed in the farm's timezone, not the server's.
"""

from datetime import date, datetime
from typing import Union
from zoneinfo import ZoneInfo
from app.core.config import settings


def farm_tz() -> ZoneInfo:
    return ZoneInfo(settings.farm_timezone)


def local_now() -> datetime:
    return datetime.now(farm_tz())


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
