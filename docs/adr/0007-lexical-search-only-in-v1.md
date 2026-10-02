# 0007. Lexical issue search only in v1

- Status: accepted
- Date: 2026-10-01

## Context

`GET /search/issues` now accepts `advanced_search` and `search_type`
(`semantic`, `hybrid`). Their limits are tighter and behaviour is less
predictable.

## Decision

v1 uses the default lexical search with documented qualifiers only. Newer
options can be evaluated after v1 with the evaluation harness.

## Consequences

Results are reproducible and explainable. We may miss some relevant issues that
semantic search would find; the watchlist model makes this less important.
