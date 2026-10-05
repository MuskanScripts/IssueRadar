# Platform apps

The FirstPR platform (the hosted website) is built here. The engine it shares with the self-hosted CLI lives in `packages/core`.

| Folder | What it is | Run it with |
|---|---|---|
| `api/` | FastAPI app under `/api/v1`: health, GitHub sign-in, sessions, `/me`, onboarding, today's pick, Explore, issue pages, workspaces and pull requests, watched repos, admin, GitHub webhooks | `uvicorn --factory firstpr_api.main:create_app` |
| `worker/` | Arq worker on Redis: syncs the shared catalogue and people's own repos, rebuilds the issue cards, holds daily picks, sets up workspaces, handles webhooks | `arq firstpr_worker.main.WorkerSettings` |
| `web/` | Next.js app. Public pages are server-rendered and cached; pages after sign-in are client components that call the API | `npm run dev` |

Code both the API and the worker need (database tables, migrations, GitHub sign-in, the app's token, fit and daily picks) is in `packages/platform` (`firstpr_platform`). Both also use the engine in `packages/core`: the worker to sync and score, the API for skill lists and fit.

In front of them, a Caddy proxy (`infra/compose/Caddyfile`) puts everything on one address: `/api/*` goes to FastAPI, everything else to Next.js. One address means the session cookie works on every page with no extra setup.

| Route | Kind | What it shows today |
|---|---|---|
| `/` | Public, server-rendered, cached 30 seconds | Intro text and the platform status, fetched by the server from the API |
| `/onboarding` | Signed in, client component | Three short, skippable steps: level, skills, starter packs. New people land here first |
| `/home` | Signed in, client component | Today's pick, why it was picked, how long it is held, Show me another, today's minutes, streak, XP and a 17-week calendar |
| `/explore` | Signed in, client component | Every open issue nobody holds, with filters, best fit / recently active / shuffled order, Load more, and Refresh |
| `/issues/<owner>/<repo>/<number>` | Signed in, client component | Why it is free, why it suits you, what to do first, repo health; checked live on GitHub when our copy is over 10 minutes old |
| `/workspaces` | Signed in, client component | My work: the issues you started, with their state, and the practice-repo rule |
| `/workspaces/<id>` | Signed in, client component | The setup steps live, Open your Codespace or clone instructions, I finished (commits and files), and the Create pull request form |
| `/progress` | Signed in, client component | XP, streak with the weekly freeze, today's minutes, the full-year activity calendar, badges and recent XP |
| `/pulls` | Signed in, client component | My pull requests: Needs you, Waiting on others, Done, with what to do, recent activity, a nudge to copy for quiet ones, and Check now |
| `/notifications` | Signed in, client component | Everything FirstPR told you; the bell in the menu shows the unread count live |
| `/settings` | Signed in, client component | Email on or off, the daily digest, and a link to change level and skills |
| `/email-off` | Public | Where the unsubscribe link in every email lands |
| `/leaderboard`, `/paths` | Signed in, client component | Coming-soon placeholders with an "I want this" button |
| `/profile` | Signed in, client component | Stats, the full-year calendar, merged pull requests, skills, connected GitHub status, the public/private switch, Settings and Sign out |
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
   - Setup URL: `http://localhost:8080/api/v1/github/installed`, with Redirect on update ticked
   - Webhook, Active: unticked (GitHub cannot reach localhost)
   - Repository permissions: Administration, Contents, Pull requests and Codespaces read and write (for Start working, see below); Issues and Metadata read-only. Account permissions: Email addresses, read-only.
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

## Daily pick and Explore

After every sync the worker turns each open issue into an issue card (`issue_cards`): the engine's verdicts on availability, level, time and repo health, plus the repo's stack. The API reads only these cards, so no page runs the engine. When there are no cards yet (the first start after an upgrade), the worker builds them from what earlier syncs stored.

Fit is worked out per user on each request, from the cards and what the user chose in onboarding, with the engine's own pieces: tier fit against the chosen level, stack match against their skills, repo health, freshness and how many people already commented (`firstpr_platform.picks`). It is shown as a percentage, with the reasons in plain words.

- **Today's pick** is made on the first visit of the user's local day (their browser's time zone), or by the worker every 15 minutes for people active in the last 14 days. It comes from their starter packs (all catalogue repos when they chose none) and their own watched repos.
- **Holds:** a pick is held for 48 hours. A unique index allows one active hold per issue, so two people are never sent to the same issue. Held issues disappear from everyone else's Explore. A new day releases yesterday's pick if it was not started.
- **Show me another** releases the pick and holds the next best one, at most 3 times a day. A swapped issue does not come back.
- **Explore** lists open issues nobody else holds, with filters for level, skill, language and freshness, sorted by fit, recent activity or a shuffle seed, paged with a cursor.
- **Refresh** on Explore queues a sync of the user's own repos with their token and of the catalogue (at most once in 5 minutes for everyone), then shows how many issues changed since.
- **Logging:** every pick shown, swapped or opened, and every click to GitHub, goes to `recommendation_events` with the fit and its parts, for a learned ranking later.
- **Coming soon:** placeholders sit where later features will live. "I want this" clicks are stored once per user and counted on `/admin`.

## Workspaces and pull requests

From an issue page, **Start working** sets everything up in the user's own GitHub account, in the worker, with their own token:

1. Check the FirstPR GitHub App is installed on their account. If it is not, the page shows an Install button (`https://github.com/apps/<FIRSTPR_GITHUB_APP_SLUG>/installations/new`); after installing, GitHub sends them back to the same issue through the app's Setup URL. They should choose **All repositories**, so the app can see the fork it makes.
2. Fork the repo, or reuse their fork, and bring it up to date with upstream.
3. Create a branch, `firstpr/<number>-<title>`.
4. Start a Codespace on that branch with a 15-minute idle timeout and a 7-day retention period. Or skip it with **Work on my computer**.

The workspace page follows the steps live (server-sent events, with polling as a fallback). When a Codespace cannot be created or does not start (no hours left, a broken dev container), the workspace falls back to clone instructions instead of an error. The issue stays held for the user while they work on it (30 days), and survives a new day.

**I finished** compares the branch with where it started and lists the commits and changed files. **Create pull request** opens a form with the title and `Fixes #<number>` filled in, starting from the repo's own pull request template when it has one. Nothing is sent until the user clicks. When GitHub does not let the app open the pull request on the upstream repo (the app is not installed there), the page gives them GitHub's own form, already filled in, and FirstPR picks the pull request up within a few minutes.

Rules:

- At most 3 open pull requests at a time (`FIRSTPR_MAX_OPEN_PRS`).
- When `FIRSTPR_PRACTICE_REPO` is set (for example a repo of easy practice issues you own and add to the catalogue), a person's first pull request has to go there before they can open one on a real project. Empty turns the rule off.
- **No GitHub write without a click.** Forking, syncing the fork, creating the branch and the Codespace, opening the pull request and deleting the Codespace all go through one `_write` method in `firstpr_platform.github_user`, called only from the user's own POST (Start working, Try again, Create pull request, Stop working). Scheduled jobs only read: every 5 minutes the worker checks Codespace states and looks for pull requests opened on GitHub's form. A test runs every scheduled job and checks GitHub saw no writes. GitHub itself stops idle Codespaces and deletes old ones, so FirstPR never has to.

## Pull requests and notifications

The worker tracks each user's pull requests with their own token and the engine's PR tracker (`packages/core`, the same status rules as the CLI): the ones opened through FirstPR, and a search for their other public pull requests of the last 90 days. Private repos are never searched.

| When | What |
|---|---|
| Every 2 hours | Everyone active in the last 14 days |
| A few seconds after a webhook | The one pull request it is about (reviews, comments, checks, pushes); only for repos where the app is installed, such as your practice repo |
| Right after Create pull request | That pull request |
| Check now on My PRs | The user's pull requests, at most once in 5 minutes |

A change of status becomes a notification: merged, changes requested, checks failing, merge conflict, approved, gone quiet (with a nudge drafted to copy, never posted), closed. The first time a pull request is seen is not news. Workspace problems (setup stopped, or no Codespace) are notifications too. The same change never makes two notifications, even when GitHub sends a webhook twice.

The bell in the menu follows `/api/v1/me/notifications/stream` (server-sent events) for a live unread count. The proxy does not compress `/api`, and Next.js does not compress either, so the stream is not held back.

Email goes through [Resend](https://resend.com) (`FIRSTPR_RESEND_API_KEY`, `FIRSTPR_EMAIL_FROM` on a domain you verified there). Without a key nothing is sent.

- Straight away: merged, changes requested, workspace problems.
- Everything else waits for the daily digest at 8 in the morning in the user's time zone, sent only on days with something new.
- Every email goes through one function that checks the user's switch first, so turning email off in Settings stops every email.
- Every email has a one-click unsubscribe link (signed with a key derived from `FIRSTPR_TOKEN_KEYS`) and the `List-Unsubscribe` headers mail apps use for their own Unsubscribe button.

## XP, streaks and the activity calendar

**XP** is for accepted work only, and only the worker writes it, when the PR tracker sees the change: +100 for a merged pull request, +20 when one is approved, +30 for the practice task. Pull requests opened through FirstPR count from the start; other pull requests only for changes FirstPR saw happen (an old merge found by the first search earns nothing). Each award is stored with what earned it (`xp_transactions`, unique per user and source), so a webhook that arrives twice still pays once. The total is kept on the user.

**Badges**: First pull request, Warmed up (practice), Merged, Hat trick (3 merged), Explorer (merged in 3 repos), Seven days (a 7-day streak). They are checked after XP and after activity is saved, and each is a notification in the app.

**Active minutes** come from three layers:

1. The site: once a minute the page sends a heartbeat, but only while its tab is visible and the user did something in the last 2 minutes. The API checks both again and counts at most one minute per 55 seconds, in Redis under the user's own calendar day (their time zone, so 23:50 counts that day). The worker moves the counts to `daily_activity` every 10 minutes.
2. Codespaces: the 5-minute workspace check notes when a Codespace was first and last seen running. When it stops, the run minus the 15 idle minutes before the automatic stop is added to the day it started.
3. Commits: commits pushed to FirstPR branches are added to the day they were made, each once.

There is no VS Code extension yet (it is a coming-soon placeholder).

A day is **green** at 15 active minutes or a pushed commit. The **streak** is green days in a row; today counts once it is green. One missed day a week (Monday to Sunday) is bridged by a free **freeze** when the days on both sides are green; frozen days are marked on the calendar.

## Admin

GitHub logins in `FIRSTPR_ADMIN_LOGINS` (comma-separated) get the admin role when they sign in, and an Admin link appears in the menu. `/admin` shows every synced repo (problems first), which token it uses, how many people watch it, the last result, the GitHub budgets, webhook counts, how many issue cards are ready, and the "I want this" counts. Admins can add and remove catalogue repos there.

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
