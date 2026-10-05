# Platform apps

The FirstPR platform (the hosted website) is built here. The engine it shares with the self-hosted CLI lives in `packages/core`.

| Folder | What it is | Run it with |
|---|---|---|
| `api/` | FastAPI app under `/api/v1`: health, GitHub sign-in, sessions, `/me`, watched repos, admin, GitHub webhooks | `uvicorn --factory firstpr_api.main:create_app` |
| `worker/` | Arq worker on Redis: syncs the shared catalogue and people's own repos, handles webhooks | `arq firstpr_worker.main.WorkerSettings` |
| `web/` | Next.js app. Public pages are server-rendered and cached; pages after sign-in are client components that call the API | `npm run dev` |

Code both the API and the worker need (database tables, migrations, GitHub sign-in and the app's token) is in `packages/platform` (`firstpr_platform`). The worker also uses the engine in `packages/core`.

In front of them, a Caddy proxy (`infra/compose/Caddyfile`) puts everything on one address: `/api/*` goes to FastAPI, everything else to Next.js. One address means the session cookie works on every page with no extra setup.

| Route | Kind | What it shows today |
|---|---|---|
| `/` | Public, server-rendered, cached 30 seconds | Intro text and the platform status, fetched by the server from the API |
| `/home` | Signed in, client component | A greeting and the API status, fetched by the browser through the proxy |
| `/profile` | Signed in, client component | Your GitHub account, its connection status, and Sign out |
| `/admin` | Admins only, client component | Every synced repo with its token, watchers and last result, the GitHub budgets, webhooks, and adding or removing catalogue repos |

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

Database changes are Alembic migrations in `packages/platform/migrations`. The API container applies them when it starts (`python -m firstpr_platform.migrate`); CI checks that they match the models.

## Sync

The worker keeps repos and issues fresh without anyone clicking anything.

| Repos | Token | When |
|---|---|---|
| The shared catalogue (starter packs, plus repos admins add), and any repo two or more people watch | The GitHub App's installation token | Every 30 minutes (:00 and :30), and a minute after a webhook for one of them |
| A repo only one person watches | That person's own token, on their behalf | Every 30 minutes (:15 and :45) for people who used the site in the last 14 days, a few seconds after they add a repo, and a minute after a webhook |

- The sync itself is the engine's (`packages/core`): stable ordering so unchanged pages come back as free 304s, one transaction per repo, and an interrupted run carries on where it stopped. The engine keeps its tables (repos, issues, PRs, ETags) in a second database, `firstpr_catalogue`.
- The installation token changes every hour. The engine's ETag cache is keyed by "app" (or "user:<id>") instead of the token, so the 304s keep working after each change.
- When less than 20% of a token's hourly limit is left (`FIRSTPR_BUDGET_PAUSE_SHARE`), the sync stops starting new requests. The repos it did not reach show as "paused" on /admin and are done in the next run.
- Private repos are refused when someone tries to watch one. FirstPR is for open source, and it means no private data is ever stored.
- An empty catalogue is filled from the starter packs when the worker starts.

To turn on the catalogue sync, give the worker the GitHub App's ID and private key (`FIRSTPR_GITHUB_APP_ID`, `FIRSTPR_GITHUB_APP_PRIVATE_KEY`, see `infra/compose/.env.example`) and install the app on your account. Until then the catalogue sync is skipped and says so.

## Webhooks

`POST /api/v1/webhooks/github` checks each delivery's `X-Hub-Signature-256` against `FIRSTPR_GITHUB_WEBHOOK_SECRET`, stores it once (GitHub can deliver the same one twice) and queues it for the worker, so GitHub always gets a quick answer. The worker then:

- for issue, pull request, comment and repository events on a synced repo, queues that repo's sync a minute later (several events in that minute become one sync)
- for `github_app_authorization` with `revoked`, marks that person's account "reconnect needed" straight away

To receive them, set the app's webhook URL to `https://<your site>/api/v1/webhooks/github`, set the same secret on both sides, and subscribe to Issues, Issue comments, Pull requests, Pull request reviews and Repository.

## Admin

GitHub logins in `FIRSTPR_ADMIN_LOGINS` (comma-separated) get the admin role when they sign in, and an Admin link appears in the menu. `/admin` shows every synced repo (problems first), which token it uses, how many people watch it, the last result, the GitHub budgets, and webhook counts. Admins can add and remove catalogue repos there.

## Develop without Docker

```powershell
python -m pip install -e . -e "packages/platform[dev]" -e "apps/api[dev]" -e "apps/worker[dev]"
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

- the engine (`issueradar`) never imports the platform
- shared platform code (`firstpr_platform`) never imports the API or the worker
- the API and the worker never import each other (the API queues worker jobs by name)
- scoring (`issueradar.engine`) never touches GitHub, the database or any interface
- the GitHub client never depends on anything built on top of it

To run it locally, install all three packages and import-linter, then run `lint-imports` from the repository root:

```powershell
python -m pip install -e . -e "packages/platform[dev]" -e "apps/api[dev]" -e "apps/worker[dev]" import-linter
lint-imports
```
