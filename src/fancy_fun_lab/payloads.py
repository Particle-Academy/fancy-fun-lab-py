"""The broadcast payloads: what laravel-fun-lab's ``broadcastWith()`` returns.

Key for key and type for type, for ``xp.awarded``, ``metric.level-reached``,
``achievement.unlocked`` and ``prize.awarded``. This is the JSON a Laravel Echo
listener receives and ``@particle-academy/fancy-fun-lab-ui`` reads
(``feedItemFromEcho``, ``FunLabXpFeed``, ``FunLabLevelUp``), so a host that
relays these over its own socket feeds the UI exactly as a Laravel backend would.

Pinned by the shared ``fun-lab/events`` table. Every event object the engine
emits also exposes its payload as ``event.payload``; these functions are the
same serializers, for a host that builds or stores events itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .clock import iso

if TYPE_CHECKING:
    from .events import AchievementUnlocked, MetricLevelReached, PrizeAwarded, XpAwarded


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


def xp_awarded_payload(e: XpAwarded) -> dict[str, Any]:
    """``XpAwarded::broadcastWith()``. ``id`` is the profile's row for this metric."""
    return {
        "id": int(e.profile_metric["id"]),
        "profile_id": int(e.profile_metric["profile_id"]),
        "gamed_metric_id": int(e.gamed_metric["id"]),
        "gamed_metric_slug": str(e.gamed_metric["slug"]),
        "gamed_metric_name": str(e.gamed_metric["name"]),
        "amount": int(e.amount),
        "total_xp": int(e.profile_metric["total_xp"]),
        "current_level": int(e.profile_metric["current_level"]),
        "reason": e.reason,
        "source": e.source,
        "occurred_at": iso(e.occurred_at),
    }


def level_reached_payload(e: MetricLevelReached) -> dict[str, Any]:
    """``MetricLevelReached::broadcastWith()``. ``achievements`` is what this crossing granted."""
    return {
        "profile_id": int(e.profile["id"]),
        "gamed_metric_id": int(e.gamed_metric["id"]),
        "gamed_metric_slug": str(e.gamed_metric["slug"]),
        "gamed_metric_name": str(e.gamed_metric["name"]),
        "level": int(e.level["level"]),
        "level_name": _str(e.level.get("name")),
        "xp_threshold": int(e.level["xp_threshold"]),
        "total_xp": int(e.total_xp),
        "achievements": [
            {
                "id": int(a["id"]),
                "slug": str(a["slug"]),
                "name": str(a["name"]),
                "icon": _str(a.get("icon")),
            }
            for a in e.achievements
        ],
        "occurred_at": iso(e.occurred_at),
    }


def achievement_unlocked_payload(e: AchievementUnlocked) -> dict[str, Any]:
    """``AchievementUnlocked::broadcastWith()``. ``id`` is the grant's."""
    return {
        "grant_type": "achievement",
        "id": int(e.grant["id"]),
        "profile_id": int(e.grant["profile_id"]),
        "achievement_id": int(e.achievement["id"]),
        "achievement_slug": str(e.achievement["slug"]),
        "achievement_name": str(e.achievement["name"]),
        "achievement_icon": _str(e.achievement.get("icon")),
        "reason": e.reason,
        "source": e.source,
        # PHP reads the grant's created_at here, not granted_at.
        "granted_at": iso(e.grant.get("created_at")),
    }


def prize_awarded_payload(e: PrizeAwarded) -> dict[str, Any]:
    """``PrizeAwarded::broadcastWith()``. ``id`` is the grant's."""
    return {
        "grant_type": "prize",
        "id": int(e.award["id"]),
        "profile_id": int(e.award["profile_id"]),
        "prize_id": int(e.prize["id"]),
        "prize_slug": str(e.prize["slug"]),
        "prize_name": str(e.prize["name"]),
        "status": str(e.award["status"]),
        "reason": e.reason,
        "source": e.source,
        "granted_at": iso(e.award.get("granted_at")),
    }
