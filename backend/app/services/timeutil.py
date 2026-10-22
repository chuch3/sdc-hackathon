from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import Settings


def business_zone(settings: Settings | None = None) -> ZoneInfo:
    return ZoneInfo((settings or Settings()).business_timezone)


def business_date(value: datetime, settings: Settings | None = None) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(business_zone(settings)).date()


def utc_start(day: date, settings: Settings | None = None) -> datetime:
    """First UTC instant of a business date, for range queries on stored timestamps."""
    settings = settings or Settings()
    local = datetime.combine(day, datetime.min.time(), tzinfo=business_zone(settings))
    return local.astimezone(timezone.utc)
