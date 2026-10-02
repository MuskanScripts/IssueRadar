# 0012. Sync open lists with ETags instead of `updated:>=` search

- Status: accepted
- Date: 2026-10-02

## Context

The brief asks for incremental sync with `updated:>=` and for ETag caching.
The two do not combine: an ETag only helps when the same URL is requested
again, and a moving `updated:>=` or `since=` value changes the URL every run,
so GitHub can never answer 304. Search also has its own budget of 30 requests
per minute, while the list endpoints use the 5,000 per hour core budget.

## Decision

For each watched repository, `sync` fetches:

1. `GET /repos/{owner}/{repo}`
2. `GET /repos/{owner}/{repo}/issues?state=open&sort=created&direction=asc&per_page=100`
3. `GET /repos/{owner}/{repo}/pulls?state=open&sort=created&direction=asc&per_page=100`

with the same parameters every time and a stable sort, so unchanged pages come
back as free 304s. Items that drop out of a complete open list are marked
`not_open` (closed, transferred or deleted). Lists stop at
`sync.max_pages_per_list` pages; a truncated list never marks anything.

Search (`-linked:pr`, `updated:>=`) is still used where it adds information the
lists do not have, starting in M2.

## Consequences

Measured on a real repo: the second sync answered every request with 304 and
used no budget (RESULTS.md). A new issue near the start of a long list shifts
later pages, so those pages are re-downloaded; that is still far cheaper than
search for watchlists of normal size.
