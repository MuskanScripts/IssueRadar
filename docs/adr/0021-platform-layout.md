# 0021. Platform apps and the shared engine

- Status: accepted
- Date: 2026-10-05

## Context

The hosted platform (API, worker, web app) needs the same engine as the
self-hosted CLI: availability, difficulty, health, ranking and the GitHub
client. ADR 0003 put that engine in `src/issueradar`.

## Decision

- The engine lives in `packages/core/src/issueradar`. The root `pyproject.toml`
  still builds the `firstpr` package from it, so the PyPI package, the GitHub
  Action and the Docker image do not change.
- Platform apps live in `apps/`: `api/` (FastAPI), `worker/` (Arq) and `web/`
  (Next.js). Each has its own `pyproject.toml` or `package.json`, tests and
  Dockerfile.
- `infra/compose/` runs the platform locally behind one Caddy proxy.
- `.importlinter` holds the import rules and CI runs them: the engine never
  imports the apps, the apps never import each other, scoring stays free of
  I/O, and the GitHub client depends on nothing above it.

## Consequences

The CLI and the platform share one engine and one set of tests. Paths in docs
and configs now point into `packages/core`. The API and worker will depend on
the `firstpr` package (installed from `packages/core` in development) when they
start using the engine.
