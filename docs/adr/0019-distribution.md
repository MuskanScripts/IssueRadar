# 0019. Distribution: composite Action, PyPI with trusted publishing, GHCR image

- Status: accepted
- Date: 2026-10-02

## Context

M6 needs three ways to run FirstPR: a scheduled GitHub Actions job for people
without a server, `pip install` for people with Python, and a container for
people with a home server. Each must work from the README alone, keep secrets
out of files, and only read from GitHub.

## Decision

- **Action.** A composite action (`action.yml` at the repo root) installs the
  package from the action's own checkout, restores the SQLite database from the
  Actions cache, applies a `watchlist.txt` file (`watch add --file --exact`) and
  runs `firstpr daily`. Composite, not Docker or JavaScript: no image to pull on
  every run, the same code path as the CLI, and it runs on any runner with Python.
  The template repo pins the moving major tag (`@v0`), which the release
  workflow moves.
- **Database between runs.** `actions/cache/restore` and `actions/cache/save`
  with a key per run and a prefix restore key, saved even when a step fails, so
  ETags, sent items and PR history survive.
- **PyPI.** Released by `.github/workflows/release.yml` on a `vX.Y.Z` tag using
  trusted publishing (OIDC). No API token is stored. The wheel bundles the
  built dashboard (`scripts/bundle_web.py`), so users need no Node.
- **Container.** One image (`ghcr.io/muskanscripts/issueradar`), non-root,
  `/data` volume, health check on `/api/health`, pushed by the same workflow.
  `docker-compose.yml` runs the dashboard and a daily loop from that image.
- **Landing page.** Static HTML in `site/`, self-hosted fonts, deployed to
  GitHub Pages. No build step.

## Consequences

- The maintainer must register the PyPI trusted publisher, enable Pages, and
  create the template repo (docs/human-tasks.md).
- The template falls back to `GITHUB_TOKEN` when no `FIRSTPR_GITHUB_TOKEN`
  secret exists. ADR 0006 still recommends a fine-grained token; the
  self-test workflow measures what `GITHUB_TOKEN` can read and RESULTS.md
  records it.
- Actions caches expire after 7 days unused, so a long pause means one cold
  run that may repeat a few issues.
