# Architecture

Status: M0. This page describes the target design and marks what exists today.

## Pipeline

```mermaid
flowchart LR
    W[Watchlist] --> D[Discover]
    D --> F[Fetch]
    F --> N[Normalise]
    N --> E[Enrich]
    E --> S[Score]
    S --> R[Rank]
    R --> V[Deliver]
    F <--> C[GitHub client<br/>GET and GraphQL queries only]
    E <--> C
    C <--> B[API budgeter<br/>core, search, graphql]
    N --> DB[(SQLite or Postgres)]
    S --> DB
    V --> O1[RSS and Markdown]
    V --> O2[Email, Telegram, Discord, Slack]
```

| Stage | What it does | Milestone |
| --- | --- | --- |
| Discover | Per-repo issue search with `is:issue state:open no:assignee -linked:pr`, incremental with `updated:>=` | M1 |
| Fetch | REST with ETags; GraphQL batches for comments and timelines of finalists | M1 |
| Normalise | Store repos, issues, signals and PRs with `user_id` on personal tables | M1 |
| Enrich | Availability, difficulty, repo health, stack matching | M2 |
| Score and rank | Weighted formulas from config, each with a "why" list | M2 |
| Deliver | Digest renderers and channels | M3 |

## Interfaces

All of these are thin shells over the same core package.

| Interface | Exists today |
| --- | --- |
| CLI (`firstpr`) | `--version`, `doctor`, `demo` |
| FastAPI server | M5 |
| React dashboard (`web/`) | Shell that renders demo data with the design tokens |
| Scheduled GitHub Action | M6 |

## Boundaries that matter

- **Only the GitHub client talks to GitHub**, and it refuses writes (ADR 0004).
- **Config holds every limit and weight** (ADR 0005). `firstpr doctor` prints the loaded GitHub limits.
- **Demo data never mixes with real data** (ADR 0008).
- **The product name is in `brand.json`** (ADR 0002). The web app imports the same file.

## Code map (today)

```
src/issueradar/
  brand.json, brand.py     product identity
  cli.py                   Typer app
  config/defaults.yaml     limits, thresholds, weights
  config/settings.py       pydantic schema, loader, friendly errors
  models.py                Tier, Availability, PullRequestStatus, ...
  demo/loader.py           demo dataset schema and loader
  demo/fixtures/demo.json  demo data
web/src/
  styles/tokens.css        design tokens, light and dark
  lib/                     brand and demo data for the web
  components/              level dots, free pill, lists, theme toggle
```
