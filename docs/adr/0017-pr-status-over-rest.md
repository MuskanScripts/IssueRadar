# 0017. PR status from REST, in a fixed order

- Status: accepted
- Date: 2026-10-02

## Context

The brief suggests GraphQL (`reviewDecision`, `mergeable`, `statusCheckRollup`)
for PR details. GraphQL could not be reached from the environment M4 was built
in, while every REST endpoint needed could, and could be recorded for tests.
`reviewDecision` is also empty when a repo doesn't require reviews, so the
latest reviews have to be read anyway.

## Decision

- Details come from REST: the PR (`mergeable`, `mergeable_state`, `draft`,
  `merged`), its reviews, the head commit's check runs and combined status, and
  the issue timeline.
- One status per PR, first match wins: merge conflict, CI failing, changes
  requested, approved, stale, waiting for review. Closed PRs are merged,
  accepted by a bot import (repo rules), or closed unmerged.
- `mergeable: null` means GitHub is still computing; it is never a conflict.
- Each reviewer's latest decisive review counts; comments don't change a
  decision; a dismissal removes it; the author's own reviews are ignored.
- Stale: no activity by anyone other than the author for `stale_days` (7),
  counted from the last such activity or from when the PR was opened.

## Consequences

About five requests per open PR per refresh, mostly 304s after the first.
The order means a PR with both a conflict and a requested change shows the
conflict first, because nothing else can be merged until it's fixed.
