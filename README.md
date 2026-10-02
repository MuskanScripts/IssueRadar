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

> **Status: milestone M0 (scaffold).** The demo works. Syncing real repositories
> arrives in M1. See [PLAN.md](PLAN.md) for the roadmap.
>
> "FirstPR" is a working name.

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

If PowerShell refuses to run `Activate.ps1`, allow local scripts for your user
once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Dashboard (demo data)

From the repository root:

```powershell
fnm use
cd web
npm ci
npm run dev
```

Open http://localhost:5173. `fnm use` picks Node 22 from `.nvmrc`
(run `fnm install 22` first if you don't have it).

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
```

CI runs all of these on every push and pull request, plus a secret scan.

## Project layout

```
src/issueradar/        Python core: CLI, config, models, demo data
  brand.json           the product name and other user-facing identifiers
  config/defaults.yaml every GitHub limit, threshold and scoring weight
  demo/fixtures/       demo data, always labelled "Demo data"
tests/                 Python tests (never touch the network)
web/                   React dashboard (Vite, TypeScript, Tailwind CSS)
docs/                  architecture, ADRs, GitHub API notes, human tasks
examples/              sample config and skills.yaml
```

## Documentation

- [PLAN.md](PLAN.md): milestones, decisions and risks
- [docs/github-api-notes.md](docs/github-api-notes.md): GitHub API limits we rely on, with sources
- [docs/architecture.md](docs/architecture.md): how the pieces fit
- [docs/design-tokens.md](docs/design-tokens.md): colours, type and the rules for using them
- [docs/adr](docs/adr): architecture decision records
- [docs/human-tasks.md](docs/human-tasks.md): things only the maintainer can do
- [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## Licence

[MIT](LICENSE). Not affiliated with GitHub.
