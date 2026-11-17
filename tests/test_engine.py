"""Engine behaviour the shared tables cannot express: the emitter, dispatch off,
the validation pipeline and Python-specific type guards."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from fancy_fun_lab import (
    AwardRejected,
    FunLab,
    FunLabConfig,
    FunLabError,
    PeriodLeaderboardUnavailable,
    Subject,
    __version__,
    headline,
    slug,
)

AT = datetime(2026, 11, 18, 12, 0, 0)
ADA = Subject("user", 1)


def _lab(**config: Any) -> FunLab:
    lab = FunLab(clock=lambda: AT, config=FunLabConfig(**config))
    lab.setup("gamed-metric", {"slug": "combat"})
    lab.setup("metric-level", {"metric": "combat", "level": 2, "xp": 10})
    return lab


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_listeners_by_name_and_wildcard_and_unsubscribe() -> None:
    lab = _lab()
    named: list[int] = []
    every: list[str] = []
    off = lab.on("xp.awarded", lambda e: named.append(e.amount))
    lab.on("*", lambda name, e: every.append(name))
    lab.award("combat").to(ADA).amount(12).save()
    off()
    lab.award("combat").to(ADA).amount(1).save()
    assert named == [12]
    assert every == ["metric.level-reached", "xp.awarded", "xp.awarded"]


def test_dispatch_off_emits_nothing_logs_nothing_and_still_levels() -> None:
    lab = _lab(dispatch=False)
    seen: list[str] = []
    lab.on("*", lambda name, e: seen.append(name))
    pm = lab.award("combat").to(ADA).amount(12).save()
    assert seen == []
    assert pm["current_level"] == 2
    assert lab.analytics().count() == 0
    with pytest.raises(PeriodLeaderboardUnavailable):
        lab.leaderboard().period("weekly").get()


def test_the_validation_pipeline_can_refuse_awards_and_grants() -> None:
    lab = _lab()
    lab.setup("achievement", {"slug": "hello"})
    calls: list[tuple[str, int]] = []

    def no_bots(subject: Subject, award_type: str, amount: int, *rest: Any) -> Any:
        calls.append((award_type, amount))
        return {"valid": False, "message": "no bots"} if subject.id == 99 else None

    lab.add_validation_step(no_bots)
    bot = Subject("user", 99)
    with pytest.raises(AwardRejected) as refused:
        lab.award("combat").to(bot).amount(5).save()
    assert refused.value.kind == "pipeline_rejected"
    assert str(refused.value) == "no bots"
    result = lab.grant("hello").to(bot).save()
    assert (result.success, result.message) == (False, "no bots")
    assert lab.award("combat").to(ADA).amount(5).save()["total_xp"] == 5
    assert calls == [("points", 5), ("achievement", 0), ("points", 5)]


def test_a_recipient_is_required() -> None:
    lab = _lab()
    with pytest.raises(FunLabError, match="Recipient is required"):
        lab.award("combat").amount(5).save()
    with pytest.raises(FunLabError, match="Recipient is required"):
        lab.grant("combat").save()


def test_setup_refuses_a_bool_where_an_int_is_required() -> None:
    """Python-specific: ``True`` is an ``int`` here and is not in PHP."""
    lab = _lab()
    with pytest.raises(FunLabError, match="'level' must be int, bool given"):
        lab.setup("metric-level", {"metric": "combat", "level": True, "xp": 1})


def test_an_aware_clock_is_read_as_utc_seconds() -> None:
    later = datetime(2026, 11, 18, 14, 0, 0, 123456, tzinfo=timezone(timedelta(hours=2)))
    lab = FunLab(clock=lambda: later)
    assert lab.now() == AT
    assert lab.now().tzinfo is None
    assert FunLab().now() <= datetime.now(UTC).replace(tzinfo=None)


def test_strings_are_exported() -> None:
    assert slug("Combat XP") == "combat-xp"
    assert headline("Combat XP") == "Combat Xp"
