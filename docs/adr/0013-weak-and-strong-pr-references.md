# 0013. Strong and weak references from pull requests

- Status: accepted
- Date: 2026-10-02

## Context

Layer 2 of "has a PR" detection scans open PR text for issue numbers. On real
recorded data, Dependabot PR bodies produced up to 159 unrelated numbers per
PR, copied from upstream release notes (RESULTS.md).

## Decision

- A reference preceded by a GitHub closing keyword (close, fix, resolve and
  their forms) is stored in `closing_issues`: strong signal.
- Any other `#n`, `owner/repo#n` or issue URL for the same repo goes in
  `mentioned_issues`: weak signal.
- Bodies of bot-authored PRs (`type: Bot` or a login ending in `[bot]`) are not
  scanned; their titles still are.

## Consequences

M2 can treat a closing reference as "has a PR" and a mention as "maybe", and
explain which one it saw. Human PRs that paste long logs can still produce weak
mentions; the evaluation harness will show whether that matters.
