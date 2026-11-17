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
source is the reference.
