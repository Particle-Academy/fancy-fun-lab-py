"""``LeaderboardBuilder``: ranked boards, as laravel-fun-lab 0.8.0 computes them.

- All-time boards rank on the profile totals (``total_xp``, or
  ``achievement_count`` / ``prize_count``).
- A ``daily``, ``weekly`` (from Monday) or ``monthly`` board ranks on the XP
  EARNED since the period started, summed from the event log's ``xp_awarded``
  rows, and lists only profiles that earned some. With the log off it is
  refused (``PeriodLeaderboardUnavailable``). Any other period string is an
  all-time board, as in PHP.
- A metric board ranks on that metric's XP and lists only profiles with a
  record for it; with a period, on that metric's XP earned in the period.
- Opted-out profiles are excluded unless asked; ties break on profile id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .clock import start_of_day, start_of_month, start_of_week
from .errors import FunLabError, PeriodLeaderboardUnavailable
from .store import Row

if TYPE_CHECKING:
    from .engine import FunLab


@dataclass
class LeaderboardEntry:
    rank: int
    profile: Row
    metric_slug: str | None = None
    metric_xp: int | None = None
    metric_level: int | None = None
    period_xp: float | None = None


@dataclass
class LeaderboardPage:
    total: int
    per_page: int
    current_page: int
    items: list[LeaderboardEntry]

    @property
    def last_page(self) -> int:
        return max(1, -(-self.total // self.per_page))


class LeaderboardBuilder:
    def __init__(self, lab: FunLab) -> None:
        self._lab = lab
        self._type: str | None = None
        self._sort = "xp"
        self._period: str | None = None
        self._per_page = 15
        self._page: int | None = None
        self._exclude_opted_out = True
        self._metric: str | Row | None = None

    def for_(self, awardable_type: str) -> LeaderboardBuilder:
        self._type = awardable_type
        return self

    def by(self, sort: str) -> LeaderboardBuilder:
        """``xp`` (alias ``points``), ``achievements`` or ``prizes``."""
        self._sort = "xp" if sort == "points" else sort
        return self

    def period(self, period: str | None = None) -> LeaderboardBuilder:
        self._period = period
        return self

    def metric(self, metric: str | Row | None) -> LeaderboardBuilder:
        self._metric = metric
        return self

    def exclude_opted_out(self, exclude: bool = True) -> LeaderboardBuilder:
        self._exclude_opted_out = exclude
        return self

    def per_page(self, per_page: int) -> LeaderboardBuilder:
        self._per_page = per_page
        return self

    def page(self, page: int) -> LeaderboardBuilder:
        self._page = page
        return self

    def get(self) -> list[LeaderboardEntry]:
        return self._ranked(self._rows(), 0)

    def take(self, limit: int) -> list[LeaderboardEntry]:
        return self._ranked(self._rows()[: max(0, limit)], 0)

    def paginate(self) -> LeaderboardPage:
        rows = self._rows()
        page = self._page if self._page is not None and self._page >= 1 else 1
        offset = (page - 1) * self._per_page
        return LeaderboardPage(
            total=len(rows),
            per_page=self._per_page,
            current_page=page,
            items=self._ranked(rows[offset : offset + self._per_page], offset),
        )

    # --- the query ---------------------------------------------------------

    @staticmethod
    def _ranked(rows: list[LeaderboardEntry], offset: int) -> list[LeaderboardEntry]:
        for i, row in enumerate(rows):
            row.rank = offset + i + 1
        return rows

    def _period_start(self) -> datetime | None:
        now = self._lab.now()
        if self._period == "daily":
            return start_of_day(now)
        if self._period == "weekly":
            return start_of_week(now)
        if self._period == "monthly":
            return start_of_month(now)
        return None

    def _resolve_metric(self) -> Row | None:
        if self._metric is None or isinstance(self._metric, dict):
            return self._metric
        metric = self._lab.gamed_metric(self._metric)
        if metric is None:
            raise FunLabError(f"GamedMetric '{self._metric}' not found.")
        return metric

    def _earned(self, start: datetime, metric: Row | None) -> dict[tuple[str, Any], float]:
        config = self._lab.config
        if not (config.log_to_database and config.dispatch):
            raise PeriodLeaderboardUnavailable(
                "A period leaderboard is computed from the event log, which is off. "
                "Use an all-time board, or turn the event log on."
            )
        sums: dict[tuple[str, Any], float] = {}
        for log in self._lab.store.select("event_logs", {"event_type": "xp_awarded"}):
            if log["occurred_at"] < start:
                continue
            if (
                metric is not None
                and (log["context"] or {}).get("gamed_metric_slug") != metric["slug"]
            ):
                continue
            key = (str(log["awardable_type"]), log["awardable_id"])
            sums[key] = sums.get(key, 0.0) + float(log["amount"] or 0)
        return {k: v for k, v in sums.items() if v > 0}

    def _rows(self) -> list[LeaderboardEntry]:
        lab = self._lab
        profiles = lab.store.select("profiles")
        if self._type is not None:
            profiles = [p for p in profiles if p["awardable_type"] == self._type]
        if self._exclude_opted_out:
            profiles = [p for p in profiles if p["is_opted_in"]]

        metric = self._resolve_metric()
        start = self._period_start() if self._period not in (None, "all-time") else None
        period_board = start is not None
        earned = self._earned(start, metric) if start is not None else None

        rows: list[LeaderboardEntry] = []
        for p in profiles:
            entry = LeaderboardEntry(rank=0, profile=p)
            if metric is not None:
                pm = lab._one("profile_metrics", profile_id=p["id"], gamed_metric_id=metric["id"])
                if pm is None:
                    continue
                entry.metric_slug = str(metric["slug"])
                entry.metric_xp = int(pm["total_xp"])
                entry.metric_level = int(pm["current_level"])
            if earned is not None:
                who = (str(p["awardable_type"]), p["awardable_id"])
                if who not in earned:
                    continue
                entry.period_xp = earned[who]
            rows.append(entry)

        def key(e: LeaderboardEntry) -> tuple[float, ...]:
            p = e.profile
            if metric is not None:
                score = float(
                    e.period_xp if period_board and e.period_xp is not None else e.metric_xp or 0
                )
                if self._sort == "achievements":
                    return (-p["achievement_count"], -score, p["id"])
                if self._sort == "prizes":
                    return (-p["prize_count"], -score, p["id"])
                return (-score, p["id"])
            if period_board:
                if self._sort == "achievements":
                    return (-p["achievement_count"], p["id"])
                if self._sort == "prizes":
                    return (-p["prize_count"], p["id"])
                return (-(e.period_xp or 0.0), p["id"])
            if self._sort == "achievements":
                return (-p["achievement_count"], p["id"])
            if self._sort == "prizes":
                return (-p["prize_count"], p["id"])
            return (-p["total_xp"], p["id"])

        return sorted(rows, key=key)
