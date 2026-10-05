# Platform apps

The FirstPR platform (the hosted website) is built here, next to the self-hosted CLI, which stays in `src/issueradar`.

| Folder | What it is | Run it with |
|---|---|---|
| `api/` | FastAPI app under `/api/v1`. Today: `GET /api/v1/health` | `uvicorn --factory firstpr_api.main:create_app` |
| `worker/` | Arq worker on Redis. Today: a heartbeat every minute | `arq firstpr_worker.main.WorkerSettings` |
| `web/` | Next.js app. Public pages are server-rendered and cached; pages after sign-in are client components that call the API | `npm run dev` |

In front of them, a Caddy proxy (`infra/compose/Caddyfile`) puts everything on one address: `/api/*` goes to FastAPI, everything else to Next.js. One address means the session cookie works on every page with no extra setup.

| Route | Kind | What it shows today |
|---|---|---|
| `/` | Public, server-rendered, cached 30 seconds | Intro text and the platform status, fetched by the server from the API |
| `/home` | Signed-in area (sign-in comes in Step 2), client component | The API status, fetched by the browser through the proxy, with a Refresh button |

## Run everything locally

```powershell
docker compose -f infra/compose/compose.yaml up --build
```

Then open http://localhost:8080 for the site and http://localhost:8080/api/v1/health for the API. The health check answers 200 when Postgres and Redis are reachable and 503 when one is not. The `worker` field shows `ok`, `stale` or `missing` but does not cause a 503, so a stopped worker is visible without taking the site down.

## Develop without Docker

```powershell
python -m pip install -e "apps/api[dev]" -e "apps/worker[dev]"
cd apps/api; pytest; mypy
```

For the web app, with the API running on port 8000 (`npm run dev` sends `/api` there):

```powershell
cd apps/web
npm install
npm run dev     # http://localhost:3000
npm run lint; npm run typecheck; npm run build
```

The test against real Postgres and Redis runs when `FIRSTPR_TEST_DATABASE_URL` and `FIRSTPR_TEST_REDIS_URL` are set. CI sets both.

## Why the CLI code has not moved

The plan puts the shared engine in `packages/core`. Moving `src/issueradar` now would change the PyPI package, the GitHub Action and the Docker image for no gain yet, because nothing here uses the engine. It moves in the last part of Step 1, before the sync worker starts using it in Step 3.
