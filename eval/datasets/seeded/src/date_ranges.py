"""Build reporting periods for dashboards."""

from datetime import date, datetime, timedelta


def days_in_period(start: date, end: date) -> list[date]:
    """Every day from ``start`` to ``end``, both included."""
    count = (end - start).days
    return [start + timedelta(days=offset) for offset in range(count)]


def is_expired(expires_at: datetime) -> bool:
    """Whether a timezone-aware expiry time has passed."""
    return expires_at < datetime.now()


def week_start(day: date) -> date:
    """The Monday of the week that contains ``day``."""
    return day - timedelta(days=day.weekday())
