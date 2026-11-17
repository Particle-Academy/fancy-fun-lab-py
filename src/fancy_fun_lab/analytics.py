"""``AnalyticsBuilder``: aggregates over the event log, as laravel-fun-lab 0.8.0 reads it.

Every aggregate is computed by the engine over the rows the store returns, with
SQL's rules: ``total``/``average``/``min``/``max`` ignore rows with no amount
(achievements and prizes carry none), ``average`` of nothing is 0.0 and
``min``/``max`` of nothing is ``None``.

The ``week`` time-series interval is NOT pinned by the shared tables: on
laravel-fun-lab it means a different week on each database (SQLite and MySQL
count Monday-start weeks from 00, Postgres uses ISO weeks). Here it is
SQLite's ``%Y-%W``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .clock import iso, parse_datetime, start_of_day, start_of_month, start_of_week, start_of_year
from .errors import FunLabError
from .store import Row

if TYPE_CHECKING:
    from .engine import FunLab, Subject

AWARD_TYPES = ("points", "achievement", "prize", "badge")

_SERIES = {
    "hour": "%Y-%m-%d %H:00:00",
    "day": "%Y-%m-%d",
    "week": "%Y-%W",
    "month": "%Y-%m",
    "year": "%Y",
}


class AnalyticsBuilder:
    def __init__(self, lab: FunLab) -> None:
        self._lab = lab
        self._award_type: str | None = None
        self._awardable_type: str | None = None
        self._awardable_id: Any = None
        self._source: str | None = None
        self._achievement: str | None = None
        self._start: datetime | None = None
        self._end: datetime | None = None

    # --- filters -----------------------------------------------------------

    def by_type(self, award_type: str) -> AnalyticsBuilder:
        if award_type not in AWARD_TYPES:
            raise FunLabError(
                f'"{award_type}" is not a valid award type ({", ".join(AWARD_TYPES)})'
            )
        self._award_type = award_type
        return self

    def for_awardable_type(self, awardable_type: str) -> AnalyticsBuilder:
        self._awardable_type = awardable_type
        return self

    def for_awardable(self, subject: Subject) -> AnalyticsBuilder:
        """That one subject: its type AND its id."""
        self._awardable_type = subject.type
        self._awardable_id = subject.id
        return self

    def from_source(self, source: str) -> AnalyticsBuilder:
        self._source = source
        return self

    def for_achievement(self, achievement_slug: str) -> AnalyticsBuilder:
        self._achievement = achievement_slug
        return self

    def period(self, period: str | None = None) -> AnalyticsBuilder:
        """``daily``, ``weekly`` (from Monday), ``monthly``, ``yearly`` or ``all-time``/None."""
        if period is None or period == "all-time":
            self._start = self._end = None
            return self
        now = self._lab.now()
        self._end = now
        starts = {
            "daily": start_of_day,
            "weekly": start_of_week,
            "monthly": start_of_month,
            "yearly": start_of_year,
        }
        self._start = starts[period](now) if period in starts else None
        return self

    def between(self, start: str | datetime, end: str | datetime | None = None) -> AnalyticsBuilder:
        self._start = parse_datetime(start)
        self._end = parse_datetime(end) if end is not None else self._lab.now()
        return self

    def since(self, start: str | datetime) -> AnalyticsBuilder:
        self._start = parse_datetime(start)
        self._end = self._lab.now()
        return self

    def until(self, end: str | datetime) -> AnalyticsBuilder:
        self._end = parse_datetime(end)
        return self

    # --- the query ---------------------------------------------------------

    def _matches(self, row: Row, with_achievement: bool = True) -> bool:
        if self._award_type is not None and row["award_type"] != self._award_type:
            return False
        if self._awardable_type is not None and row["awardable_type"] != self._awardable_type:
            return False
        if self._awardable_id is not None and row["awardable_id"] != self._awardable_id:
            return False
        if (
            with_achievement
            and self._achievement is not None
            and row["achievement_slug"] != self._achievement
        ):
            return False
        if self._source is not None and row["source"] != self._source:
            return False
        at = row["occurred_at"]
        if self._start is not None and at < self._start:
            return False
        return not (self._end is not None and at > self._end)

    def rows(self) -> list[Row]:
        """The event-log rows every filter admits, in id order."""
        return [r for r in self._lab.store.select("event_logs") if self._matches(r)]

    @staticmethod
    def _amounts(rows: list[Row]) -> list[float]:
        return [float(r["amount"]) for r in rows if r["amount"] is not None]

    @staticmethod
    def _distinct(rows: list[Row]) -> int:
        return len({f"{r['awardable_type']}-{r['awardable_id']}" for r in rows})

    def count(self) -> int:
        return len(self.rows())

    def total(self) -> float:
        return float(sum(self._amounts(self.rows())))

    def average(self) -> float:
        amounts = self._amounts(self.rows())
        return sum(amounts) / len(amounts) if amounts else 0.0

    def min(self) -> float | None:
        amounts = self._amounts(self.rows())
        return min(amounts) if amounts else None

    def max(self) -> float | None:
        amounts = self._amounts(self.rows())
        return max(amounts) if amounts else None

    def active_users(self) -> int:
        return self._distinct(self.rows())

    def achievement_completion_rate(self, achievement_slug: str | None = None) -> float:
        if achievement_slug is not None:
            self._achievement = achievement_slug
        if self._achievement is None:
            return 0.0
        eligible = self._distinct(
            [r for r in self._lab.store.select("event_logs") if self._matches(r, False)]
        )
        if eligible == 0:
            return 0.0
        completed = self._distinct(
            [r for r in self.rows() if r["achievement_slug"] == self._achievement]
        )
        return completed / eligible * 100

    def time_series(self, interval: str = "day") -> list[dict[str, Any]]:
        fmt = _SERIES.get(interval, _SERIES["day"])
        buckets: dict[str, list[Row]] = {}
        for row in self.rows():
            buckets.setdefault(row["occurred_at"].strftime(fmt), []).append(row)
        return [
            {"period": period, "count": len(rows), "total": float(sum(self._amounts(rows)))}
            for period, rows in sorted(buckets.items())
        ]

    def _grouped(self, key: str) -> dict[str, list[Row]]:
        groups: dict[str, list[Row]] = {}
        for row in self.rows():
            value = row[key]
            groups.setdefault(
                "unknown" if value is None and key == "source" else str(value), []
            ).append(row)
        return groups

    def by_award_type(self) -> dict[str, dict[str, Any]]:
        return {
            k: {"count": len(rows), "total": float(sum(self._amounts(rows)))}
            for k, rows in self._grouped("award_type").items()
        }

    def by_awardable_type(self) -> dict[str, dict[str, Any]]:
        return {
            k: {
                "count": len(rows),
                "total": float(sum(self._amounts(rows))),
                "unique_awardables": len({r["awardable_id"] for r in rows}),
            }
            for k, rows in self._grouped("awardable_type").items()
        }

    def by_source(self) -> dict[str, dict[str, Any]]:
        return {
            k: {"count": len(rows), "total": float(sum(self._amounts(rows)))}
            for k, rows in self._grouped("source").items()
        }

    def export(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Newest first; rows logged in the same second break on id, newest first."""
        rows = sorted(self.rows(), key=lambda r: (r["occurred_at"], r["id"]), reverse=True)
        if limit is not None:
            rows = rows[:limit]
        return [
            {
                "id": r["id"],
                "event_type": r["event_type"],
                "award_type": r["award_type"],
                "awardable_type": r["awardable_type"],
                "awardable_id": r["awardable_id"],
                "achievement_slug": r["achievement_slug"],
                "amount": r["amount"],
                "reason": r["reason"],
                "source": r["source"],
                "occurred_at": iso(r["occurred_at"]),
                "context": r["context"],
            }
            for r in rows
        ]
