# FirstPR plan

FirstPR (working name) finds open-source issues a person can actually work on,
and then tracks the pull requests they open. It is read-only toward GitHub,
deterministic, and explains every score it shows.

This file holds the milestones, the decisions that shape them, and the risks.
Each decision has a short ADR in [`docs/adr`](docs/adr). GitHub API facts and
their sources are in [`docs/github-api-notes.md`](docs/github-api-notes.md).

## How we work

- One milestone at a time. At the end of each: all tests pass, docs are
  updated, work is committed, and we stop for a review before the next one.
- Every number shown as real comes from real API data. Sample data is
  labelled "Demo data".
- Tests never touch the network. They use recorded fixtures of real public API
  responses.
- Commands are given for PowerShell on Windows 11. No bash-only scripts, no
  Makefiles.

## Architecture in one paragraph

A Python core (`src/issueradar`) runs the pipeline **discover, fetch,
normalise, enrich, score, rank, deliver**. A single GitHub client is the only
code that talks to GitHub; it refuses anything but REST `GET` and GraphQL
queries, and an API budgeter in front of it tracks every rate-limit bucket.
Results go to SQLite through SQLAlchemy (Postgres-ready). The Typer CLI, the
FastAPI server and the scheduled GitHub Action are thin shells over the same
core. The React dashboard (`web/`) talks only to the FastAPI server, or, in
demo mode, to bundled fixtures.

```
watchlist ──► discover ──► fetch ──► normalise ──► enrich ──► score ──► rank ──► deliver
                 │            │                        │          │                 │
                 └── GitHub client (GET + GraphQL queries only) ◄─┘                 ├─ RSS / Markdown
                              │                                                     ├─ email / Telegram
                        API budgeter (core, search, graphql)                        └─ Discord / Slack
                              │
                         SQLite / Postgres  ◄── CLI · FastAPI · Action · Web
```

## Key decisions (summary)

| # | Decision | ADR |
| --- | --- | --- |
| 1 | Keep ADRs for every significant decision | [0001](docs/adr/0001-record-architecture-decisions.md) |
| 2 | Code name `issueradar` is stable; the product name lives only in `brand.json` | [0002](docs/adr/0002-brand-in-one-place.md) |
| 3 | One repository: Python core at the root, web app in `web/` | [0003](docs/adr/0003-repository-layout.md) |
| 4 | The GitHub client is read-only and a test enforces it | [0004](docs/adr/0004-read-only-github-client.md) |
| 5 | Every API limit and scoring weight lives in config | [0005](docs/adr/0005-limits-and-weights-in-config.md) |
| 6 | The Action template uses a fine-grained PAT, not `GITHUB_TOKEN` | [0006](docs/adr/0006-pat-for-action-template.md) |
| 7 | v1 uses lexical issue search only | [0007](docs/adr/0007-lexical-search-only-in-v1.md) |
| 8 | Demo data is synthetic, uses `sample/` repo names, and is always labelled | [0008](docs/adr/0008-demo-data.md) |
| 9 | Fonts are bundled with the app, not loaded from Google | [0009](docs/adr/0009-self-hosted-fonts.md) |
| 10 | Frontend dependencies are added in the milestone that uses them | [0010](docs/adr/0010-staged-frontend-dependencies.md) |
| 11 | Plain `venv` + `pip`, `hatchling` build backend | [0011](docs/adr/0011-python-tooling.md) |
| 12 | Sync open lists with ETags instead of `updated:>=` search | [0012](docs/adr/0012-etag-list-sync.md) |
| 13 | PR references are strong (closing keywords) or weak (mentions); bot PR bodies skipped | [0013](docs/adr/0013-weak-and-strong-pr-references.md) |
| 14 | Enrich finalists only, over REST (GraphQL batching later) | [0014](docs/adr/0014-finalist-enrichment-over-rest.md) |
| 15 | Score at query time; keep snapshots for history | [0015](docs/adr/0015-score-at-query-time.md) |
| 16 | A digest item is sent once, until what the reader sees changes | [0016](docs/adr/0016-digest-idempotency.md) |

## Milestones

Status: **M0, M1 and M2 done (merged). M3 in review.** Everything after M3 is planned, not built.

### M0. Scaffold

Scope: repository layout, Python package and CLI skeleton (`firstpr --version`,
`firstpr doctor`, `firstpr demo`), config schema with GitHub limits, demo
fixtures, design tokens (light and dark), web app shell that renders the demo
fixtures with the tokens, CI, Dependabot, ADRs, this plan, API notes, community
files.

Done when:

- [x] A fresh clone installs and starts with the documented PowerShell commands.
- [x] Demo fixtures load in the CLI (`firstpr demo`) and in the web shell.
- [x] CI is green on GitHub.

### M1. GitHub client, budgeter, storage

Scope: async `httpx` client (REST + GraphQL), read-only guard, API budgeter per
token and resource, retry and backoff policy from config, ETag cache,
SQLAlchemy models and first Alembic migration for every table in brief 5.2,
watchlist sync with `updated:>=` incremental fetch, fixture recorder.

Done when:

- [ ] A sync of a watchlist works with a real token. (Works through the build
  container's GitHub access; still to run with your personal token.)
- [x] A second run uses ETag caching and measurably fewer requests; the difference
  and the conditional-request measurement are written to `RESULTS.md`.
- [x] A test simulates quota exhaustion mid-sync; the next run resumes with no data loss.
- [x] GraphQL errors inside HTTP 200 responses are handled and tested.
- [x] A test proves the client rejects every non-GET REST method and any GraphQL mutation.

### M2. Engines and evaluation

Scope: availability (six states, three PR-detection layers, claim patterns,
maintainer invitations), difficulty (labels, heuristics, time bucket), repo
health, stack matching, ranking, per-repo rules and starter packs,
`firstpr explain <issue-url>`, evaluation harness and labelling CSV template,
`docs/scoring.md`.

Done when:

- [x] One command prints precision and recall for FREE detection and tier
  accuracy (`firstpr eval run`). Real numbers wait on hand-labelled issues.
- [x] `explain` shows the "why" for availability, tier and health.
- [x] Claim detection has unit tests, including maintainer-invitation false positives.
- [ ] Starter packs verified with `firstpr pack verify` (needs a personal token).
- [x] Merged.

### M3. CLI and digest

Scope: all CLI commands from brief section 6, digest sections, idempotency via
`seen_items`, dismiss and snooze, renderers (HTML, text, Markdown), channels
(RSS and Markdown first, then SMTP email, Telegram, Discord, Slack).

Done when:

- [x] `digest --send` works for RSS and Markdown.
- [x] A second run sends nothing new (tested).
- [x] Email, Telegram, Discord and Slack channels, off until configured.
- [x] Digest from cache in under 5 seconds (about 2 s on 5,000 generated issues; RESULTS.md).

### M4. PR tracker

Scope: `author:@me is:pr` discovery, GraphQL details, status derivation, stale
logic, "needs you" ordering, nudge drafts (never posted), per-PR timeline,
bot-import acceptance rule.

Done when: statuses match github.com for at least 5 real PRs; stale-day logic is
tested with frozen time.

### M5. API and dashboard

Scope: FastAPI with OpenAPI, React dashboard (Radar, list view, issue drawer,
Repos, My PRs, Profile, Digest, Insights, Settings), demo mode, command
palette, keyboard shortcuts, saved views, density toggle.

Done when: demo mode runs with no token; the Playwright smoke test passes; axe
reports zero serious violations on every screen; the main flow works by
keyboard alone.

### M6. Distribution

Scope: GitHub Action template repo, Dockerfile and compose, PyPI packaging with
trusted publishing, release automation, docs set, landing page, screen recording.

Done when: following only the README on a clean machine takes under 10 minutes;
the template repo's scheduled workflow produces a digest.

### M7. Hosted multi-user mode (feature flag)

Starts only after M0 to M6 ship and a handful of other people use it. Sign in
with GitHub (no write scopes), encrypted tokens, Postgres, shared crawler
prioritised by watcher count, per-user rate limits, delete-my-data, privacy
policy and terms.

### M8 (optional). MCP server

Read-only tools (`find_issues`, `explain_issue`, `my_prs`) using the official
MCP Python SDK.

### M9 (optional). Classifier experiment

Only after the hand-labelled set exists. Ships only if it beats the rule-based
tiers on that set; numbers are reported either way.

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Rate limits are lower than they look (search is 30/min; secondary limits are opaque) | Slow or failed syncs | Per-repo search, serial requests, ETag cache, budgeter with safety margin, resume after quota hit |
| `-linked:pr` misses PRs that only mention an issue | Shows issues as free when they are not | Layer 2 open-PR scan and layer 3 timeline check on finalists; show "why" so users can judge |
| Claim detection by phrases is noisy (non-English, sarcasm, maintainers inviting) | Wrong FREE/CLAIMED | Configurable patterns, `author_association` check, UNCLEAR state, evaluation harness with real labels |
| Difficulty from labels and text is a guess | Wrong tier | Show the reasons, collect "harder/easier" feedback, measure accuracy |
| Hand-labelled evaluation set does not exist yet | Cannot report precision honestly | Ship the CSV template in M2; report only measured numbers |
| Conditional requests may not save quota as documented | Higher API use | Measure in M1 and report |
| GitHub docs change | Wrong limits | All limits in config; `docs/github-api-notes.md` dated with sources |
| Product name may be taken | Rename later | Name lives in `brand.json` (ADR 0002) |
| Hosted mode carries legal and privacy duties | Compliance issues | Deferred to M7; read current GitHub terms first; flag items for a lawyer |
| Scope is large for one person | Nothing ships | Strict milestone gates; optional features stay optional |
