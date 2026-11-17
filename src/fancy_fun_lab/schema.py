"""The table layout, column for column, of laravel-fun-lab's migrations.

Both stores share it: ``InMemoryStore`` uses it to fill defaults, and
``SqliteStore`` to create tables a Laravel app would recognise and to convert
values. Tables are named without their prefix here; stores add ``lfl_`` (or
whatever prefix they are given, as ``lfl.table_prefix`` does).

Column kinds: ``id``, ``int``, ``str``, ``bool``, ``json``, ``datetime`` and
``decimal`` (a decimal(…, 2) column: stored as a number, read as a float rounded
to two places, as Laravel's ``decimal:2`` cast does).
"""

from __future__ import annotations

from typing import Any

#: table -> column -> (kind, default)
SCHEMA: dict[str, dict[str, tuple[str, Any]]] = {
    "gamed_metrics": {
        "id": ("id", None),
        "slug": ("str", None),
        "name": ("str", None),
        "description": ("str", None),
        "icon": ("str", None),
        "active": ("bool", True),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "metric_levels": {
        "id": ("id", None),
        "gamed_metric_id": ("int", None),
        "level": ("int", None),
        "xp_threshold": ("int", None),
        "name": ("str", None),
        "description": ("str", None),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "metric_level_groups": {
        "id": ("id", None),
        "slug": ("str", None),
        "name": ("str", None),
        "description": ("str", None),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "metric_level_group_metrics": {
        "id": ("id", None),
        "metric_level_group_id": ("int", None),
        "gamed_metric_id": ("int", None),
        "weight": ("decimal", 1.0),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "metric_level_group_levels": {
        "id": ("id", None),
        "metric_level_group_id": ("int", None),
        "level": ("int", None),
        "xp_threshold": ("int", None),
        "name": ("str", None),
        "description": ("str", None),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "achievements": {
        "id": ("id", None),
        "slug": ("str", None),
        "name": ("str", None),
        "description": ("str", None),
        "icon": ("str", None),
        "awardable_type": ("str", None),
        "meta": ("json", None),
        "is_active": ("bool", True),
        "is_hidden": ("bool", False),
        "sort_order": ("int", 0),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "achievement_metric_levels": {
        "id": ("id", None),
        "achievement_id": ("int", None),
        "metric_level_id": ("int", None),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "achievement_metric_level_group_levels": {
        "id": ("id", None),
        "achievement_id": ("int", None),
        "metric_level_group_level_id": ("int", None),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "prizes": {
        "id": ("id", None),
        "slug": ("str", None),
        "name": ("str", None),
        "description": ("str", None),
        "type": ("str", None),
        "cost_in_points": ("decimal", 0.0),
        "inventory_quantity": ("int", None),
        "meta": ("json", None),
        "is_active": ("bool", True),
        "sort_order": ("int", 0),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "profiles": {
        "id": ("id", None),
        "awardable_type": ("str", None),
        "awardable_id": ("int", None),
        "is_opted_in": ("bool", True),
        "display_preferences": ("json", None),
        "visibility_settings": ("json", None),
        "total_xp": ("int", 0),
        "achievement_count": ("int", 0),
        "prize_count": ("int", 0),
        "last_activity_at": ("datetime", None),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "profile_metrics": {
        "id": ("id", None),
        "profile_id": ("int", None),
        "gamed_metric_id": ("int", None),
        "total_xp": ("int", 0),
        "current_level": ("int", 1),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "profile_metric_groups": {
        "id": ("id", None),
        "profile_id": ("int", None),
        "metric_level_group_id": ("int", None),
        "current_level": ("int", 1),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "achievement_grants": {
        "id": ("id", None),
        "profile_id": ("int", None),
        "achievement_id": ("int", None),
        "reason": ("str", None),
        "source": ("str", None),
        "meta": ("json", None),
        "granted_at": ("datetime", None),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "prize_grants": {
        "id": ("id", None),
        "profile_id": ("int", None),
        "prize_id": ("int", None),
        "reason": ("str", None),
        "source": ("str", None),
        "status": ("str", "pending"),
        "granted_at": ("datetime", None),
        "claimed_at": ("datetime", None),
        "fulfilled_at": ("datetime", None),
        "meta": ("json", None),
        "created_at": ("datetime", None),
        "updated_at": ("datetime", None),
    },
    "event_logs": {
        "id": ("id", None),
        "event_type": ("str", None),
        "award_type": ("str", None),
        "awardable_type": ("str", None),
        "awardable_id": ("int", None),
        "award_id": ("int", None),
        "achievement_slug": ("str", None),
        "amount": ("float", None),
        "reason": ("str", None),
        "source": ("str", None),
        "context": ("json", None),
        "occurred_at": ("datetime", None),
        "created_at": ("datetime", None),
    },
}

#: Unique keys, as the migrations declare them (SqliteStore creates them).
UNIQUE: dict[str, list[tuple[str, ...]]] = {
    "gamed_metrics": [("slug",)],
    "metric_levels": [("gamed_metric_id", "level")],
    "metric_level_groups": [("slug",)],
    "metric_level_group_metrics": [("metric_level_group_id", "gamed_metric_id")],
    "metric_level_group_levels": [("metric_level_group_id", "level")],
    "achievements": [("slug",)],
    "achievement_metric_levels": [("achievement_id", "metric_level_id")],
    "achievement_metric_level_group_levels": [("achievement_id", "metric_level_group_level_id")],
    "prizes": [("slug",)],
    "profiles": [("awardable_type", "awardable_id")],
    "profile_metrics": [("profile_id", "gamed_metric_id")],
    "profile_metric_groups": [("profile_id", "metric_level_group_id")],
    "achievement_grants": [("profile_id", "achievement_id")],
}


def two_places(value: float) -> float:
    """Laravel's ``decimal:2`` cast: rounded half up to two places."""
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(repr(float(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
