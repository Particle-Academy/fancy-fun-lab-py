"""The ``Store`` contract, on both stores: what the shared tables cannot express."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest

from fancy_fun_lab import FunLab, InMemoryStore, SqliteStore, Store, Subject

AT = datetime(2026, 11, 18, 12, 0, 0)

FACTORIES: dict[str, Callable[[], Store]] = {
    "memory": InMemoryStore,
    "sqlite": lambda: SqliteStore(":memory:"),
}


@pytest.fixture(params=list(FACTORIES))
def store(request: pytest.FixtureRequest) -> Iterator[Store]:
    s = FACTORIES[request.param]()
    yield s
    close = getattr(s, "close", None)
    if close is not None:
        close()


def _metric_row(store: Store) -> int:
    row = store.insert(
        "profile_metrics",
        {"profile_id": 1, "gamed_metric_id": 1, "created_at": AT, "updated_at": AT},
    )
    return int(row["id"])


def test_insert_assigns_ids_from_one_and_fills_defaults(store: Store) -> None:
    first = store.insert(
        "profiles",
        {"awardable_type": "user", "awardable_id": 1, "created_at": AT, "updated_at": AT},
    )
    second = store.insert(
        "profiles",
        {"awardable_type": "user", "awardable_id": 2, "created_at": AT, "updated_at": AT},
    )
    assert (first["id"], second["id"]) == (1, 2)
    assert first["is_opted_in"] is True
    assert first["total_xp"] == 0
    assert first["created_at"] == AT


def test_select_filters_by_equality_and_orders_by_id(store: Store) -> None:
    for i in (3, 1, 2):
        store.insert(
            "profiles", {"awardable_type": "user", "awardable_id": i, "is_opted_in": i != 2}
        )
    assert [r["awardable_id"] for r in store.select("profiles")] == [3, 1, 2]
    assert [r["awardable_id"] for r in store.select("profiles", {"is_opted_in": True})] == [3, 1]
    assert store.select("profiles", {"last_activity_at": None})


def test_json_and_decimal_columns_round_trip(store: Store) -> None:
    row = store.insert(
        "prizes",
        {
            "slug": "x",
            "name": "X",
            "type": "virtual",
            "cost_in_points": 0.335,
            "meta": {"a": [1, 2]},
        },
    )
    again = store.get("prizes", int(row["id"]))
    assert again is not None
    assert again["meta"] == {"a": [1, 2]}
    # decimal:2, rounded half up
    assert again["cost_in_points"] == 0.34


def test_claim_level_is_a_compare_and_set(store: Store) -> None:
    pm = _metric_row(store)
    assert store.claim_level("profile_metrics", pm, 1, 3, AT) is True
    assert store.claim_level("profile_metrics", pm, 1, 4, AT) is False
    row = store.get("profile_metrics", pm)
    assert row is not None
    assert row["current_level"] == 3


def test_claim_level_has_exactly_one_winner_under_a_race(store: Store) -> None:
    pm = _metric_row(store)
    wins: list[bool] = []
    start = threading.Barrier(16)

    def contender() -> None:
        start.wait()
        wins.append(store.claim_level("profile_metrics", pm, 1, 2, AT))

    threads = [threading.Thread(target=contender) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert wins.count(True) == 1
    assert len(wins) == 16


def test_increment_is_atomic_under_a_race(store: Store) -> None:
    pm = _metric_row(store)
    threads = [
        threading.Thread(target=lambda: store.increment("profile_metrics", pm, "total_xp", 1, AT))
        for _ in range(50)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    row = store.get("profile_metrics", pm)
    assert row is not None
    assert row["total_xp"] == 50


def test_a_level_is_announced_once_when_awards_race(store: Store) -> None:
    lab = FunLab(store=store, clock=lambda: AT)
    lab.setup("gamed-metric", {"slug": "combat"})
    lab.setup("metric-level", {"metric": "combat", "level": 2, "xp": 10})
    lab.setup("achievement", {"slug": "two"})
    lab.attach_achievement("two", metric_level=("combat", 2))
    ada = Subject("user", 1)
    lab.award("combat").to(ada).amount(1).save()

    reached: list[int] = []
    lab.on("metric.level-reached", lambda e: reached.append(e.level["level"]))
    start = threading.Barrier(8)

    def award() -> None:
        start.wait()
        lab.award("combat").to(ada).amount(10).save()

    threads = [threading.Thread(target=award) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert reached == [2]
    assert len(lab.achievement_grants(lab.profile(ada))) == 1


def test_sqlite_writes_laravels_layout(tmp_path: Path) -> None:
    path = tmp_path / "lfl.sqlite"
    store = SqliteStore(path)
    lab = FunLab(store=store, clock=lambda: AT)
    lab.setup("gamed-metric", {"slug": "combat"})
    lab.award("combat").to(Subject("user", 7)).amount(5).save()
    store.close()

    db = sqlite3.connect(path)
    try:
        tables = {r[0] for r in db.execute("select name from sqlite_master where type = 'table'")}
        assert {"lfl_profiles", "lfl_event_logs", "lfl_gamed_metrics"} <= tables
        active, created = db.execute("select active, created_at from lfl_gamed_metrics").fetchone()
        assert (active, created) == (1, "2026-11-18 12:00:00")
        context = db.execute(
            "select context from lfl_event_logs where event_type = 'xp_awarded'"
        ).fetchone()[0]
        assert '"meta":[]' in context
    finally:
        db.close()

    reopened = SqliteStore(path)
    try:
        assert FunLab(store=reopened).level_info(Subject("user", 7), "combat")["total_xp"] == 5
    finally:
        reopened.close()


def test_a_table_prefix_is_honoured() -> None:
    store = SqliteStore(":memory:", prefix="game_")
    try:
        FunLab(store=store, clock=lambda: AT).setup("gamed-metric", {"slug": "combat"})
        assert store.select("gamed_metrics")[0]["slug"] == "combat"
    finally:
        store.close()
