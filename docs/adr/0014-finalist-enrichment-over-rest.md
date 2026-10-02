# 0014. Enrich finalists only, over REST

- Status: accepted
- Date: 2026-10-02

## Context

Claims live in comments and many PR links live in the issue timeline. Reading
both for every open issue of a big repo would cost two requests per issue. The
brief prefers batching through GraphQL, but GraphQL could not be reached from
the environment M2 was built in, so GraphQL queries and field names could not
be checked against real responses.

## Decision

- Only **finalists** are enriched: open issues with no assignee, no
  `linked:pr` hit and no closing reference from an open PR, most recently
  updated first, up to `enrich.max_issues_per_repo` (30) per repo.
- Comments are re-read only when the issue's `updated_at` changed. Timelines are
  always requested conditionally, so an unchanged timeline is a free 304.
- Both use REST (`/issues/{n}/comments`, `/issues/{n}/timeline`), which was
  verified against recorded responses.
- Repo health inputs are refreshed at most every 24 hours.

## Consequences

The first sync of a repo costs up to about 70 requests; later ones mostly
304s. Issues outside the finalist set show as UNCLEAR ("comments not checked")
until they become finalists. Moving finalist reads to batched GraphQL is a
later optimisation, once real GraphQL responses are recorded.
