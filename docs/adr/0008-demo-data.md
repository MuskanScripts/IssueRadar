# 0008. Demo data is synthetic and labelled

- Status: accepted
- Date: 2026-10-01

## Context

Demo mode must run without a token for contributors, screenshots and a public
demo. Every number shown as real must be reproducible from real API data.

## Decision

- Demo fixtures in `src/issueradar/demo/fixtures/` are written by hand, use
  made-up `sample/...` repository names and `example` users, and carry
  `"label": "Demo data"` at the top. The CLI and UI show that label wherever
  demo data appears.
- Demo data is never mixed with real data in the same view.
- Recorded real API responses (M1) live separately in `tests/fixtures/github/`
  and are used only by tests.

## Consequences

Screenshots made in demo mode are honest by construction. Demo numbers say
nothing about real repositories, and docs must not quote them as results.
