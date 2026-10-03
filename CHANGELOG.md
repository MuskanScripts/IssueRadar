# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Changed

- GitHub Actions moved to their Node 24 versions everywhere, including `action.yml` and the template workflow, so runs no longer show the Node 20 deprecation warning.
- Dev tools: pytest up to 9, pytest-cov up to 7, mypy up to 2, rich up to 15; jsdom 30 and the newest `@types/node` 22 for the dashboard.

## [0.1.0] - 2026-10-03

First release: milestones M0 to M6 and M8.

### Added (M8)

- MCP server, `firstpr mcp` over stdio, with read-only `find_issues`, `explain_issue` and `my_prs` tools that return structured results. Optional extra: `firstpr[mcp]`.
- docs/mcp.md and ADR 0020.

### Added (M6)

- GitHub Action (`action.yml`) and the template repo files in `template/`: a daily scheduled digest with the database kept in the Actions cache.
- `firstpr daily` (sync, your pull requests, digest), `watch add --file` and `--exact`, and the digest on the Actions run summary.
- Docker image (non-root, `/data` volume, health check) and `docker-compose.yml` with the dashboard and a daily job; `GET /api/health`.
- The wheel bundles the built dashboard. Release workflow: PyPI with trusted publishing, GHCR image, GitHub release.
- Landing page in `site/` for GitHub Pages, brand assets in `docs/brand/`.
- Docs: `docs/github-action.md`, `docs/self-hosting.md`, `ROADMAP.md`, ADR 0019.

### Changed (M6)

- Network errors are retried and then reported in one line instead of a traceback.

### Added (M5)

- Local API (FastAPI, OpenAPI at /api/docs) and `firstpr serve`, bound to 127.0.0.1 by default.
- Dashboard: Radar with a one-time sweep, keyboard-friendly virtualised list, issue drawer with every reason, Repos, My PRs board with nudge drafts, Profile editor, Digest preview, Insights, Settings.
- Command palette (Ctrl+K), shortcuts (j, k, o, x, s, /), saved views, density toggle, light and dark themes.
- Demo mode in the browser with no token or server.
- Playwright smoke test with axe checks on every screen, in CI.

### Added (M4)

- PR tracker: finds your PRs (search, or one repo's list) and derives a status from the PR, its reviews, checks and timeline.
- `firstpr prs` (most urgent first) and `firstpr prs --show` (timeline and nudge draft).
- Nudge drafts after 7 quiet days, shown for you to copy and never posted.
- The digest's "Your pull requests" section, and a coach warning when 3 or more of your PRs await a first review.
- PRs closed with a repo's bot-import label count as accepted.
- Recorded fixtures of 5 real PRs; `scripts/record_fixtures.py --pr`.

### Added (M3)

- Daily digest with free issues, your pull requests, new since yesterday, watchlist alerts and a quiet-day note.
- Sent items are remembered: a second `digest --send` sends nothing new. `dismiss` and `snooze`.
- Markdown, plain-text and HTML rendering; RSS, Markdown, email (SMTP), Telegram, Discord and Slack channels.
- `firstpr init`, `firstpr export`, and a contribution checklist in `explain`.
- `scripts/bench_digest.py`; ranking about five times faster (RESULTS.md).

### Added (M2)

- Availability engine with six states and a reason for every decision; maintainer invitations are never claims.
- Difficulty engine (score, tier, time estimate, issue type), repo health engine with CLA, DCO, AI-policy and issue-first flags, stack matching against `skills.yaml`, and ranking.
- Enrichment during sync: one `linked:pr` search per repo, comments and timelines for finalists, repo health inputs cached for 24 hours.
- `firstpr explain`, `firstpr find`, `firstpr eval sample/run`, `firstpr pack list/add/verify`.
- Per-repo rules and four starter packs (not verified yet).
- `docs/scoring.md`, ADRs 0014 and 0015, migration 0002.

### Fixed (M2)

- Upgrading a SQLite database no longer deletes child rows: foreign keys are off while tables are rebuilt.
- Repos that use YAML issue forms now get credit for an issue template.

### Added (M1)

- Read-only GitHub client: REST `GET` only and GraphQL queries only, enforced by tests.
- API budgeter that tracks core, search and GraphQL budgets from response headers and stops at a safety margin.
- Retry rules from GitHub's docs: `retry-after`, at least a minute for secondary limits, exponential backoff, fixed retry count.
- ETag cache in the database; a second sync of an unchanged repo uses no budget (RESULTS.md).
- SQLite storage with Alembic migrations for every table in the brief.
- `firstpr watch add/remove/list`, `firstpr sync`, and `firstpr doctor --measure-etag`.
- Sync resumes after a quota hit, and one failing repo no longer stops the run.
- Fixture recorder script and recorded real responses; tests block the network.

### Changed (M1)

- PR references are split into closing (strong) and mentioned (weak); bot PR bodies are skipped, after real data showed heavy noise.
- Dependabot no longer proposes React major upgrades.

### Added (M0)

- M0 scaffold: Python package with `firstpr --version`, `doctor` and `demo`.
- Config schema with every GitHub limit and scoring weight, validated with friendly errors.
- Demo dataset, labelled "Demo data", shared by the CLI and the web app.
- Web shell (React, Vite, Tailwind CSS v4) with light and dark design tokens and contrast tests.
- CI (lint, type-check, tests, build, package build, secret scan) and Dependabot.
- PLAN.md, ADRs 0001 to 0011, GitHub API notes, contributor and security docs.

[Unreleased]: https://github.com/MuskanScripts/IssueRadar/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MuskanScripts/IssueRadar/releases/tag/v0.1.0
