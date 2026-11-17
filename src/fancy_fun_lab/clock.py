"""Time, the way the PHP engine sees it.

Laravel stores timestamps to the second, in the app timezone, and prints them
with ``toIso8601String()``. The engine therefore works in naive UTC datetimes
truncated to whole seconds: a clock with microseconds would make two events in
the same request differ where PHP's are equal, and a period boundary would move.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

#: Returns "now". Injected so the fixtures and the period boards can freeze it.
Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


def normalize(value: datetime) -> datetime:
    """Naive UTC, whole seconds."""
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(microsecond=0)


def parse_datetime(value: str | datetime) -> datetime:
    """An ISO 8601 string (or a datetime) as naive UTC; a bare value is UTC."""
    if isinstance(value, datetime):
        return normalize(value)
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return normalize(datetime.fromisoformat(text))


def iso(value: datetime | None) -> str | None:
    """Carbon's ``toIso8601String()`` for a UTC timestamp."""
    if value is None:
        return None
    return value.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def to_db(value: datetime) -> str:
    """Laravel's datetime column format."""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def from_db(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")


def start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0)


def start_of_week(now: datetime) -> datetime:
    """Carbon's default week starts on Monday."""
    return start_of_day(now) - timedelta(days=now.weekday())


def start_of_month(now: datetime) -> datetime:
    return start_of_day(now).replace(day=1)


def start_of_year(now: datetime) -> datetime:
    return start_of_day(now).replace(month=1, day=1)
