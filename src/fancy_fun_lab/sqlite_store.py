"""``SqliteStore``: the ``Store`` contract on the standard library's ``sqlite3``.

The tables, columns and value formats are laravel-fun-lab's own (``lfl_``
prefix, booleans as 0/1, JSON as text, timestamps as ``Y-m-d H:i:s``), so a
Python service and a Laravel app can share one SQLite file. Tables are created
if missing; an existing Laravel-migrated database is used as it is.

``claim_level`` is one ``UPDATE ... WHERE current_level = ?``, which SQLite
executes atomically; ``increment`` is one ``UPDATE ... SET col = col + ?``. Every
call runs in autocommit under one lock, so the store may be shared by threads.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .clock import from_db, to_db
from .schema import SCHEMA, UNIQUE, two_places
from .store import Row

_SQL_TYPES = {
    "id": "integer primary key autoincrement not null",
    "int": "integer",
    "str": "varchar",
    "bool": "tinyint(1)",
    "json": "text",
    "datetime": "datetime",
    "decimal": "numeric",
    "float": "numeric",
}


class SqliteStore:
    def __init__(
        self, path: str | Path = ":memory:", prefix: str = "lfl_", create: bool = True
    ) -> None:
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        self._prefix = prefix
        if create:
            self.create_tables()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def table(self, name: str) -> str:
        return self._prefix + name

    def create_tables(self) -> None:
        with self._lock:
            for name, columns in SCHEMA.items():
                cols = []
                for column, (kind, default) in columns.items():
                    spec = f'"{column}" {_SQL_TYPES[kind]}'
                    if default is not None and kind != "id":
                        spec += (
                            f" default {self._to_sql(kind, default)!r}"
                            if kind == "str"
                            else f" default {self._to_sql(kind, default)}"
                        )
                    cols.append(spec)
                self._db.execute(
                    f'create table if not exists "{self.table(name)}" ({", ".join(cols)})'
                )
                for unique in UNIQUE.get(name, []):
                    index = self.table(name) + "_" + "_".join(unique) + "_unique"
                    quoted = ", ".join(f'"{c}"' for c in unique)
                    target = f'"{self.table(name)}" ({quoted})'
                    self._db.execute(f'create unique index if not exists "{index}" on {target}')

    # --- value conversion -------------------------------------------------

    @staticmethod
    def _to_sql(kind: str, value: Any) -> Any:
        if value is None:
            return None
        if kind == "datetime":
            return to_db(value) if isinstance(value, datetime) else value
        if kind == "json":
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if kind == "bool":
            return 1 if value else 0
        if kind in ("decimal", "float"):
            return float(value)
        return value

    @staticmethod
    def _from_sql(kind: str, value: Any) -> Any:
        if value is None:
            return None
        if kind == "datetime":
            return from_db(str(value))
        if kind == "json":
            return json.loads(value)
        if kind == "bool":
            return bool(value)
        if kind == "decimal":
            return two_places(float(value))
        if kind == "float":
            return float(value)
        if kind in ("int", "id"):
            return int(value)
        return value

    def _row(self, name: str, cursor: sqlite3.Cursor, values: tuple[Any, ...]) -> Row:
        columns = SCHEMA[name]
        names = [d[0] for d in cursor.description]
        return {
            col: self._from_sql(columns[col][0], val)
            for col, val in zip(names, values, strict=True)
            if col in columns
        }

    # --- the contract ------------------------------------------------------

    def insert(self, table: str, row: Row) -> Row:
        columns = SCHEMA[table]
        data = {
            c: self._to_sql(columns[c][0], row.get(c, default))
            for c, (kind, default) in columns.items()
            if kind != "id"
        }
        names = ", ".join(f'"{c}"' for c in data)
        marks = ", ".join("?" for _ in data)
        with self._lock:
            cur = self._db.execute(
                f'insert into "{self.table(table)}" ({names}) values ({marks})', list(data.values())
            )
            new_id = int(cur.lastrowid or 0)
            stored = self.get(table, new_id)
        assert stored is not None
        return stored

    def get(self, table: str, id: int) -> Row | None:
        with self._lock:
            cur = self._db.execute(f'select * from "{self.table(table)}" where "id" = ?', (id,))
            values = cur.fetchone()
            return self._row(table, cur, values) if values is not None else None

    def select(self, table: str, where: Row | None = None) -> list[Row]:
        columns = SCHEMA[table]
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (where or {}).items():
            if value is None:
                clauses.append(f'"{column}" is null')
            else:
                clauses.append(f'"{column}" = ?')
                params.append(self._to_sql(columns[column][0], value))
        sql = f'select * from "{self.table(table)}"'
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += ' order by "id"'
        with self._lock:
            cur = self._db.execute(sql, params)
            return [self._row(table, cur, values) for values in cur.fetchall()]

    def update(self, table: str, id: int, changes: Row) -> None:
        if not changes:
            return
        columns = SCHEMA[table]
        sets = ", ".join(f'"{c}" = ?' for c in changes)
        params = [self._to_sql(columns[c][0], v) for c, v in changes.items()]
        with self._lock:
            self._db.execute(
                f'update "{self.table(table)}" set {sets} where "id" = ?', [*params, id]
            )

    def increment(self, table: str, id: int, column: str, amount: int, touch: datetime) -> None:
        with self._lock:
            self._db.execute(
                f'update "{self.table(table)}" set "{column}" = "{column}" + ?, '
                '"updated_at" = ? where "id" = ?',
                (amount, to_db(touch), id),
            )

    def claim_level(
        self, table: str, id: int, from_level: int, to_level: int, touch: datetime
    ) -> bool:
        with self._lock:
            cur = self._db.execute(
                f'update "{self.table(table)}" set "current_level" = ?, "updated_at" = ? '
                'where "id" = ? and "current_level" = ?',
                (to_level, to_db(touch), id, from_level),
            )
            return cur.rowcount == 1
