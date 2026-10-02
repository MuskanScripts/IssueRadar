# 0018. Demo mode runs in the browser from the bundled fixtures

- Status: accepted
- Date: 2026-10-02

## Context

Demo mode must run with no token, for contributors, screenshots and a public
demo, and the smoke test must run in CI. Serving demo data from the API would
need Python, a database and a server for every demo and every frontend test run.

## Decision

The dashboard has two data sources behind one interface (`lib/source.ts`):
the local API, and a demo source that maps the bundled `demo.json` (the same
file the CLI uses) into the API's shapes. `?demo=1` or the switch in Settings
picks the demo source and every screen shows "Demo data". Dismiss, snooze,
profile and saved views work in demo mode and are kept in the browser only.

## Consequences

The built dashboard alone is a working demo (a static host would do), and the
Playwright suite needs only `vite preview`. The demo mapping must follow API
changes; TypeScript types catch most mismatches.
