"""Persistence: the ``Store`` contract and the in-memory reference store.

The engine owns no persistence. It reads and writes rows through this narrow
contract, and every query (leaderboards, analytics) is computed by the engine
over the rows a store returns, so two stores that keep the contract give the
same answers by construction.

Two primitives carry correctness, and they are the store's job, not the
engine's:

- ``claim_level`` is a compare-and-set: it moves ``current_level`` from
  ``from_level`` to ``to_level`` only if nobody moved it first. This is what
  makes a level (and its achievements) claimed exactly once however many
  requests cross the threshold together.
- ``increment`` is atomic.

A row is a ``dict`` of plain values: ``int``, ``float``, ``str``, ``bool``,
``None``, JSON values (``dict`` / ``list``) and naive-UTC ``datetime``.
"""

from __future__ import annotations

import copy
import threading
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from .schema import SCHEMA, two_places

Row = dict[str, Any]


@runtime_checkable
class Store(Protocol):
    """What the engine needs from persistence. Tables are named as in ``schema.SCHEMA``."""

    def insert(self, table: str, row: Row) -> Row:
        """Insert a row; return it complete (``id`` assigned 1, 2, 3, ..., defaults filled)."""
        ...

    def get(self, table: str, id: int) -> Row | None: ...

    def select(self, table: str, where: Row | None = None) -> list[Row]:
        """Rows whose columns equal every value in ``where``, ordered by ``id``."""
        ...

    def update(self, table: str, id: int, changes: Row) -> None: ...

    def increment(self, table: str, id: int, column: str, amount: int, touch: datetime) -> None:
        """Atomically add ``amount`` to ``column`` and set ``updated_at`` to ``touch``."""
        ...

    def claim_level(
        self, table: str, id: int, from_level: int, to_level: int, touch: datetime
    ) -> bool:
        """Compare-and-set ``current_level``: ``from_level`` -> ``to_level``, or False."""
        ...


def normalize_row(table: str, row: Row) -> Row:
    """Fill defaults and apply each column's cast, as a Laravel model read back would."""
    out: Row = {}
    for column, (kind, default) in SCHEMA[table].items():
        value = row.get(column, default)
        if value is not None:
            if kind == "bool":
                value = bool(value)
            elif kind == "decimal":
                value = two_places(float(value))
            elif kind == "float":
                value = float(value)
        out[column] = value
    return out


class InMemoryStore:
    """The reference store: dictionaries behind one lock. Tests and the fixtures run on it."""

    def __init__(self) -> None:
        self._tables: dict[str, dict[int, Row]] = {t: {} for t in SCHEMA}
        self._next: dict[str, int] = dict.fromkeys(SCHEMA, 1)
        self._lock = threading.RLock()

    def insert(self, table: str, row: Row) -> Row:
        with self._lock:
            new_id = self._next[table]
            self._next[table] = new_id + 1
            stored = normalize_row(table, {**copy.deepcopy(row), "id": new_id})
            self._tables[table][new_id] = stored
            return copy.deepcopy(stored)

    def get(self, table: str, id: int) -> Row | None:
        with self._lock:
            row = self._tables[table].get(id)
            return copy.deepcopy(row) if row is not None else None

    def select(self, table: str, where: Row | None = None) -> list[Row]:
        with self._lock:
            rows = [
                copy.deepcopy(r)
                for _, r in sorted(self._tables[table].items())
                if all(r.get(k) == v for k, v in (where or {}).items())
            ]
            return rows

    def update(self, table: str, id: int, changes: Row) -> None:
        with self._lock:
            row = self._tables[table][id]
            self._tables[table][id] = normalize_row(table, {**row, **copy.deepcopy(changes)})

    def increment(self, table: str, id: int, column: str, amount: int, touch: datetime) -> None:
        with self._lock:
            row = self._tables[table][id]
            row[column] = int(row[column]) + amount
            row["updated_at"] = touch

    def claim_level(
        self, table: str, id: int, from_level: int, to_level: int, touch: datetime
    ) -> bool:
        with self._lock:
            row = self._tables[table].get(id)
            if row is None or int(row["current_level"]) != from_level:
                return False
            row["current_level"] = to_level
            row["updated_at"] = touch
            return True
