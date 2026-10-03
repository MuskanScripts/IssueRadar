# FirstPR

Find open-source issues you can actually work on, then track the pull requests
you open.

FirstPR watches the repositories you choose and answers three questions about
every open issue:

1. **Is it free?** Nobody is assigned, no pull request is linked or mentions it, and nobody has claimed it in the comments.
2. **Is it my level and my stack?** Beginner, Intermediate or Pro, matched against your skills.
3. **Is the repo worth my time?** A health score from how fast maintainers reply and how often outside pull requests get merged.

Every answer comes with the reasons behind it. FirstPR is **read-only toward
GitHub**: it never comments, opens pull requests, assigns, stars or follows. When
a pull request goes quiet it drafts a polite nudge for you to copy, and you
decide whether to send it.

![FirstPR dashboard on demo data: the radar, an issue's reasons, keyboard navigation, My PRs, the digest preview, Insights and dark mode](docs/media/demo.gif)

*40 seconds of the dashboard on demo data ([MP4](docs/media/demo.mp4)). Try it yourself with `firstpr serve --demo`.*

> **Status: v0.1.0.** Everything runs locally, in Docker, as a daily GitHub
> Actions job, or from an AI assistant over MCP. See [ROADMAP.md](ROADMAP.md)
> for what is next.
>
> "FirstPR" is a working name.

## Three ways to run it

| You want | Use | Guide |
| --- | --- | --- |
| A daily digest, no server, nothing installed | GitHub Actions template | [docs/github-action.md](docs/github-action.md) |
| The dashboard on your own machine | `pip install firstpr` | [docs/self-hosting.md](docs/self-hosting.md) |
| It always on, on a home server | Docker Compose | [docs/self-hosting.md](docs/self-hosting.md#2-docker-compose) |

The rest of this page is for running it from a clone of the source.

## Quick start (Windows PowerShell)

You need Python 3.11 or newer (3.13 recommended) and, for the dashboard,
Node 22 LTS through [fnm](https://github.com/Schniz/fnm).

```powershell
git clone https://github.com/MuskanScripts/IssueRadar.git
cd IssueRadar
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
firstpr doctor
firstpr demo
```

`firstpr demo` runs on bundled demo data. It needs no token and makes no API calls.

### Watch and sync real repositories

Create a read-only token first ([docs/human-tasks.md](docs/human-tasks.md)), then:

```powershell
$env:FIRSTPR_GITHUB_TOKEN = "your-read-only-token"
firstpr doctor
firstpr watch add modelcontextprotocol/python-sdk
firstpr sync
```

Run `firstpr sync` again and most requests come back as free `304 Not Modified`
answers from the local cache.

### Find and explain

```powershell
Copy-Item examples\skills.yaml skills.yaml   # then edit it
firstpr find --level beginner --language python
firstpr explain https://github.com/modelcontextprotocol/python-sdk/issues/123
firstpr pack list
```

`explain` works on any public issue; if its repo isn't synced it fetches just
that issue. Every score is explained in [docs/scoring.md](docs/scoring.md).

### Daily digest

```powershell
firstpr init              # creates firstpr.yaml and skills.yaml to edit
firstpr digest            # preview
firstpr digest --send     # writes digests/latest.md and digests/feed.xml
```

Email, Telegram, Discord and Slack are set up in [docs/digest.md](docs/digest.md).

`firstpr daily` runs sync, your pull requests and `digest --send` in one go.
It is what the Action, the Docker job and a scheduled task run. A watchlist
can also live in a file: `firstpr watch add --file watchlist.txt --exact`.

### Your pull requests

```powershell
firstpr prs                                   # find your PRs and what each needs
firstpr prs --show owner/repo#12              # one PR's timeline and nudge draft
firstpr prs --repo owner/repo                 # only one repo (no search API needed)
```

Statuses, most urgent first: changes requested, CI failing, merge conflict,
stale (with a polite nudge drafted for you to copy), approved, waiting for
review, merged, closed. Nothing is ever posted for you. Data is stored in a SQLite file in your user data
folder; set `FIRSTPR_DB_URL` to use another location or database.

If PowerShell refuses to run `Activate.ps1`, allow local scripts for your user
once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Dashboard

From the repository root:

```powershell
fnm use
cd web
npm ci
npm run build
cd ..
firstpr serve
```

Open http://127.0.0.1:8765. `fnm use` picks Node 22 from `.nvmrc` (run
`fnm install 22` first if you don't have it). Add `?demo=1` to the address, or
use the switch in Settings, to see bundled demo data with no token.

While working on the dashboard itself, run `firstpr serve` in one window and
`npm run dev` in `web/` in another, then open http://localhost:5173.

Keys: `j` and `k` move through the list, `o` opens an issue, `x` dismisses,
`s` snoozes, `/` searches, `Ctrl+K` jumps anywhere.

### From an AI assistant (MCP)

```powershell
python -m pip install -e ".[mcp]"
firstpr mcp
```

`firstpr mcp` gives any MCP-capable assistant three read-only tools:
`find_issues`, `explain_issue` and `my_prs`. Client setup is in
[docs/mcp.md](docs/mcp.md).

## Run the checks

Python, from the repository root with the virtual environment active:

```powershell
ruff check .
ruff format --check .
mypy
pytest
```

Web, from `web/`:

```powershell
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium   # once
npm run e2e                       # smoke test and accessibility checks
```

CI runs all of these on every push and pull request, plus a container build
and a secret scan. The Action is tested by `action-selftest.yml`.

## Project layout

```
src/issueradar/        Python core: CLI, config, models, demo data
  brand.json           the product name and other user-facing identifiers
  config/defaults.yaml every GitHub limit, threshold and scoring weight
  demo/fixtures/       demo data, always labelled "Demo data"
  github/              the only code that talks to GitHub (read-only)
  storage/             database tables and migrations
  sync/                watchlist, sync and enrichment
  engine/              availability, difficulty, health, stack and ranking
  presets/             repo rules and starter packs
  radar.py             runs the engines on stored data
  api/                 local API for the dashboard
  mcp_server.py        MCP tools for AI assistants
eval/                  labelling template for the evaluation harness
tests/                 Python tests (never touch the network)
  fixtures/github/     recorded and documented GitHub responses
scripts/               fixture recorder, benchmarks, release helpers
web/                   React dashboard (Vite, TypeScript, Tailwind CSS)
site/                  landing page (static, GitHub Pages)
template/              files for the GitHub Actions template repo
action.yml             the GitHub Action
Dockerfile             container image; docker-compose.yml runs it
config/                settings mounted into the containers
docs/                  architecture, ADRs, GitHub API notes, human tasks
examples/              sample config and skills.yaml
```

## Documentation

- [PLAN.md](PLAN.md): milestones, decisions and risks
- [docs/github-api-notes.md](docs/github-api-notes.md): GitHub API limits we rely on, with sources
- [RESULTS.md](RESULTS.md): measured numbers, each with the command that produced it
- [docs/scoring.md](docs/scoring.md): exactly how every score is computed
- [docs/digest.md](docs/digest.md): the daily digest and its channels
- [docs/github-action.md](docs/github-action.md): run it on GitHub Actions
- [docs/self-hosting.md](docs/self-hosting.md): pip, Docker Compose, scheduled tasks
- [docs/mcp.md](docs/mcp.md): use it from an AI assistant over MCP
- [ROADMAP.md](ROADMAP.md): what is done and what is next
- [CHANGELOG.md](CHANGELOG.md): what changed in each release
- [eval/README.md](eval/README.md): how to label issues and measure the engines
- [docs/architecture.md](docs/architecture.md): how the pieces fit
- [docs/design-tokens.md](docs/design-tokens.md): colours, type and the rules for using them
- [docs/adr](docs/adr): architecture decision records
- [docs/human-tasks.md](docs/human-tasks.md): things only the maintainer can do
- [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## Licence

[MIT](LICENSE). Not affiliated with GitHub.
