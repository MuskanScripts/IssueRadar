# 0004. The GitHub client is read-only

- Status: accepted
- Date: 2026-10-01

## Context

A bug that posts a comment, opens a PR or assigns an issue on a maintainer's
repository would hurt the user's reputation. GitHub also restricts excessive
automated activity.

## Decision

FirstPR never writes to GitHub. The single GitHub client (built in M1):

- rejects any REST method other than `GET` before a request is sent;
- rejects any GraphQL document that contains a `mutation` or `subscription`
  operation, by parsing it, not by string search;
- is the only module allowed to import `httpx` for GitHub hosts (checked by a test).

Nudge messages are drafts shown for the user to copy. They are never sent.

## Consequences

Some convenient features (auto-claiming, auto-nudging) are impossible by design.
Tests in M1 prove the guard and fail if it is removed.
