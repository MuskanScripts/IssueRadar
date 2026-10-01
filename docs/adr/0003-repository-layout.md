# 0003. Repository layout

- Status: accepted
- Date: 2026-10-01

## Context

The project has a Python core (engine, CLI, API) and a React dashboard. They
share demo fixtures and design decisions and are released together.

## Decision

One repository:

- `src/issueradar/`: Python package (src layout), including `brand.json`,
  config defaults and demo fixtures.
- `tests/`: Python tests. `tests/fixtures/github/` will hold recorded API
  responses (M1).
- `web/`: React app with its own `package.json`. It imports `brand.json` and the
  demo fixtures from the Python package instead of copying them.
- `docs/`: documentation and ADRs. `examples/`: sample user config.
  `presets/`: repo rules and starter packs (M2).

## Consequences

One CI workflow covers both halves. The web build reaches outside `web/` for
two JSON files; Vite allows this with `server.fs.allow`.
