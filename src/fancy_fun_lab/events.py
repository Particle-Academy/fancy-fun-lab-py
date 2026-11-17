"""Events, by the names the PHP engine broadcasts them under.

``FunLab.on(name, listener)`` subscribes; ``"*"`` receives every event as
``listener(name, event)``. Nothing is broadcast: wiring an event to a socket or
a queue is the host's job, as ``lfl.events.broadcast`` is Laravel's.

Order is part of the contract and follows the PHP engine: an award emits each
``metric.level-reached`` (and the achievements its levels grant) BEFORE its own
``xp.awarded``, because PHP dispatches ``XpAwarded`` after progression runs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .clock import iso
from .store import Row

XP_AWARDED = "xp.awarded"
METRIC_LEVEL_REACHED = "metric.level-reached"
ACHIEVEMENT_UNLOCKED = "achievement.unlocked"
PRIZE_AWARDED = "prize.awarded"
AWARD_GRANTED = "award.granted"
CATALOG_MUTATED = "catalog.mutated"

#: The PHP model class each catalog entity type is, as the event log records it.
#: Written verbatim so a log shared with a Laravel app reads the same.
PHP_MODEL = {
    "gamed-metric": "LaravelFunLab\\Models\\GamedMetric",
    "metric-level": "LaravelFunLab\\Models\\MetricLevel",
    "metric-level-group": "LaravelFunLab\\Models\\MetricLevelGroup",
    "metric-level-group-level": "LaravelFunLab\\Models\\MetricLevelGroupLevel",
    "metric-level-group-metric": "LaravelFunLab\\Models\\MetricLevelGroupMetric",
    "achievement": "LaravelFunLab\\Models\\Achievement",
    "prize": "LaravelFunLab\\Models\\Prize",
}


@dataclass
class XpAwarded:
    profile_metric: Row
    gamed_metric: Row
    recipient: Any
    amount: int
    reason: str | None = None
    source: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_log(self, at: Any) -> dict[str, Any]:
        return {
            "event_type": "xp_awarded",
            "award_type": "points",
            "recipient_type": self.recipient.type,
            "recipient_id": self.recipient.id,
            "gamed_metric_id": self.gamed_metric["id"],
            "gamed_metric_slug": self.gamed_metric["slug"],
            "amount": self.amount,
            "total_xp": self.profile_metric["total_xp"],
            "current_level": self.profile_metric["current_level"],
            "reason": self.reason,
            "source": self.source,
            # PHP json-encodes an empty array as [], never {}.
            "meta": self.meta or [],
            "occurred_at": iso(at),
        }


@dataclass
class MetricLevelReached:
    profile: Row
    profile_metric: Row
    gamed_metric: Row
    level: Row
    recipient: Any
    achievements: list[Row]
    total_xp: int


@dataclass
class AchievementUnlocked:
    recipient: Any
    achievement: Row
    grant: Row
    reason: str | None = None
    source: str | None = None

    def to_log(self, at: Any) -> dict[str, Any]:
        return {
            "event_type": "achievement_unlocked",
            "award_type": "achievement",
            "recipient_type": self.recipient.type,
            "recipient_id": self.recipient.id,
            "achievement_id": self.achievement["id"],
            "achievement_slug": self.achievement["slug"],
            "achievement_name": self.achievement["name"],
            "grant_id": self.grant["id"],
            "reason": self.reason,
            "source": self.source,
            "occurred_at": iso(at),
        }


@dataclass
class PrizeAwarded:
    recipient: Any
    award: Row
    prize: Row
    reason: str | None = None
    source: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_log(self, at: Any) -> dict[str, Any]:
        return {
            "event_type": "prize_awarded",
            "award_type": "prize",
            "recipient_type": self.recipient.type,
            "recipient_id": self.recipient.id,
            "award_id": self.award["id"],
            "reason": self.reason,
            "source": self.source,
            "meta": self.meta or [],
            "occurred_at": iso(at),
        }


@dataclass
class AwardGranted:
    result: Any
    type: str
    recipient: Any
    award: Row


@dataclass
class CatalogMutated:
    entity_type: str
    model: Row
    was_created: bool
    actor: Any = None

    def to_log(self, at: Any) -> dict[str, Any]:
        return {
            "event_type": "catalog_mutated",
            "entity_type": self.entity_type,
            "entity_model": PHP_MODEL[self.entity_type],
            "entity_id": self.model["id"],
            "entity_slug": self.model.get("slug"),
            "was_created": self.was_created,
            "actor_type": getattr(self.actor, "type", None),
            "actor_id": getattr(self.actor, "id", None),
            "occurred_at": iso(at),
        }


Listener = Callable[..., Any]


class Emitter:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = {}

    def on(self, name: str, listener: Listener) -> Callable[[], None]:
        """Subscribe; returns a function that unsubscribes."""
        self._listeners.setdefault(name, []).append(listener)

        def off() -> None:
            self._listeners.get(name, []).remove(listener)

        return off

    def emit(self, name: str, event: Any) -> None:
        for listener in list(self._listeners.get(name, [])):
            listener(event)
        for listener in list(self._listeners.get("*", [])):
            listener(name, event)
