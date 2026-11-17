# Changelog

All notable changes to this package are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Pre-1.0, breaking changes land in MINOR releases.** The version number is not
promising otherwise until 1.0.

## [Unreleased]

## [0.1.1] - 2026-11-17

### Fixed

- **The broadcastable events now carry the payload laravel-fun-lab broadcasts.** `xp.awarded`, `metric.level-reached`, `achievement.unlocked` and `prize.awarded` events gain a `payload` property: the flat dict PHP's `broadcastWith()` returns, key for key (`{id, profile_id, gamed_metric_id, gamed_metric_slug, gamed_metric_name, amount, total_xp, current_level, reason, source, occurred_at}` for `xp.awarded`; `{profile_id, gamed_metric_id, gamed_metric_slug, gamed_metric_name, level, level_name, xp_threshold, total_xp, achievements: [{id, slug, name, icon}], occurred_at}` for `metric.level-reached`; the grant payloads for the other two). In 0.1.0 a host could only relay the raw event, whose rows are nested, so `@particle-academy/fancy-fun-lab-ui` rendered `+5 XP in {metric}` and `FunLabLevelUp` the same way. **Consumer action:** if you relay events to a browser, send `event.payload` instead of the event (or your own mapping, which you can now delete). Nothing else changes: the events keep every attribute they had.
- `XpAwarded` and `MetricLevelReached` gain an `occurred_at` attribute (the engine's clock at emission), defaulted, so constructing them positionally still works.

### Added

- `fancy_fun_lab.payloads`: `xp_awarded_payload`, `level_reached_payload`, `achievement_unlocked_payload`, `prize_awarded_payload`, also exported from the package root. The same serializers `event.payload` uses.
- Runs the new `fun-lab/events` table (fancy-conformance 0.50.0, 9 rows, goldens exported from the PHP event classes' `broadcastWith()`), on both stores. Test-only.

### Changed

- **Docs:** the README gives the install line (`pip install fancy-fun-lab`) instead of saying the package is not yet published; 0.1.0 is on PyPI. No code changed; nothing to do.

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
