# Platform apps

The FirstPR platform (the hosted website) is built here, next to the self-hosted CLI, which stays in `src/issueradar`.

| Folder | What it is | Run it with |
|---|---|---|
| `api/` | FastAPI app under `/api/v1`. Today: `GET /api/v1/health` | `uvicorn --factory firstpr_api.main:create_app` |
| `worker/` | Arq worker on Redis. Today: a heartbeat every minute | `arq firstpr_worker.main.WorkerSettings` |

The web app (Next.js) comes next, in `apps/web/`.

## Run everything locally

```powershell
docker compose -f infra/compose/compose.yaml up --build
```

Then open http://localhost:8000/api/v1/health. It answers 200 when Postgres and Redis are reachable and 503 when one is not. The `worker` field shows `ok`, `stale` or `missing` but does not cause a 503, so a stopped worker is visible without taking the site down.

## Develop without Docker

```powershell
python -m pip install -e "apps/api[dev]" -e "apps/worker[dev]"
cd apps/api; pytest; mypy
```

The test against real Postgres and Redis runs when `FIRSTPR_TEST_DATABASE_URL` and `FIRSTPR_TEST_REDIS_URL` are set. CI sets both.

## Why the CLI code has not moved

The plan puts the shared engine in `packages/core`. Moving `src/issueradar` now would change the PyPI package, the GitHub Action and the Docker image for no gain yet, because nothing here uses the engine. It moves in Step 3, when the sync worker first imports it.
