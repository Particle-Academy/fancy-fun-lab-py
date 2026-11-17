# Using fancy-fun-lab

A headless gamification engine for Python: XP to gamed metrics, levels and
weighted level groups, achievements, prizes with inventory, leaderboards and an
event log with analytics. Zero runtime dependencies. It behaves exactly like
the PHP [`particle-academy/laravel-fun-lab`](https://github.com/Particle-Academy/laravel-fun-lab)
and the Node [`@particle-academy/fancy-fun-lab`](https://github.com/Particle-Academy/fancy-fun-lab-js):
all three pass the same `fun-lab/*` conformance tables.

## Install

```bash
pip install fancy-fun-lab
```

Python 3.11 or newer. Import name: `fancy_fun_lab`.

## Find it on the Fancy MCP catalog

The Fancy MCP catalog server is `https://ui.particle.academy/mcp` (streamable
HTTP, no API key; MCP id `fancy-ui`). Search it with `search-backend-packages`
for "gamification" to find this package beside its PHP and Node twins, and
`install-instructions` for the commands. The matching UI is
`@particle-academy/fancy-fun-lab-ui`.

## Essentials

```python
from fancy_fun_lab import FunLab, Subject, SqliteStore

lab = FunLab()  # in-memory store, system clock
# lab = FunLab(store=SqliteStore("app.sqlite"))  # the same tables a Laravel app uses

lab.setup("gamed-metric", {"slug": "combat", "name": "Combat"})
lab.setup("metric-level", {"metric": "combat", "level": 2, "xp": 100, "name": "Apprentice"})
lab.setup("achievement", {"slug": "apprentice"})
lab.attach_achievement("apprentice", metric_level=("combat", 2))  # granted on reaching it

ada = Subject("user", 1)  # any awardable: a type and an id
lab.award("combat").to(ada).amount(150).because("boss").from_("arena").save()

lab.has_level(ada, 2, metric="combat")  # True
lab.level_info(ada, "combat")  # current, total, next, progress %
lab.grant("first-login").to(ada).save()  # AwardResult(success, message)
lab.leaderboard().for_("user").period("weekly").take(10)
lab.analytics().by_type("points").period("monthly").total()
```

- **Catalog:** `setup(a, with_)` creates or updates by slug. `a` is
  `gamed-metric` (`metric`), `metric-level` (`level`), `metric-level-group`
  (`group`), `metric-level-group-level` (`group-level`),
  `metric-level-group-metric` (`group-metric`, with a `weight`), `achievement`
  or `prize`. An achievement's `for` takes a subject type.
- **XP:** `award(metric)...save()` returns the profile-metric row, or raises
  `FunLabError` (bad input) / `AwardRejected` (`kind`: `cap_exceeded`,
  `pipeline_rejected`, `opted_out`).
- **Grants:** `grant(slug)...save()` returns an `AwardResult`; a refusal is a
  result with a message, never an exception. An achievement is held once; a
  prize repeats until its inventory runs out. `claim_prize(id)`,
  `fulfill_prize(id)`.
- **Opt-out:** `opt_out(subject)`, `opt_in(subject)`. Opted-out subjects get
  nothing and are left off leaderboards unless `exclude_opted_out(False)`.
- **Events:** `lab.on("xp.awarded", fn)`, also `metric.level-reached`,
  `achievement.unlocked`, `prize.awarded`, `award.granted`, `catalog.mutated`,
  or `"*"` for `fn(name, event)`. Nothing is broadcast; wire them yourself.
- **Validation:** `lab.add_validation_step(fn)`; return
  `{"valid": False, "message": ...}` to refuse an award or grant.
- **JSON:** `fancy_fun_lab.resources` turns rows into the exact shapes the
  Laravel package's API returns (profile, leaderboard entry, achievement,
  prize, metric level, grants), which is what the UI renders.
- **Stores:** `InMemoryStore` (default) or `SqliteStore(path, prefix="lfl_")`.
  Your own: implement the `Store` protocol; `claim_level` must be a real
  compare-and-set and `increment` atomic.
- **Time:** `FunLab(clock=...)` takes any callable returning a `datetime`;
  timestamps are kept as naive UTC, to the second.

## Traps

- **A period leaderboard needs the event log.** `daily`, `weekly` (from
  Monday) and `monthly` boards rank on XP *earned in the period*, read from the
  log. With `FunLabConfig(log_to_database=False)` or `dispatch=False` they raise
  `PeriodLeaderboardUnavailable` rather than return an empty board.
- **Default names come from `headline()`, which lowercases acronyms:**
  `setup("gamed-metric", {"slug": "Combat XP"})` is named `"Combat Xp"`. Pass a
  `name` if that matters.
- **Slugs drop non-Latin scripts:** `slug("日本語") == ""`. Give an ASCII slug.
- **`setup()` overwrites:** fields you leave out of a second `setup()` of the
  same slug go back to their defaults (description, icon, ...), as Laravel's
  `updateOrCreate` does.
- **`has_level()` creates the subject's profile** if it had none.
- **Group XP truncates per metric:** two metrics at weight 0.5 with 7 XP each
  are 6, not 7.
- **Progress is from the current level's floor,** not from zero, and is
  clamped to 0-100.
- **Event order:** an award emits its `metric.level-reached` events (and the
  achievements they grant) before its own `xp.awarded`.
