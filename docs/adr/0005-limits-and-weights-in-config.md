# 0005. Limits and weights live in config

- Status: accepted
- Date: 2026-10-01

## Context

GitHub changes limits without notice, and scoring weights need tuning and must
be visible to users.

## Decision

`src/issueradar/config/defaults.yaml` holds every GitHub limit, retry setting,
threshold and scoring weight. A pydantic schema (`issueradar.config.settings`)
validates it, and the user's `firstpr.yaml` overrides any value. Code never
hard-codes these numbers. Each GitHub number has its source in
`docs/github-api-notes.md`.

## Consequences

Config validation errors must be friendly (field path plus what is allowed).
`firstpr doctor` shows the effective values.
