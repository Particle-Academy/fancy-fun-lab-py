# fancy-fun-lab

[![Fancified](art/fancified.svg)](https://particle.academy)

**A headless gamification engine for Python.** XP awarded to gamed metrics,
levels and weighted level groups, achievements, prizes with inventory,
leaderboards (all-time, daily, weekly, monthly and per metric) and an event log
with analytics, with **zero runtime dependencies**.

The Python twin of [`particle-academy/laravel-fun-lab`](https://github.com/Particle-Academy/laravel-fun-lab)
(PHP), with [`@particle-academy/fancy-fun-lab`](https://github.com/Particle-Academy/fancy-fun-lab-js) (Node) beside it.
All three run the same `fun-lab/*` conformance tables from
[`fancy-conformance`](https://github.com/Particle-Academy/fancy-conformance) in
their own CI, so the same awards give the same levels, boards and log in every
runtime, and [`@particle-academy/fancy-fun-lab-ui`](https://github.com/Particle-Academy/fancy-fun-lab-ui)
renders the same JSON whichever backend produced it.

<!-- fancy-agents-note:start -->
> **For agents.** Every Fancy package, this one included, is listed on the
> Fancy MCP catalog server at `https://ui.particle.academy/mcp` (streamable HTTP, no API key;
> MCP id `fancy-ui`), with install commands and docs. How an agent installs
> and uses this package is in [AGENTS.md](https://github.com/Particle-Academy/fancy-fun-lab-py/blob/main/AGENTS.md).
<!-- fancy-agents-note:end -->

## What it does

- **XP to gamed metrics** ("combat", "crafting", "coins"), with a per-action cap
  and validation hooks.
- **Levels** per metric, and **level groups** that weigh several metrics
  together. A level is claimed exactly once, even under concurrent awards.
- **Achievements**, granted by hand or automatically when a level is reached,
  and **prizes** with inventory and a claim / fulfil lifecycle.
- **Leaderboards** all-time, daily, weekly or monthly (on the XP earned in the
  period), per metric, by awardable type, paged.
- **An event log** of every award, grant and catalog change, with analytics:
  counts, totals, active users, completion rates, time series, breakdowns.
- **Opt-out**, honoured everywhere.
- **Stores:** in-memory, or SQLite on the standard library using
  laravel-fun-lab's own tables, so it can share a database with a Laravel app.

## Example

```python
from fancy_fun_lab import FunLab, Subject

lab = FunLab()
lab.setup("gamed-metric", {"slug": "combat"})
lab.setup("metric-level", {"metric": "combat", "level": 2, "xp": 100})

ada = Subject("user", 1)
lab.award("combat").to(ada).amount(150).save()
lab.level_info(ada, "combat")["current_level"]  # 2
```

## Status

```bash
pip install fancy-fun-lab
```

## License

MIT
