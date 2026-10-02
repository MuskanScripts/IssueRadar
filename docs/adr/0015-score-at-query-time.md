# 0015. Score at query time, keep snapshots for history

- Status: accepted
- Date: 2026-10-02

## Context

Ranking depends on the user's skills and filters, which change more often
than the GitHub data. Availability, tier and health don't depend on the user.

## Decision

- `find`, `explain` and `eval` run the engines on stored data each time they
  are called. Nothing about ranking is stored.
- `sync` writes a `score_snapshots` row per open issue with the
  user-independent results (availability, tier, difficulty and health scores,
  reasons), to give history for trends and the digest's "changed since
  yesterday" later.

## Consequences

Changing a weight in config takes effect immediately, with no re-sync. Scoring
a few thousand issues takes well under a second, so there is no need for a
cache yet.
