# Contributing

Notes for anyone, human or agent, working ON this package's code. How to USE the
package is in [AGENTS.md](./AGENTS.md); what it is, is in [README.md](./README.md).
`CLAUDE.md` is a symlink to this file, so Claude Code reads these notes when it
works in this repo.

This file describes **this package's code**. Process rules (publishing,
versioning, backports) live in the envelope's rules and are deliberately not
repeated here.

## What this package is

A **port** of `particle-academy/laravel-fun-lab`, not a redesign. Behaviour is
settled by the shared `fun-lab/*` tables in `fancy-conformance`, whose goldens
are exported from the PHP engine; where a table is silent, the PHP engine's
source is the reference. Modules map onto PHP classes of the same purpose
(`engine.py` is `AwardEngine` + the services + the two builders, `setup.py` is
`SetupValidator`, `leaderboard.py` / `analytics.py` the builders,
`resources.py` the `Http/Resources`), so a question is answered by reading the
PHP method of the same name.

## Setup and tests

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -e . --group dev
pytest          # needs ../fancy-conformance beside this repo (the .agi envelope)
ruff check . && ruff format --check .
mypy
```

`tests/test_conformance.py` runs every `fun-lab/*` table twice, on
`InMemoryStore` and on `SqliteStore`. `tests/scenario_runner.py` is the
adapter, and it mirrors `laravel-fun-lab/tests/Conformance/ScenarioRunner.php`
line for line: if you change one, change the other, or the goldens stop meaning
the same thing on both sides. CI checks fancy-conformance out at the tag
`PINNED_SUITE_VERSION` names; a test fails if the two disagree.

## Invariants

- **Zero runtime dependencies.** `dependencies = []` in `pyproject.toml`. Any
  addition is an owner approval request first.
- **Every query is computed by the engine over rows.** Stores only insert,
  get, select-by-equality, update, increment and claim. That is why the two
  stores cannot disagree on a leaderboard: there is one leaderboard
  implementation. A store that wants SQL-side aggregation must still return the
  same rows.
- **`claim_level` is the only path that moves `current_level`.** It is what
  makes a level (and its achievements) claimed exactly once under concurrent
  awards, for metrics and groups both. Never write `current_level` with
  `update()`.
- **`_save()` touches `updated_at` only when something changed**, like
  Eloquent. `increment()` and `claim_level()` always touch it, like Eloquent's
  query-builder updates. The timestamps in the tables depend on both.
- **Messages are contract.** They are compared verbatim with PHP, including
  `->to($user)` in a Python error and the full stop that award refusals have
  and grant refusals do not.
- **The event log writes what PHP writes**: `[]` (never `{}`) for an empty
  `meta`, the PHP model class in `entity_model`, the entity slug in
  `achievement_slug` for catalog rows, and `system` / `0` as the awardable of a
  system event. A log shared with a Laravel app must read the same.

## Traps

- **`bool` is an `int` in Python.** `setup.py` checks `bool` first; the
  fixture loader refuses `True` for `1`. Keep both.
- **Clocks.** `now()` is naive UTC truncated to the second. A clock with
  microseconds would make two rows in one request differ where PHP's are equal.
- **`slug()` is best effort outside the table.** Laravel folds through
  `voku/portable-ascii`; this folds Latin with NFKD plus a short map, and drops
  what portable-ascii measurably drops (fractions, roman numerals, circled
  numbers, the `dz` digraphs). A new non-Latin case belongs in
  `fun-lab/strings` first, red.
- **SQLite connections are closed by whoever opens them.** The suite runs with
  warnings as errors, and an unclosed connection is a `ResourceWarning`.
