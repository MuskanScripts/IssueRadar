# Platform apps

The FirstPR platform (the hosted website) is built here. The engine it shares with the self-hosted CLI lives in `packages/core`.

| Folder | What it is | Run it with |
|---|---|---|
| `api/` | FastAPI app under `/api/v1`: health, GitHub sign-in, sessions, `GET /me` | `uvicorn --factory firstpr_api.main:create_app` |
| `worker/` | Arq worker on Redis. Today: a heartbeat every minute | `arq firstpr_worker.main.WorkerSettings` |
| `web/` | Next.js app. Public pages are server-rendered and cached; pages after sign-in are client components that call the API | `npm run dev` |

In front of them, a Caddy proxy (`infra/compose/Caddyfile`) puts everything on one address: `/api/*` goes to FastAPI, everything else to Next.js. One address means the session cookie works on every page with no extra setup.

| Route | Kind | What it shows today |
|---|---|---|
| `/` | Public, server-rendered, cached 30 seconds | Intro text and the platform status, fetched by the server from the API |
| `/home` | Signed in, client component | A greeting and the API status, fetched by the browser through the proxy |
| `/profile` | Signed in, client component | Your GitHub account, its connection status, and Sign out |

## Run everything locally

```powershell
docker compose -f infra/compose/compose.yaml up --build
```

Then open http://localhost:8080 for the site and http://localhost:8080/api/v1/health for the API. The health check answers 200 when Postgres and Redis are reachable and 503 when one is not. The `worker` field shows `ok`, `stale` or `missing` but does not cause a 503, so a stopped worker is visible without taking the site down.

## Sign-in

People sign in with GitHub through a GitHub App. Nothing else is needed: no passwords, no separate account.

1. Create a GitHub App for development: GitHub, Settings, Developer settings, GitHub Apps, New GitHub App.
   - Homepage URL: `http://localhost:8080`
   - Callback URL: `http://localhost:8080/api/v1/auth/github/callback`
   - Expire user authorization tokens: ticked
   - Request user authorization (OAuth) during installation: unticked
   - Webhook, Active: unticked (webhooks come in Step 3)
   - Account permissions: Email addresses, read-only. Nothing else yet.
   - Where can this app be installed: Only on this account
2. On the app's page, copy the Client ID and generate a client secret.
3. Copy `infra/compose/.env.example` to `infra/compose/.env` and fill in the client ID, the secret and a token key (the file says how to make one).
4. `docker compose -f infra/compose/compose.yaml up --build`, open http://localhost:8080 and click Sign in with GitHub.

How it works:

- `GET /api/v1/auth/github/login` sends the browser to GitHub with a one-time `state` (also kept in a cookie on this browser) and a PKCE challenge. Each IP address gets at most 20 sign-in attempts every 10 minutes (`FIRSTPR_LOGIN_ATTEMPTS_PER_10_MINUTES`).
- `GET /api/v1/auth/github/callback` checks the state, swaps the code for a user token and a refresh token, saves the user, and starts a session. It then sends the browser back to where it started, but only to paths on this site.
- GitHub tokens are encrypted with Fernet before they reach the database (`FIRSTPR_TOKEN_KEYS`, newest key first, so keys can be rotated). They are never logged and never sent to the browser.
- The session cookie is HTTP-only and SameSite=Lax. The database stores only a SHA-256 of it. Sessions last 30 days and are extended while used. Redis caches them, and signing out deletes both, so a copied cookie stops working at once.
- Every request that changes something needs the `X-CSRF-Token` header to match the `firstpr_csrf` cookie.
- `GET /api/v1/me` checks with GitHub at most every 5 minutes that access still works, refreshing the 8-hour token when it is about to run out. If GitHub says no (the app was revoked, or the refresh token expired), the account is marked "reconnect needed" and the site shows the reconnect banner. Signing in again fixes it.

Database changes are Alembic migrations in `apps/api/migrations`. The API container applies them when it starts; CI checks that they match the models.

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

## Import rules

`.importlinter` at the repository root says which code may import which, and CI checks it with `lint-imports`:

- the engine (`issueradar`) never imports the platform apps
- the API and the worker never import each other
- scoring (`issueradar.engine`) never touches GitHub, the database or any interface
- the GitHub client never depends on anything built on top of it

To run it locally, install all three packages and import-linter, then run `lint-imports` from the repository root:

```powershell
python -m pip install -e . -e "apps/api[dev]" -e "apps/worker[dev]" import-linter
lint-imports
```
