"""The JSON shapes of laravel-fun-lab's ``Http/Resources``, field for field.

What ``@particle-academy/fancy-fun-lab-ui`` renders, so a Python backend can
answer it exactly as the Laravel package does. These return data; they serve
nothing. Timestamps are Carbon's ``toIso8601String()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .clock import iso
from .leaderboard import LeaderboardEntry
from .store import Row

if TYPE_CHECKING:
    from .engine import FunLab


def gamed_metric(m: Row) -> dict[str, Any]:
    return {
        "id": m["id"],
        "slug": m["slug"],
        "name": m["name"],
        "description": m["description"],
        "icon": m["icon"],
        "active": bool(m["active"]),
        "created_at": iso(m["created_at"]),
        "updated_at": iso(m["updated_at"]),
    }


def metric_level(lab: FunLab, lv: Row) -> dict[str, Any]:
    metric = lab.store.get("gamed_metrics", int(lv["gamed_metric_id"]))
    return {
        "id": lv["id"],
        "gamed_metric_id": lv["gamed_metric_id"],
        "gamed_metric_slug": metric["slug"] if metric else None,
        "level": int(lv["level"]),
        "xp_threshold": int(lv["xp_threshold"]),
        "name": lv["name"],
        "description": lv["description"],
        "created_at": iso(lv["created_at"]),
        "updated_at": iso(lv["updated_at"]),
    }


def achievement(a: Row) -> dict[str, Any]:
    return {
        "id": a["id"],
        "slug": a["slug"],
        "name": a["name"],
        "description": a["description"],
        "icon": a["icon"],
        "awardable_type": a["awardable_type"],
        "meta": a["meta"],
        "is_active": bool(a["is_active"]),
        "sort_order": int(a["sort_order"]),
        "created_at": iso(a["created_at"]),
        "updated_at": iso(a["updated_at"]),
    }


def prize(lab: FunLab, p: Row) -> dict[str, Any]:
    return {
        "id": p["id"],
        "slug": p["slug"],
        "name": p["name"],
        "description": p["description"],
        "type": p["type"],
        "cost_in_points": float(p["cost_in_points"]),
        "inventory_quantity": p["inventory_quantity"],
        "remaining_inventory": lab.remaining_inventory(p),
        "meta": p["meta"],
        "is_active": bool(p["is_active"]),
        "sort_order": int(p["sort_order"]),
        "created_at": iso(p["created_at"]),
        "updated_at": iso(p["updated_at"]),
    }


def profile(p: Row) -> dict[str, Any]:
    return {
        "id": p["id"],
        "awardable_type": p["awardable_type"],
        "awardable_id": p["awardable_id"],
        "is_opted_in": bool(p["is_opted_in"]),
        "display_preferences": p["display_preferences"],
        "visibility_settings": p["visibility_settings"],
        "total_xp": int(p["total_xp"]),
        "achievement_count": int(p["achievement_count"]),
        "prize_count": int(p["prize_count"]),
        "last_activity_at": iso(p["last_activity_at"]),
        "created_at": iso(p["created_at"]),
        "updated_at": iso(p["updated_at"]),
    }


def profile_metric(lab: FunLab, m: Row) -> dict[str, Any]:
    """``AwardResource``: a profile's XP in one gamed metric."""
    metric = lab.store.get("gamed_metrics", int(m["gamed_metric_id"]))
    return {
        "id": m["id"],
        "profile_id": m["profile_id"],
        "gamed_metric_id": m["gamed_metric_id"],
        "gamed_metric_slug": metric["slug"] if metric else None,
        "gamed_metric_name": metric["name"] if metric else None,
        "total_xp": int(m["total_xp"]),
        "current_level": int(m["current_level"]),
        "created_at": iso(m["created_at"]),
        "updated_at": iso(m["updated_at"]),
    }


def achievement_grant(lab: FunLab, g: Row) -> dict[str, Any]:
    """``AwardGrantResource`` for an achievement grant."""
    a = lab.store.get("achievements", int(g["achievement_id"]))
    return {
        "grant_type": "achievement",
        "id": g["id"],
        "profile_id": g["profile_id"],
        "achievement_id": g["achievement_id"],
        "achievement_slug": a["slug"] if a else None,
        "achievement_name": a["name"] if a else None,
        "reason": g["reason"],
        "source": g["source"],
        "meta": g["meta"],
        "granted_at": iso(g["created_at"]),
    }


def prize_grant(lab: FunLab, g: Row) -> dict[str, Any]:
    """``AwardGrantResource`` for a prize grant."""
    p = lab.store.get("prizes", int(g["prize_id"]))
    return {
        "grant_type": "prize",
        "id": g["id"],
        "profile_id": g["profile_id"],
        "prize_id": g["prize_id"],
        "prize_slug": p["slug"] if p else None,
        "prize_name": p["name"] if p else None,
        "status": g["status"],
        "reason": g["reason"],
        "source": g["source"],
        "meta": g["meta"],
        "granted_at": iso(g["created_at"]),
    }


def leaderboard_entry(e: LeaderboardEntry) -> dict[str, Any]:
    p = e.profile
    out: dict[str, Any] = {
        "rank": e.rank,
        "id": p["id"],
        "awardable_type": p["awardable_type"],
        "awardable_id": p["awardable_id"],
        "total_xp": int(p["total_xp"]),
        "achievement_count": int(p["achievement_count"]),
        "prize_count": int(p["prize_count"]),
        "last_activity_at": iso(p["last_activity_at"]),
    }
    if e.metric_slug is not None:
        out["metric"] = {
            "slug": e.metric_slug,
            "total_xp": int(e.metric_xp or 0),
            "current_level": int(e.metric_level or 0),
        }
    if e.period_xp is not None:
        out["period_xp"] = int(e.period_xp)
    return out
