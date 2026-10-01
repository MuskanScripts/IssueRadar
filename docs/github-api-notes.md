# GitHub API notes

What FirstPR relies on from the GitHub API, and where each fact came from.

**Checked on 2026-10-01.** `docs.github.com` was not reachable from the build
environment, so every fact below was read from the source of the same pages in
the [`github/docs`](https://github.com/github/docs) repository (`main` branch),
from the public GraphQL schema in that repository
(`src/graphql/data/fpt/schema.docs.graphql`), and from GitHub's OpenAPI
description ([`github/rest-api-description`](https://github.com/github/rest-api-description)).
These are the files the docs site is built from.

Status legend:

- **Verified (docs)**: stated in the docs source today.
- **Verified (schema)**: present in the published GraphQL schema or OpenAPI file.
- **Not stated**: the docs do not say. We will measure it and record the result here.
- **To measure**: needs a real token. Planned milestone in brackets.

Every number in this file also lives in `src/issueradar/config/defaults.yaml`.
Code reads limits from config, never from constants.

## 1. REST primary rate limits

| Fact | Value | Status | Source |
| --- | --- | --- | --- |
| Authenticated user (PAT, OAuth, GitHub App user token) | 5,000 requests per hour, shared by everything acting as that user | Verified (docs) | `data/reusables/rest-api/primary-rate-limit-authenticated-users.md` |
| Unauthenticated | 60 requests per hour, per originating IP | Verified (docs) | `primary-rate-limit-unauthenticated-users.md` |
| `GITHUB_TOKEN` in Actions | 1,000 requests per hour per repository | Verified (docs) | `primary-rate-limit-github-token-in-actions.md` |
| GitHub App installation token | 5,000 per hour minimum; +50 per repo above 20 repos; +50 per org user above 20 users; capped at 12,500 | Verified (docs) | `primary-rate-limit-github-app-installations.md` |
| Rate limit headers | `x-ratelimit-limit`, `-remaining`, `-used`, `-reset` (UTC epoch seconds), `-resource` | Verified (docs) | `content/rest/using-the-rest-api/rate-limits-for-the-rest-api.md` |
| Headers are authoritative | Values can differ between regions; trust headers over `GET /rate_limit`; do not depend on an exact remaining count | Verified (docs) | same page |
| `GET /rate_limit` | Does not count against the primary limit, can count against the secondary limit | Verified (docs) | same page |
| Exceeding the primary limit | `403` or `429`, `x-ratelimit-remaining: 0`; do not retry before `x-ratelimit-reset` | Verified (docs) | same page |

**Design consequence.** The budgeter tracks each resource (`core`, `search`,
`graphql`) from `x-ratelimit-resource` and the other headers on every response.
It plans with a safety margin (config: `github.budget.safety_margin`) rather than
spending to exactly zero, because the docs warn the count can wobble.

## 2. Secondary rate limits (REST and GraphQL)

Source: `data/reusables/rest-api/secondary-rate-limit-rest-graphql.md`. Verified (docs).

- At most **100 concurrent requests**, shared across REST and GraphQL.
- At most **900 points per minute** for REST endpoints, **2,000 points per minute** for GraphQL.
- Points: GraphQL query without mutations = 1, with mutations = 5; most REST `GET`/`HEAD`/`OPTIONS` = 1; most `POST`/`PATCH`/`PUT`/`DELETE` = 5. Some endpoints have unpublished costs.
- At most **90 seconds of CPU time per 60 seconds** of real time, no more than 60 of it for GraphQL. Estimate it from total response time.
- Content creation limits (80 per minute, 500 per hour) exist. FirstPR never creates content, so they do not apply.
- The limits "are subject to change without notice", and a limit may be hit "for undisclosed reasons".

What to do when limited (Verified (docs), REST page "Exceeding the rate limit"):

1. If `retry-after` is present, wait that many seconds.
2. Else if `x-ratelimit-remaining` is `0`, wait until `x-ratelimit-reset`.
3. Otherwise wait **at least one minute**.
4. If it keeps failing, back off exponentially and **give up after a fixed number of retries**.
5. "Continuing to make requests while you are rate limited may result in the banning of your integration."

There is no way to check secondary-limit status in advance.

**Design consequence.** Requests are serial by default (config:
`github.concurrency.max_in_flight: 1`). The retry policy above is implemented
once, in the HTTP layer, with `max_retries` and `min_secondary_wait_seconds` in
config.

## 3. Conditional requests (ETag)

Source: `content/rest/using-the-rest-api/best-practices-for-using-the-rest-api.md`. Verified (docs).

- Most endpoints return `etag`; many return `last-modified`.
- "Making a conditional request does not count against your primary rate limit if a `304` response is returned and the request was made while correctly authorized with an `Authorization` header."
- A `304` is only returned when the representation is unchanged. Different `per_page`, `page` or filters give a different ETag. Sorts like `sort=updated` reshuffle pages, so use a stable sort when polling.
- Conditional requests are not supported for unsafe methods (irrelevant: FirstPR only sends `GET`).

**To measure [M1].** The brief notes a third-party claim that authenticated
conditional requests are unreliable. M1 adds a live check (`firstpr doctor
--measure-etag`) that records `x-ratelimit-remaining` before and after a `304`
and writes the result to `RESULTS.md`. Unit tests use fixtures only.

GraphQL has no ETag support. Repeated GraphQL reads are cached locally with a TTL.

## 4. GraphQL limits

Source: `content/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api.md`. Verified (docs).

| Fact | Value |
| --- | --- |
| Primary limit, users (PAT, apps acting as a user) | 5,000 points per hour |
| Primary limit, `GITHUB_TOKEN` | 1,000 points per hour per repository |
| Primary limit, GitHub App installation | 5,000 per hour, same +50 scaling, capped at 12,500 |
| Connections | Every connection must pass `first` or `last`, value 1 to 100 |
| Nodes | One call may not request more than 500,000 total nodes |
| Cost | Query `rateLimit { cost remaining resetAt }`; `x-ratelimit-resource` is always `graphql` |
| Exceeding the primary limit | **HTTP 200** with an error message and `x-ratelimit-remaining: 0` |
| Exceeding a secondary limit | HTTP **200 or 403** with an error message; same wait rules as REST |
| Timeout | Over 10 seconds is terminated ("We couldn't respond to your request in time"), and **extra points are deducted from the next hour** |

**Design consequence.** The GraphQL client treats a `200` with an `errors`
array as a failure, checks headers on every response, logs `rateLimit.cost`
per query, and keeps batches small enough to finish well under 10 seconds
(config: `github.graphql.batch_size`).

## 5. Search

Sources: `content/rest/search/search.md`, `content/search-github/searching-on-github/searching-issues-and-pull-requests.md`, OpenAPI `/search/issues`. Verified (docs).

| Fact | Value |
| --- | --- |
| Rate limit, authenticated | 30 requests per minute (all search endpoints except code search) |
| Rate limit, code search | 10 requests per minute, authentication required |
| Rate limit, unauthenticated | 10 requests per minute |
| Results | Up to 1,000 per search; `per_page` max 100 |
| Query length | Max 256 characters, not counting operators or qualifiers |
| Operators | Max five `AND`, `OR`, `NOT` |
| Repository scope | Searches at most 4,000 matching repositories |
| Timeouts | Returns what was found so far with `incomplete_results: true` (not proof that results are missing) |
| 422 | "Validation Failed": bad syntax, or `repo:`/`user:`/`org:` you cannot access |
| GitHub App user tokens | Must include `is:issue` or `is:pull-request`, otherwise 422 |

Qualifiers confirmed in the docs: `is:issue`, `is:open` / `state:open`,
`no:assignee`, `linked:pr` and `-linked:pr`, `label:`, `archived:false`,
`language:`, `updated:>=DATE`, `comments:`, `interactions:`, `is:locked`,
`repo:owner/name`.

- `-linked:pr` matches issues "not linked to a pull request **by a closing reference**". A PR that only mentions the issue is not caught. That is why availability uses three layers (brief section 4.3).
- `no:` qualifiers have no negated form in the docs table (there is no `-no:`). We use `assignee:*` when we need "has an assignee".

**Newer options (out of scope for v1).** The OpenAPI file lists
`advanced_search=true` and `search_type` (`semantic`, `hybrid`; default lexical)
on `GET /search/issues`. We do not use them in v1 (ADR 0007). Not verified
here: the 10-requests-per-minute limit for semantic search mentioned in the
brief.

**Design consequence.** Search runs per repository (`repo:owner/name`), never
globally, and the query builder refuses queries over the length or operator
limits before sending them.

## 6. Issue timeline and "has a PR"

- REST: `GET /repos/{owner}/{repo}/issues/{issue_number}/timeline` exists and works for GitHub Apps. Verified (schema, OpenAPI).
- GraphQL `Issue` has `timelineItems(itemTypes: [...], first: N)` and `closedByPullRequestsReferences(...)`. Verified (schema).
- `IssueTimelineItemsItemType` includes `CROSS_REFERENCED_EVENT`, `CONNECTED_EVENT`, `DISCONNECTED_EVENT`, `ASSIGNED_EVENT`, `UNASSIGNED_EVENT`, `LABELED_EVENT`, `ISSUE_COMMENT`. Verified (schema).
- `CrossReferencedEvent` has `willCloseTarget: Boolean!`, `source`, `actor`, `createdAt`. Verified (schema).
- **To measure [M1].** Layer 2 (scan open PR titles and bodies for `#123`) is a design guess from the brief. M1 records real open-PR lists from a few repos and checks how many issue links it finds that `-linked:pr` misses.

## 7. Comments and roles

`CommentAuthorAssociation` values (Verified (schema)): `COLLABORATOR`,
`CONTRIBUTOR`, `FIRST_TIMER`, `FIRST_TIME_CONTRIBUTOR`, `MANNEQUIN`, `MEMBER`,
`NONE`, `OWNER`.

FirstPR treats `OWNER`, `MEMBER` and `COLLABORATOR` as maintainers. Everyone
else is an outside contributor. (The REST `author_association` field uses the
same values.)

## 8. Pull request tracking

Verified (schema):

- `PullRequestReviewDecision`: `APPROVED`, `CHANGES_REQUESTED`, `REVIEW_REQUIRED`. The field is nullable, so it is empty when a repo does not require reviews. We also read the latest reviews.
- `PullRequestReviewState`: `APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`, `DISMISSED`, `PENDING`.
- `MergeableState`: `CONFLICTING`, `MERGEABLE`, `UNKNOWN`. `UNKNOWN` means "still computing"; re-query on the next sync.
- `StatusState` (for `statusCheckRollup.state`): `ERROR`, `EXPECTED`, `FAILURE`, `PENDING`, `SUCCESS`.

Search qualifiers `author:@me`, `is:pr`, `review:`, `status:`, `draft:`,
`is:merged`, `is:unmerged` are in the search docs. **To measure [M4]:**
whether a fine-grained token with no extra permissions can run
`author:@me is:pr` search. `firstpr doctor` will check it.

## 9. Tokens

- Fine-grained PATs "always include read-only access to all public repositories on GitHub". Verified (docs, `managing-your-personal-access-tokens.md`). So the least-privileged token is: fine-grained, resource owner = you, repository access = "Public repositories (read-only)", no extra permissions.
- A classic PAT "with no assigned scopes can only access public information". Verified (docs). Acceptable fallback.
- `GITHUB_TOKEN` is an installation token whose "permissions are limited to the repository that contains your workflow". Verified (docs, `content/actions/concepts/security/github_token.md`). **Not stated:** whether it can read other repositories' public data. Irrelevant for the template, because its 1,000-per-hour-per-repo budget is too small anyway; the template uses a PAT secret (ADR 0006). To measure in M6 for the record.

## 10. Still to verify

| Item | When | How |
| --- | --- | --- |
| Authenticated `304` does not reduce `x-ratelimit-remaining` | M1 | Live measurement, recorded in `RESULTS.md` |
| Open-PR scan finds links that `-linked:pr` misses | M1 | Recorded fixtures from real repos |
| Fine-grained PAT can search `author:@me is:pr` | M4 | `firstpr doctor` with the user's token |
| `GITHUB_TOKEN` reading other public repos | M6 | One run in the template repo |
| Semantic/hybrid search limits | after v1 | Out of scope |
