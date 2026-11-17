# Changelog

All notable changes to this package are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Pre-1.0, breaking changes land in MINOR releases.** The version number is not
promising otherwise until 1.0.

## [Unreleased]

## [0.1.0] - 2026-11-17

### Added

- **The engine, to parity with laravel-fun-lab 0.8.0.** Catalog setup with the
  same types, aliases, validation messages, upsert-by-slug and default names;
  XP awards with the per-action cap, validation pipeline and opt-out; metric
  levels and weighted level groups, each claimed exactly once with their
  attached achievements; achievement and prize grants with inventory and
  redemption; `has_level`, `level_info` and `group_level_info` with progress
  from the level floor; leaderboards (all-time, daily / weekly / monthly on the
  XP earned in the period, per metric, paged); the event log and its analytics;
  events by the PHP names; serializers for the PHP API's JSON shapes; `slug()`
  and `headline()` as Laravel's `Str` computes them.
- **Two stores:** `InMemoryStore`, and `SqliteStore` on the standard library's
  `sqlite3` with laravel-fun-lab's own tables (`lfl_` prefix, configurable).
- **Held to the PHP engine by the shared `fun-lab/*` tables** (fancy-conformance
  0.49.0, 67 rows), run on both stores in CI on Python 3.11 to 3.14.
- Zero runtime dependencies.
