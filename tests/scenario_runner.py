"""Run one ``fun-lab/*`` conformance scenario through THIS engine.

The Python mirror of ``laravel-fun-lab/tests/Conformance/ScenarioRunner.php``,
the adapter the goldens were exported with. It must return the identical
document, so it is written against the same rules:

- subjects are named (``"ada": "user"``); awardable ids are 1, 2, 3 in the order
  they are listed, and awardable types are reported by those names;
- every step returns ``{"result", "events"}``; a refusal is a result, never an
  exception: ``{"error": "invalid", "message"}`` or
  ``{"error": "rejected", "kind", "message"}``;
- keyed results (groups, the ``by*`` breakdowns) are lists sorted by key,
  because PHP encodes an empty map as ``[]``.

It drives only the public API, so a passing row is a claim about what a
consumer sees.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fancy_fun_lab import (
    AwardRejected,
    FunLab,
    FunLabConfig,
    FunLabError,
    Store,
    Subject,
    resources,
)
from fancy_fun_lab.clock import parse_datetime


class _Clock:
    def __init__(self, at: str) -> None:
        self.now: datetime = parse_datetime(at)

    def __call__(self) -> datetime:
        return self.now


def run_scenario(spec: dict[str, Any], store_factory: Callable[[], Store]) -> dict[str, Any]:
    store = store_factory()
    try:
        return _run(spec, store)
    finally:
        close = getattr(store, "close", None)
        if close is not None:
            close()


def _run(spec: dict[str, Any], store: Store) -> dict[str, Any]:
    clock = _Clock(str(spec["clock"]))
    config = spec.get("config") or {}
    lab = FunLab(
        store=store,
        clock=clock,
        config=FunLabConfig(
            max_points_per_action=int(config.get("max_points_per_action", 10000)),
            log_to_database=bool(config.get("log_to_database", True)),
            dispatch=bool(config.get("dispatch", True)),
        ),
    )

    subjects: dict[str, Subject] = {}
    for index, (name, kind) in enumerate((spec.get("subjects") or {}).items(), start=1):
        if kind not in ("user", "team"):
            raise ValueError(f"unknown subject type {kind}")
        subjects[name] = Subject(type=kind, id=index)

    events: list[dict[str, Any]] = []
    lab.on("*", lambda name, event: events.append(_capture(name, event)))

    out = []
    for step in spec["steps"]:
        events.clear()
        result = _step(lab, clock, subjects, step)
        out.append({"result": result, "events": [e for e in events if e]})
    return {"steps": out}


def _capture(name: str, e: Any) -> dict[str, Any]:
    """The same fields the PHP adapter records, by the event's stable name."""
    if name == "xp.awarded":
        return {
            "event": name,
            "metric": e.gamed_metric["slug"],
            "amount": e.amount,
            "total_xp": e.profile_metric["total_xp"],
        }
    if name == "metric.level-reached":
        return {
            "event": name,
            "metric": e.gamed_metric["slug"],
            "level": e.level["level"],
            "achievements": [a["slug"] for a in e.achievements],
            "total_xp": e.total_xp,
        }
    if name == "achievement.unlocked":
        return {"event": name, "achievement": e.achievement["slug"], "source": e.source}
    if name == "prize.awarded":
        return {"event": name, "prize": e.prize["slug"], "source": e.source}
    if name == "award.granted":
        return {"event": name, "type": e.type}
    if name == "catalog.mutated":
        return {"event": name, "entity": e.entity_type, "created": e.was_created}
    return {}


def _guard(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except AwardRejected as e:
        return {"error": "rejected", "kind": e.kind, "message": str(e)}
    except FunLabError as e:
        return {"error": "invalid", "message": str(e)}


def _step(lab: FunLab, clock: _Clock, subjects: dict[str, Subject], s: dict[str, Any]) -> Any:
    op = s["op"]

    def who(key: str) -> Subject:
        return subjects[str(s[key])]

    if op == "clock":
        clock.now = parse_datetime(str(s["at"]))
        return None
    if op == "setup":
        return _guard(lambda: {"id": lab.setup(str(s["a"]), s.get("with") or {})["id"]})
    if op == "attach":
        return _guard(lambda: _attach(lab, s))
    if op == "award":
        return _guard(lambda: _award(lab, who("to"), s))
    if op == "grant":
        return _guard(lambda: _grant(lab, who("to"), s))
    if op == "optOut":
        return lab.opt_out(who("who"))
    if op == "optIn":
        return lab.opt_in(who("who"))
    if op == "redeem":
        return _guard(lambda: _redeem(lab, s))
    if op == "hasLevel":
        return _guard(
            lambda: lab.has_level(
                who("who"), int(s["level"]), metric=s.get("metric"), group=s.get("group")
            )
        )
    if op == "levelInfo":
        if "group" in s:
            return lab.group_level_info(who("who"), str(s["group"]))
        return lab.level_info(who("who"), str(s["metric"]))
    if op == "leaderboard":
        return _guard(lambda: _leaderboard(lab, s))
    if op == "profile":
        return _profile(lab, who("who"))
    if op == "catalog":
        return {
            "metrics": [resources.gamed_metric(m) for m in lab.gamed_metrics()],
            "levels": [resources.metric_level(lab, lv) for lv in lab.metric_levels()],
            "achievements": [resources.achievement(a) for a in lab.achievements()],
            "prizes": [resources.prize(lab, p) for p in lab.prizes()],
        }
    if op == "analytics":
        return _guard(lambda: _analytics(lab, subjects, s))
    raise ValueError(f"unknown op {op}")


def _attach(lab: FunLab, s: dict[str, Any]) -> bool:
    if "metricLevel" in s:
        ml = s["metricLevel"]
        lab.attach_achievement(
            str(s["achievement"]), metric_level=(str(ml["metric"]), int(ml["level"]))
        )
    else:
        gl = s["groupLevel"]
        lab.attach_achievement(
            str(s["achievement"]), group_level=(str(gl["group"]), int(gl["level"]))
        )
    return True


def _award(lab: FunLab, to: Subject, s: dict[str, Any]) -> dict[str, Any]:
    b = lab.award(str(s["metric"])).to(to).amount(int(s["amount"]))
    if "reason" in s:
        b.because(str(s["reason"]))
    if "source" in s:
        b.from_(str(s["source"]))
    if "meta" in s:
        b.with_meta(dict(s["meta"]))
    pm = b.save()
    return {"total_xp": pm["total_xp"], "current_level": pm["current_level"]}


def _grant(lab: FunLab, to: Subject, s: dict[str, Any]) -> dict[str, Any]:
    b = lab.grant(str(s["slug"])).to(to)
    if "reason" in s:
        b.because(str(s["reason"]))
    if "source" in s:
        b.from_(str(s["source"]))
    if "meta" in s:
        b.with_meta(dict(s["meta"]))
    result = b.save()
    return {"success": result.success, "message": result.message}


def _redeem(lab: FunLab, s: dict[str, Any]) -> dict[str, Any]:
    grant_id = int(s["grant"])
    grant = lab.claim_prize(grant_id) if s["to"] == "claimed" else lab.fulfill_prize(grant_id)
    return resources.prize_grant(lab, grant)


def _leaderboard(lab: FunLab, s: dict[str, Any]) -> dict[str, Any]:
    board = lab.leaderboard()
    if "for" in s:
        board.for_(str(s["for"]))
    if "by" in s:
        board.by(str(s["by"]))
    if "period" in s:
        board.period(s["period"])
    if "metric" in s:
        board.metric(str(s["metric"]))
    if "excludeOptedOut" in s:
        board.exclude_opted_out(bool(s["excludeOptedOut"]))
    if "page" in s:
        page = board.per_page(int(s.get("perPage", 15))).page(int(s["page"])).paginate()
        return {
            "total": page.total,
            "entries": [resources.leaderboard_entry(e) for e in page.items],
        }
    rows = board.take(int(s["take"])) if "take" in s else board.get()
    return {"entries": [resources.leaderboard_entry(e) for e in rows]}


def _profile(lab: FunLab, subject: Subject) -> dict[str, Any]:
    profile = lab.find_profile(subject)
    if profile is None:
        return {"profile": None}
    return {
        "profile": resources.profile(profile),
        "metrics": [resources.profile_metric(lab, m) for m in lab.profile_metrics(profile)],
        "achievements": [
            resources.achievement_grant(lab, g) for g in lab.achievement_grants(profile)
        ],
        "prizes": [resources.prize_grant(lab, g) for g in lab.prize_grants(profile)],
        "groups": [
            {"group": g["slug"], **lab.group_level_info(subject, str(g["slug"]))}
            for g in lab.metric_level_groups()
        ],
    }


def _keyed(by_key: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"key": key, **by_key[key]} for key in sorted(by_key)]


def _analytics(lab: FunLab, subjects: dict[str, Subject], s: dict[str, Any]) -> Any:
    q = lab.analytics()
    if "byType" in s:
        q.by_type(str(s["byType"]))
    if "forType" in s:
        q.for_awardable_type(str(s["forType"]))
    if "forSubject" in s:
        q.for_awardable(subjects[str(s["forSubject"])])
    if "source" in s:
        q.from_source(str(s["source"]))
    if "achievement" in s:
        q.for_achievement(str(s["achievement"]))
    if "period" in s:
        q.period(s["period"])
    if "since" in s:
        q.since(str(s["since"]))
    if "until" in s:
        q.until(str(s["until"]))

    agg = s["agg"]
    if agg == "count":
        return q.count()
    if agg == "total":
        return q.total()
    if agg == "average":
        return q.average()
    if agg == "min":
        return q.min()
    if agg == "max":
        return q.max()
    if agg == "activeUsers":
        return q.active_users()
    if agg == "completionRate":
        return q.achievement_completion_rate()
    if agg == "timeSeries":
        return q.time_series(str(s.get("interval", "day")))
    if agg == "byAwardType":
        return _keyed(q.by_award_type())
    if agg == "byAwardableType":
        return _keyed(q.by_awardable_type())
    if agg == "bySource":
        return _keyed(q.by_source())
    if agg == "export":
        return q.export(int(s["limit"]) if "limit" in s else None)
    raise ValueError(f"unknown agg {agg}")
