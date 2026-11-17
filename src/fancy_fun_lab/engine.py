"""The engine: ``FunLab``, its builders, and progression.

A port of laravel-fun-lab's ``AwardEngine``, ``GamedMetricService``,
``MetricLevelService``, ``MetricLevelGroupService`` and the two builders, kept
in the same shape so a behaviour question is answered by reading the PHP
method of the same name. Every rule here is pinned by a ``fun-lab/*`` row.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .clock import Clock, normalize, system_clock
from .errors import AwardRejected, FunLabError
from .events import (
    ACHIEVEMENT_UNLOCKED,
    AWARD_GRANTED,
    CATALOG_MUTATED,
    METRIC_LEVEL_REACHED,
    PRIZE_AWARDED,
    XP_AWARDED,
    AchievementUnlocked,
    AwardGranted,
    CatalogMutated,
    Emitter,
    MetricLevelReached,
    PrizeAwarded,
    XpAwarded,
)
from .schema import SCHEMA
from .setup import normalize_type, validate
from .store import InMemoryStore, Row, Store, normalize_row
from .strings import headline, slug

if TYPE_CHECKING:
    from .analytics import AnalyticsBuilder
    from .leaderboard import LeaderboardBuilder


@dataclass(frozen=True)
class Subject:
    """An awardable: what laravel-fun-lab calls a model using the ``Awardable`` trait.

    ``type`` plays the part of the PHP class name (``"user"``, ``"team"``); it
    is what achievements' ``for`` and leaderboards' ``for_()`` match on.
    """

    type: str
    id: int | str


@dataclass(frozen=True)
class FunLabConfig:
    """``config/lfl.php``'s engine settings, with the same defaults."""

    #: ``lfl.defaults.max_points_per_action``; 0 turns the cap off.
    max_points_per_action: int = 10000
    #: ``lfl.events.log_to_database``. Period leaderboards need it.
    log_to_database: bool = True
    #: ``lfl.events.dispatch``. Off means no events AND no event log.
    dispatch: bool = True


@dataclass
class AwardResult:
    """``AwardResult``: a grant's outcome. A refused grant is a result, not an error."""

    success: bool
    message: str
    award: Row | None = None

    @classmethod
    def ok(cls, award: Row) -> AwardResult:
        return cls(True, "Award granted successfully", award)

    @classmethod
    def failure(cls, message: str) -> AwardResult:
        return cls(False, message, None)

    def succeeded(self) -> bool:
        return self.success


#: A validation-pipeline step: ``(subject, award_type, amount, reason, source, meta)``.
#: Return ``{"valid": False, "message": ...}`` to refuse; anything else passes.
PipelineStep = Callable[[Subject, str, int, "str | None", "str | None", dict[str, Any]], Any]


class FunLab:
    """The facade: ``LFL::`` in laravel-fun-lab."""

    def __init__(
        self,
        store: Store | None = None,
        clock: Clock | None = None,
        config: FunLabConfig | None = None,
    ) -> None:
        self.store: Store = store if store is not None else InMemoryStore()
        self._clock: Clock = clock or system_clock
        self.config = config or FunLabConfig()
        self._emitter = Emitter()
        self._pipeline: list[PipelineStep] = []

    # --- infrastructure ----------------------------------------------------

    def now(self) -> datetime:
        return normalize(self._clock())

    def on(self, name: str, listener: Callable[..., Any]) -> Callable[[], None]:
        """Subscribe to an event by name, or ``"*"`` for ``listener(name, event)``."""
        return self._emitter.on(name, listener)

    def add_validation_step(self, step: PipelineStep) -> None:
        """``AwardValidationPipeline::addStep``: runs before every award and grant."""
        self._pipeline.append(step)

    def _validate(
        self,
        subject: Subject,
        award_type: str,
        amount: int,
        reason: str | None,
        source: str | None,
        meta: dict[str, Any],
    ) -> str | None:
        for step in self._pipeline:
            result = step(subject, award_type, amount, reason, source, meta)
            if isinstance(result, dict) and result.get("valid") is False:
                message = result.get("message")
                return str(message) if message is not None else "Award validation failed"
        return None

    def _emit(self, name: str, event: Any) -> None:
        if not self.config.dispatch:
            return
        if self.config.log_to_database and hasattr(event, "to_log"):
            self._log(event.to_log(self.now()))
        self._emitter.emit(name, event)

    def _log(self, data: dict[str, Any]) -> None:
        """``EventLog::fromEvent``, including its fall-backs for system events."""

        def first(*keys: str) -> Any:
            for key in keys:
                if data.get(key) is not None:
                    return data[key]
            return None

        now = self.now()
        self.store.insert(
            "event_logs",
            {
                "event_type": data["event_type"],
                "award_type": first("award_type") or "system",
                "awardable_type": first("recipient_type", "actor_type") or "system",
                "awardable_id": first("recipient_id", "actor_id") or 0,
                "award_id": first("award_id", "grant_id", "entity_id"),
                "achievement_slug": first("achievement_slug", "entity_slug"),
                "amount": data.get("amount"),
                "reason": data.get("reason"),
                "source": data.get("source"),
                "context": data,
                "occurred_at": now,
                "created_at": now,
            },
        )

    def _one(self, table: str, **where: Any) -> Row | None:
        rows = self.store.select(table, where)
        return rows[0] if rows else None

    def _create(self, table: str, values: Row) -> Row:
        now = self.now()
        return self.store.insert(table, {**values, "created_at": now, "updated_at": now})

    def _save(self, table: str, row: Row, changes: Row) -> Row:
        """Eloquent ``save()``: write only what changed, and touch ``updated_at`` only then."""
        current = normalize_row(table, row)
        incoming = normalize_row(table, {**row, **changes})
        dirty = {k: incoming[k] for k in changes if current.get(k) != incoming.get(k)}
        if dirty:
            dirty["updated_at"] = self.now()
            self.store.update(table, int(row["id"]), dirty)
        updated = self.store.get(table, int(row["id"]))
        assert updated is not None
        return updated

    def _upsert(self, table: str, match: Row, values: Row) -> tuple[Row, bool]:
        """Eloquent ``updateOrCreate``."""
        existing = self._one(table, **match)
        if existing is None:
            return self._create(table, {**match, **values}), True
        return self._save(table, existing, values), False

    # --- catalog setup -----------------------------------------------------

    def setup(
        self, a: str, with_: dict[str, Any] | None = None, actor: Subject | None = None
    ) -> Row:
        """``LFL::setup($a, $with)``: create or update a catalog entity, matched on its slug."""
        data = validate(a, dict(with_ or {}))
        kind = normalize_type(a)
        row, created = self._dispatch_setup(kind, data)
        self._emit(CATALOG_MUTATED, CatalogMutated(kind, row, created, actor))
        return row

    def _dispatch_setup(self, kind: str, w: dict[str, Any]) -> tuple[Row, bool]:
        def given(key: str, default: Any = None) -> Any:
            value = w.get(key)
            return default if value is None else value

        if kind == "gamed-metric":
            raw = str(w["slug"])
            return self._upsert(
                "gamed_metrics",
                {"slug": slug(raw)},
                {
                    "name": given("name", headline(raw)),
                    "description": w.get("description"),
                    "icon": w.get("icon"),
                    "active": given("active", True),
                },
            )
        if kind == "metric-level":
            metric = self._metric_or_fail(str(w["metric"]))
            level = int(w["level"])
            return self._upsert(
                "metric_levels",
                {"gamed_metric_id": metric["id"], "level": level},
                {
                    "xp_threshold": int(w["xp"]),
                    "name": given("name", f"Level {level}"),
                    "description": w.get("description"),
                },
            )
        if kind == "metric-level-group":
            raw = str(w["slug"])
            return self._upsert(
                "metric_level_groups",
                {"slug": slug(raw)},
                {"name": given("name", headline(raw)), "description": w.get("description")},
            )
        if kind == "metric-level-group-level":
            group = self._group_or_fail(str(w["group"]))
            level = int(w["level"])
            return self._upsert(
                "metric_level_group_levels",
                {"metric_level_group_id": group["id"], "level": level},
                {
                    "xp_threshold": int(w["xp"]),
                    "name": given("name", f"Level {level}"),
                    "description": w.get("description"),
                },
            )
        if kind == "metric-level-group-metric":
            group = self._group_or_fail(str(w["group"]))
            metric = self._metric_or_fail(str(w["metric"]))
            return self._upsert(
                "metric_level_group_metrics",
                {"metric_level_group_id": group["id"], "gamed_metric_id": metric["id"]},
                {"weight": float(given("weight", 1.0))},
            )
        if kind == "achievement":
            raw = str(w["slug"])
            return self._upsert(
                "achievements",
                {"slug": slug(raw)},
                {
                    "name": given("name", headline(raw)),
                    "description": w.get("description"),
                    "icon": w.get("icon"),
                    "awardable_type": w.get("for"),
                    "meta": w.get("metadata") or None,
                    "is_active": given("active", True),
                    "is_hidden": given("hidden", False),
                    "sort_order": int(given("order", 0)),
                },
            )
        # prize
        raw = str(w["slug"])
        return self._upsert(
            "prizes",
            {"slug": slug(raw)},
            {
                "name": given("name", headline(raw)),
                "description": w.get("description"),
                "type": given("type", "virtual"),
                "cost_in_points": float(given("cost", 0)),
                "inventory_quantity": w.get("inventory"),
                "meta": w.get("metadata") or None,
                "is_active": given("active", True),
                "sort_order": int(given("order", 0)),
            },
        )

    def _metric_or_fail(self, metric_slug: str) -> Row:
        metric = self.gamed_metric(metric_slug)
        if metric is None:
            raise FunLabError(f"GamedMetric '{metric_slug}' not found")
        return metric

    def _group_or_fail(self, group_slug: str) -> Row:
        group = self.metric_level_group(group_slug)
        if group is None:
            raise FunLabError(f"MetricLevelGroup '{group_slug}' not found")
        return group

    def attach_achievement(
        self,
        achievement: str,
        metric_level: tuple[str, int] | None = None,
        group_level: tuple[str, int] | None = None,
    ) -> None:
        """Grant ``achievement`` automatically when a metric or group level is reached.

        The ``$level->achievements()->attach()`` relation in laravel-fun-lab.
        Idempotent.
        """
        ach = self._one("achievements", slug=achievement)
        if ach is None:
            raise FunLabError(f"Achievement '{achievement}' not found")
        now = self.now()
        if metric_level is not None:
            metric = self.gamed_metric(metric_level[0])
            if metric is None:
                raise FunLabError(f"GamedMetric '{metric_level[0]}' not found")
            level = self._one(
                "metric_levels", gamed_metric_id=metric["id"], level=int(metric_level[1])
            )
            if level is None:
                raise FunLabError("Metric level not found")
            if (
                self._one(
                    "achievement_metric_levels",
                    achievement_id=ach["id"],
                    metric_level_id=level["id"],
                )
                is None
            ):
                self.store.insert(
                    "achievement_metric_levels",
                    {
                        "achievement_id": ach["id"],
                        "metric_level_id": level["id"],
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            return
        if group_level is None:
            raise FunLabError("attach_achievement needs metric_level or group_level")
        group = self.metric_level_group(group_level[0])
        if group is None:
            raise FunLabError(f"MetricLevelGroup '{group_level[0]}' not found")
        glevel = self._one(
            "metric_level_group_levels",
            metric_level_group_id=group["id"],
            level=int(group_level[1]),
        )
        if glevel is None:
            raise FunLabError("Group level not found")
        table = "achievement_metric_level_group_levels"
        if (
            self._one(table, achievement_id=ach["id"], metric_level_group_level_id=glevel["id"])
            is None
        ):
            self.store.insert(
                table,
                {
                    "achievement_id": ach["id"],
                    "metric_level_group_level_id": glevel["id"],
                    "created_at": now,
                    "updated_at": now,
                },
            )

    # --- catalog reads -----------------------------------------------------

    def gamed_metric(self, metric_slug: str) -> Row | None:
        return self._one("gamed_metrics", slug=metric_slug)

    def metric_level_group(self, group_slug: str) -> Row | None:
        return self._one("metric_level_groups", slug=group_slug)

    def gamed_metrics(self) -> list[Row]:
        return self.store.select("gamed_metrics")

    def metric_levels(self) -> list[Row]:
        return self.store.select("metric_levels")

    def metric_level_groups(self) -> list[Row]:
        return self.store.select("metric_level_groups")

    def achievements(self) -> list[Row]:
        return self.store.select("achievements")

    def prizes(self) -> list[Row]:
        return self.store.select("prizes")

    def remaining_inventory(self, prize: Row) -> int | None:
        if prize["inventory_quantity"] is None:
            return None
        return max(0, int(prize["inventory_quantity"]) - self._live_grants(prize))

    def _live_grants(self, prize: Row) -> int:
        return sum(
            1
            for g in self.store.select("prize_grants", {"prize_id": prize["id"]})
            if g["status"] != "cancelled"
        )

    def _is_available(self, prize: Row) -> bool:
        if prize["inventory_quantity"] is None:
            return True
        return self._live_grants(prize) < int(prize["inventory_quantity"])

    # --- profiles ----------------------------------------------------------

    def find_profile(self, subject: Subject) -> Row | None:
        return self._one("profiles", awardable_type=subject.type, awardable_id=subject.id)

    def profile(self, subject: Subject) -> Row:
        """``getProfile()``: the subject's profile, created (opted in) on first use."""
        existing = self.find_profile(subject)
        if existing is not None:
            return existing
        return self._create(
            "profiles",
            {"awardable_type": subject.type, "awardable_id": subject.id, "is_opted_in": True},
        )

    def is_opted_out(self, subject: Subject) -> bool:
        profile = self.find_profile(subject)
        return profile is not None and not profile["is_opted_in"]

    def opt_out(self, subject: Subject) -> bool:
        profile = self.find_profile(subject)
        if profile is None:
            self._create(
                "profiles",
                {"awardable_type": subject.type, "awardable_id": subject.id, "is_opted_in": False},
            )
        else:
            self._save("profiles", profile, {"is_opted_in": False})
        return True

    def opt_in(self, subject: Subject) -> bool:
        self._save("profiles", self.profile(subject), {"is_opted_in": True})
        return True

    def profile_metrics(self, profile: Row) -> list[Row]:
        return self.store.select("profile_metrics", {"profile_id": profile["id"]})

    def achievement_grants(self, profile: Row) -> list[Row]:
        return self.store.select("achievement_grants", {"profile_id": profile["id"]})

    def prize_grants(self, profile: Row) -> list[Row]:
        return self.store.select("prize_grants", {"profile_id": profile["id"]})

    def has_achievement(self, subject: Subject, achievement: str | Row) -> bool:
        profile = self.find_profile(subject)
        if profile is None:
            return False
        if isinstance(achievement, dict):
            achievement_id = achievement["id"]
        else:
            row = self._one("achievements", slug=achievement)
            if row is None:
                return False
            achievement_id = row["id"]
        return (
            self._one("achievement_grants", profile_id=profile["id"], achievement_id=achievement_id)
            is not None
        )

    def _subject_of(self, profile: Row) -> Subject:
        return Subject(type=str(profile["awardable_type"]), id=profile["awardable_id"])

    # --- awards ------------------------------------------------------------

    def award(self, metric_slug: str) -> AwardXpBuilder:
        """``LFL::award($metricSlug)``: the only way to give XP."""
        return AwardXpBuilder(self, metric_slug)

    def grant(self, entity_slug: str) -> GrantBuilder:
        """``LFL::grant($slug)``: an achievement, or failing that a prize."""
        return GrantBuilder(self, entity_slug)

    def _award_xp(
        self,
        subject: Subject,
        metric_slug: str,
        amount: int,
        reason: str | None,
        source: str | None,
        meta: dict[str, Any],
    ) -> Row:
        metric = self.gamed_metric(metric_slug)
        if metric is None:
            raise FunLabError(f"GamedMetric '{metric_slug}' not found.")
        if not metric["active"]:
            raise FunLabError(f"GamedMetric '{metric['slug']}' is not active.")
        if self.is_opted_out(subject):
            raise AwardRejected("Recipient has opted out of gamification.", "opted_out")

        profile = self.profile(subject)
        pm = self._one("profile_metrics", profile_id=profile["id"], gamed_metric_id=metric["id"])
        if pm is None:
            pm = self._create(
                "profile_metrics",
                {
                    "profile_id": profile["id"],
                    "gamed_metric_id": metric["id"],
                    "total_xp": 0,
                    "current_level": 1,
                },
            )
        now = self.now()
        self.store.increment("profile_metrics", int(pm["id"]), "total_xp", amount, now)
        self.store.increment("profiles", int(profile["id"]), "total_xp", amount, now)
        self.store.update(
            "profiles", int(profile["id"]), {"last_activity_at": now, "updated_at": now}
        )
        fresh = self.store.get("profile_metrics", int(pm["id"]))
        assert fresh is not None

        pm = self._check_progression(fresh, metric)
        self._check_group_progression(profile, metric)
        self._emit(XP_AWARDED, XpAwarded(pm, metric, subject, amount, reason, source, meta))
        return pm

    def _claim(
        self, table: str, row: Row, unlocked_for: Callable[[int], list[Row]]
    ) -> tuple[Row, list[Row]] | None:
        """The compare-and-set loop of ``claimLevels()``, for metrics and groups alike."""
        for _ in range(5):
            from_level = int(row["current_level"])
            unlocked = unlocked_for(from_level)
            if not unlocked:
                return None
            new_level = int(unlocked[-1]["level"])
            if self.store.claim_level(table, int(row["id"]), from_level, new_level, self.now()):
                return {**row, "current_level": new_level}, unlocked
            fresh = self.store.get(table, int(row["id"]))
            if fresh is None:
                return None
            row = fresh
        return None

    @staticmethod
    def _ordered(levels: list[Row]) -> list[Row]:
        return sorted(levels, key=lambda lv: (int(lv["level"]), int(lv["id"])))

    def _level_achievements(self, pivot: str, column: str, level_id: int) -> list[Row]:
        ids = {p["achievement_id"] for p in self.store.select(pivot, {column: level_id})}
        return [a for a in self.store.select("achievements", {"is_active": True}) if a["id"] in ids]

    def _check_progression(self, pm: Row, metric: Row) -> Row:
        levels = self._ordered(
            self.store.select("metric_levels", {"gamed_metric_id": metric["id"]})
        )
        total_xp = int(pm["total_xp"])

        claim = self._claim(
            "profile_metrics",
            pm,
            lambda from_level: [
                lv
                for lv in levels
                if total_xp >= int(lv["xp_threshold"]) and int(lv["level"]) > from_level
            ],
        )
        if claim is None:
            return pm
        pm, unlocked = claim
        profile = self.store.get("profiles", int(pm["profile_id"]))
        assert profile is not None
        subject = self._subject_of(profile)

        for level in unlocked:
            granted: list[Row] = []
            for ach in self._level_achievements(
                "achievement_metric_levels", "metric_level_id", int(level["id"])
            ):
                if ach["awardable_type"] is not None and ach["awardable_type"] != subject.type:
                    continue
                if self.has_achievement(subject, ach):
                    continue
                result = (
                    self.grant(str(ach["slug"]))
                    .to(subject)
                    .because(f"Reached level {level['level']}: {level['name']}")
                    .from_("metric-level-progression")
                    .with_meta(
                        {
                            "metric_level_id": level["id"],
                            "gamed_metric_id": metric["id"],
                            "level": level["level"],
                        }
                    )
                    .save()
                )
                if result.success:
                    granted.append(ach)
            self._emit(
                METRIC_LEVEL_REACHED,
                MetricLevelReached(profile, pm, metric, level, subject, granted, total_xp),
            )
        return pm

    def _check_group_progression(self, profile: Row, metric: Row) -> None:
        group_ids = {
            gm["metric_level_group_id"]
            for gm in self.store.select(
                "metric_level_group_metrics", {"gamed_metric_id": metric["id"]}
            )
        }
        for group in self.metric_level_groups():
            if group["id"] not in group_ids:
                continue
            pmg = self._one(
                "profile_metric_groups", profile_id=profile["id"], metric_level_group_id=group["id"]
            )
            if pmg is None:
                pmg = self._create(
                    "profile_metric_groups",
                    {
                        "profile_id": profile["id"],
                        "metric_level_group_id": group["id"],
                        "current_level": 1,
                    },
                )
            self._check_group_level(pmg, group, profile)

    def _check_group_level(self, pmg: Row, group: Row, profile: Row) -> None:
        subject = self._subject_of(profile)
        total_xp = self.group_total_xp(subject, group)
        levels = self._ordered(
            self.store.select("metric_level_group_levels", {"metric_level_group_id": group["id"]})
        )
        claim = self._claim(
            "profile_metric_groups",
            pmg,
            lambda from_level: [
                lv
                for lv in levels
                if total_xp >= int(lv["xp_threshold"]) and int(lv["level"]) > from_level
            ],
        )
        if claim is None:
            return
        for level in claim[1]:
            pivot = "achievement_metric_level_group_levels"
            for ach in self._level_achievements(
                pivot, "metric_level_group_level_id", int(level["id"])
            ):
                if ach["awardable_type"] is not None and ach["awardable_type"] != subject.type:
                    continue
                if self.has_achievement(subject, ach):
                    continue
                (
                    self.grant(str(ach["slug"]))
                    .to(subject)
                    .because(f"Reached level {level['level']}: {level['name']}")
                    .from_("metric-level-group-progression")
                    .with_meta(
                        {
                            "metric_level_group_level_id": level["id"],
                            "metric_level_group_id": group["id"],
                            "level": level["level"],
                        }
                    )
                    .save()
                )

    def _grant_achievement(
        self,
        subject: Subject,
        entity_slug: str,
        reason: str | None,
        source: str | None,
        meta: dict[str, Any],
    ) -> AwardResult:
        if self.is_opted_out(subject):
            return AwardResult.failure("Recipient has opted out of gamification")
        ach = self._one("achievements", slug=entity_slug)
        if ach is None:
            return AwardResult.failure(f"Achievement '{entity_slug}' not found")
        if not ach["is_active"]:
            return AwardResult.failure(f"Achievement '{entity_slug}' is not active")
        profile = self.profile(subject)
        if (
            self._one("achievement_grants", profile_id=profile["id"], achievement_id=ach["id"])
            is not None
        ):
            return AwardResult.failure(f"Achievement '{entity_slug}' already granted")
        grant = self._create(
            "achievement_grants",
            {
                "profile_id": profile["id"],
                "achievement_id": ach["id"],
                "reason": reason,
                "source": source,
                "meta": meta or None,
                "granted_at": self.now(),
            },
        )
        self.store.increment("profiles", int(profile["id"]), "achievement_count", 1, self.now())
        result = AwardResult.ok(grant)
        self._emit(ACHIEVEMENT_UNLOCKED, AchievementUnlocked(subject, ach, grant, reason, source))
        self._emit(AWARD_GRANTED, AwardGranted(result, "achievement", subject, grant))
        return result

    def _grant_prize(
        self,
        subject: Subject,
        entity_slug: str,
        reason: str | None,
        source: str | None,
        meta: dict[str, Any],
    ) -> AwardResult:
        if self.is_opted_out(subject):
            return AwardResult.failure("Recipient has opted out of gamification")
        prize = self._one("prizes", slug=entity_slug)
        if prize is None:
            return AwardResult.failure(f"Prize '{entity_slug}' not found")
        if not prize["is_active"]:
            return AwardResult.failure(f"Prize '{entity_slug}' is not active")
        if not self._is_available(prize):
            return AwardResult.failure(f"Prize '{entity_slug}' is out of inventory")
        profile = self.profile(subject)
        grant = self._create(
            "prize_grants",
            {
                "profile_id": profile["id"],
                "prize_id": prize["id"],
                "reason": reason,
                "source": source,
                "meta": meta or None,
                "status": "granted",
                "granted_at": self.now(),
            },
        )
        self.store.increment("profiles", int(profile["id"]), "prize_count", 1, self.now())
        result = AwardResult.ok(grant)
        self._emit(PRIZE_AWARDED, PrizeAwarded(subject, grant, prize, reason, source, meta))
        self._emit(AWARD_GRANTED, AwardGranted(result, "prize", subject, grant))
        return result

    def _prize_grant_or_fail(self, grant_id: int) -> Row:
        grant = self.store.get("prize_grants", grant_id)
        if grant is None:
            raise FunLabError(f"Prize grant {grant_id} not found")
        return grant

    def claim_prize(self, grant_id: int) -> Row:
        """``PrizeGrant::claim()``."""
        grant = self._prize_grant_or_fail(grant_id)
        return self._save("prize_grants", grant, {"status": "claimed", "claimed_at": self.now()})

    def fulfill_prize(self, grant_id: int) -> Row:
        """``PrizeGrant::fulfill()``."""
        grant = self._prize_grant_or_fail(grant_id)
        return self._save(
            "prize_grants", grant, {"status": "fulfilled", "fulfilled_at": self.now()}
        )

    # --- levels ------------------------------------------------------------

    def group_total_xp(self, subject: Subject, group: Row | str) -> int:
        """Weighted group XP: each metric's XP times its weight, TRUNCATED, then summed."""
        g = self.metric_level_group(group) if isinstance(group, str) else group
        if g is None:
            return 0
        profile = self.find_profile(subject)
        if profile is None:
            return 0
        return self._weighted_xp(int(profile["id"]), g)

    def _weighted_xp(self, profile_id: int, group: Row) -> int:
        total = 0
        for gm in self.store.select(
            "metric_level_group_metrics", {"metric_level_group_id": group["id"]}
        ):
            pm = self._one(
                "profile_metrics", profile_id=profile_id, gamed_metric_id=gm["gamed_metric_id"]
            )
            if pm is not None:
                total += int(int(pm["total_xp"]) * float(gm["weight"]))
        return total

    def has_level(
        self, subject: Subject, level: int, metric: str | None = None, group: str | None = None
    ) -> bool:
        """``LFL::hasLevel()``. Creates the subject's profile, as ``getProfile()`` does."""
        if metric is None and group is None:
            raise FunLabError("Either 'metric' or 'group' must be specified for hasLevel()")
        if metric is not None and group is not None:
            raise FunLabError("Only one of 'metric' or 'group' can be specified for hasLevel()")
        profile = self.profile(subject)
        if metric is not None:
            m = self.gamed_metric(metric)
            if m is None:
                return False
            pm = self._one("profile_metrics", profile_id=profile["id"], gamed_metric_id=m["id"])
            if pm is None:
                return False
            if int(pm["current_level"]) >= level:
                return True
            row = self._one("metric_levels", gamed_metric_id=m["id"], level=level)
            if row is None:
                return int(pm["current_level"]) >= level
            return int(pm["total_xp"]) >= int(row["xp_threshold"])
        assert group is not None
        g = self.metric_level_group(group)
        if g is None:
            return False
        total = self._weighted_xp(int(profile["id"]), g)
        glevel = self._one("metric_level_group_levels", metric_level_group_id=g["id"], level=level)
        if glevel is None:
            return False
        return total >= int(glevel["xp_threshold"])

    @staticmethod
    def _progress(xp: int, floor: int, next_threshold: int | None) -> float:
        if next_threshold is None:
            return 100.0
        required = next_threshold - floor
        if required <= 0:
            return 100.0
        # Clamped at 0 too: a profile is level 1 before reaching level 1's own threshold.
        return max(0.0, min(100.0, ((xp - floor) / required) * 100))

    def level_info(self, subject: Subject, metric: str) -> dict[str, Any]:
        """Current level, XP, next threshold and progress (from the level's floor) in a metric."""
        m = self.gamed_metric(metric)
        profile = self.find_profile(subject)
        pm = None
        if m is not None and profile is not None:
            pm = self._one("profile_metrics", profile_id=profile["id"], gamed_metric_id=m["id"])
        current = int(pm["current_level"]) if pm is not None else 1
        next_threshold = None
        if m is not None:
            levels = self._ordered(self.store.select("metric_levels", {"gamed_metric_id": m["id"]}))
            above = [lv for lv in levels if int(lv["level"]) > current]
            next_threshold = int(above[0]["xp_threshold"]) if above else None
        if m is None or pm is None:
            progress = 0.0
        else:
            floor_row = self._one("metric_levels", gamed_metric_id=m["id"], level=current)
            floor = int(floor_row["xp_threshold"]) if floor_row is not None else 0
            progress = self._progress(int(pm["total_xp"]), floor, next_threshold)
        return {
            "current_level": current,
            "total_xp": int(pm["total_xp"]) if pm is not None else 0,
            "next_level_threshold": next_threshold,
            "progress_percentage": progress,
        }

    def group_level_info(self, subject: Subject, group: str) -> dict[str, Any]:
        """``MetricLevelGroupService::getLevelInfo()``."""
        g = self.metric_level_group(group)
        if g is None:
            return {
                "current_level": 1,
                "total_xp": 0,
                "next_level_threshold": None,
                "progress_percentage": 0.0,
            }
        total = self.group_total_xp(subject, g)
        levels = self._ordered(
            self.store.select("metric_level_group_levels", {"metric_level_group_id": g["id"]})
        )
        profile = self.find_profile(subject)
        current = 1
        if profile is not None:
            pmg = self._one(
                "profile_metric_groups", profile_id=profile["id"], metric_level_group_id=g["id"]
            )
            if pmg is not None:
                current = int(pmg["current_level"])
            else:
                for lv in levels:
                    if total >= int(lv["xp_threshold"]):
                        current = int(lv["level"])
                    else:
                        break
        above = [lv for lv in levels if int(lv["level"]) > current]
        next_threshold = int(above[0]["xp_threshold"]) if above else None
        floor_row = next((lv for lv in levels if int(lv["level"]) == current), None)
        floor = int(floor_row["xp_threshold"]) if floor_row is not None else 0
        return {
            "current_level": current,
            "total_xp": total,
            "next_level_threshold": next_threshold,
            "progress_percentage": self._progress(total, floor, next_threshold),
        }

    # --- queries -----------------------------------------------------------

    def leaderboard(self) -> LeaderboardBuilder:
        from .leaderboard import LeaderboardBuilder

        return LeaderboardBuilder(self)

    def analytics(self) -> AnalyticsBuilder:
        from .analytics import AnalyticsBuilder

        return AnalyticsBuilder(self)


@dataclass
class _Fluent:
    lab: FunLab
    entity: str
    recipient: Subject | None = None
    reason: str | None = None
    source: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to(self, recipient: Subject) -> Any:
        self.recipient = recipient
        return self

    def because(self, reason: str) -> Any:
        self.reason = reason
        return self

    def for_(self, reason: str) -> Any:
        return self.because(reason)

    def from_(self, source: str) -> Any:
        self.source = source
        return self

    def with_meta(self, meta: dict[str, Any]) -> Any:
        self.meta = dict(meta)
        return self


@dataclass
class AwardXpBuilder(_Fluent):
    """``LFL::award($metric)->to($u)->amount($n)->because(...)->from(...)->withMeta(...)->save()``."""

    _amount: int = 0

    def amount(self, amount: int) -> AwardXpBuilder:
        self._amount = int(amount)
        return self

    def save(self) -> Row:
        if self.recipient is None:
            raise FunLabError("Recipient is required. Use ->to($user) to set the recipient.")
        if self._amount <= 0:
            raise FunLabError(
                "Amount must be greater than 0. Use ->amount(50) to set the XP amount."
            )
        cap = int(self.lab.config.max_points_per_action)
        if cap > 0 and self._amount > cap:
            raise AwardRejected(
                f"Award amount {self._amount} exceeds the configured per-action cap of {cap}.",
                "cap_exceeded",
            )
        refused = self.lab._validate(
            self.recipient, "points", self._amount, self.reason, self.source, self.meta
        )
        if refused is not None:
            raise AwardRejected(refused, "pipeline_rejected")
        return self.lab._award_xp(
            self.recipient, self.entity, self._amount, self.reason, self.source, self.meta
        )

    grant = save


@dataclass
class GrantBuilder(_Fluent):
    """``LFL::grant($slug)``: resolved to an achievement first, then a prize."""

    _kind: str | None = None

    def __post_init__(self) -> None:
        self._kind = self._detect()

    def _detect(self) -> str | None:
        if self.lab._one("achievements", slug=self.entity) is not None:
            return "achievement"
        if self.lab._one("prizes", slug=self.entity) is not None:
            return "prize"
        return None

    def save(self) -> AwardResult:
        if self.recipient is None:
            raise FunLabError("Recipient is required. Use ->to($user) to set the recipient.")
        if self._kind is None:
            self._kind = self._detect()
        if self._kind is None:
            return AwardResult.failure(f"No Achievement or Prize found with slug '{self.entity}'")
        refused = self.lab._validate(
            self.recipient, self._kind, 0, self.reason, self.source, self.meta
        )
        if refused is not None:
            return AwardResult.failure(refused)
        if self._kind == "achievement":
            return self.lab._grant_achievement(
                self.recipient, self.entity, self.reason, self.source, self.meta
            )
        return self.lab._grant_prize(
            self.recipient, self.entity, self.reason, self.source, self.meta
        )

    grant = save


_ = SCHEMA  # the table layout the engine writes; see schema.py
