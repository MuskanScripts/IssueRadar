# Deploying FirstPR

There are two ways to run the hosted platform. They run the same code:

| | Render (managed) | One server (VPS) |
| --- | --- | --- |
| File | [`render.yaml`](../render.yaml) | [`infra/compose/compose.prod.yaml`](../infra/compose/compose.prod.yaml) |
| HTTPS | Render's own, plus your domain | Caddy, automatic (Let's Encrypt) |
| Postgres, Redis | Render Postgres and Key Value | Containers with volumes |
| Backups | Render's daily backups, plus `scripts/backup.sh` | `scripts/backup.sh` from cron |
| Cost to start | About $7 a month per service, plus the database | One small VPS |

Both need the same GitHub App and the same secrets. Do the GitHub App first.

## 1. The production GitHub App

Use a separate app from the one on your laptop, so local testing never touches real users.
On github.com/settings/apps/new (or under your organisation):

| Field | Value |
| --- | --- |
| Homepage URL | `https://<your-domain>` |
| Callback URL | `https://<your-domain>/api/v1/auth/github/callback` |
| Request user authorization (OAuth) during installation | off |
| Expire user authorization tokens | on |
| Webhook URL | `https://<your-domain>/api/v1/webhooks/github` |
| Webhook secret | a long random string; the same value goes in `FIRSTPR_GITHUB_WEBHOOK_SECRET` |
| Repository permissions | Administration, Contents, Pull requests and Codespaces: read and write; Issues and Metadata: read-only |
| Account permissions | Email addresses: read-only |
| Subscribe to events | Issues, Issue comment, Pull request, Pull request review, Repository |
| Where can it be installed | Any account |

Then generate a client secret and a private key. Install the app on your own account
(all repositories) so the catalogue sync has an installation to use.

## 2a. Render

1. Push this repo to GitHub. In Render: **New → Blueprint**, pick the repo. Render reads `render.yaml`
   and shows five resources: `firstpr-web` (public), `firstpr-api` (private), `firstpr-worker`,
   `firstpr-redis` and the `firstpr-db` Postgres.
2. Render asks for every value marked `sync: false`. Fill them in from the table in section 3.
   `FIRSTPR_PUBLIC_URL` and `SITE_URL` are the web service's address
   (`https://firstpr-web.onrender.com` until you add a domain).
3. Deploy. The API applies the database migrations on start, and the worker creates the
   `firstpr_catalogue` database on first start. If your database user cannot create databases,
   create it once in the Render shell (`CREATE DATABASE firstpr_catalogue;`) or set
   `FIRSTPR_CATALOGUE_DATABASE_URL` to another database.
4. **Custom domain:** on `firstpr-web` → Settings → Custom Domains, add `firstpr.dev` (or yours),
   add the DNS records Render shows, wait for the certificate. Then change `FIRSTPR_PUBLIC_URL`,
   `SITE_URL` and the GitHub App's URLs to the new address and redeploy.

Only the web service is reachable from the internet. It forwards `/api/*` to the API over
Render's private network (`API_INTERNAL_HOSTPORT`, set by the Blueprint), so cookies, the
GitHub callback and webhooks all use one address.

**Staging:** create a second Blueprint from the same repo on a `staging` branch, with its own
GitHub App, `FIRSTPR_ENVIRONMENT=staging` and `FIRSTPR_INVITE_ONLY=true`. Merge to `staging`
first, click through the checks in section 6, then merge to `main`.

## 2b. One server with Docker Compose

On a fresh Ubuntu server with Docker installed:

```sh
git clone https://github.com/MuskanScripts/IssueRadar.git && cd IssueRadar
cp infra/compose/.env.example infra/compose/.env
nano infra/compose/.env          # fill in section 3, plus DOMAIN and POSTGRES_PASSWORD
docker compose -f infra/compose/compose.prod.yaml --env-file infra/compose/.env up -d --build
```

Point the domain's A (and AAAA) record at the server before starting; Caddy fetches the
certificate on its own and renews it. Open ports 80 and 443 only (`ufw allow 80,443/tcp`).
Postgres and Redis are never published.

To update: `git pull && docker compose -f infra/compose/compose.prod.yaml --env-file infra/compose/.env up -d --build`.

**CDN:** optional. If you put Cloudflare in front, use "Full (strict)" TLS, turn off
"Rocket Loader" (it breaks the CSP) and add a cache bypass rule for `/api/*`, so live
streams and signed-in answers are never cached.

## 3. Settings

All Python settings start with `FIRSTPR_`. The minimum to sign in and get a daily pick is the
first block; each later one turns on one more feature and does nothing when empty.

| Variable | Service | Needed for |
| --- | --- | --- |
| `DATABASE_URL` | API, worker | Always. `postgres://` URLs from hosts are accepted as they are |
| `REDIS_URL` | API, worker | Always |
| `PUBLIC_URL` | API, worker | Always. The address people use; https means secure cookies |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | API, worker | Sign-in |
| `TOKEN_KEYS` | API, worker | Sign-in (encrypts GitHub tokens) |
| `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY` | worker | The shared catalogue sync, maintainer opt-outs |
| `GITHUB_APP_SLUG` | API | "Install FirstPR" link before Start working |
| `GITHUB_WEBHOOK_SECRET` | API | Webhooks (PR status within seconds) |
| `PRACTICE_REPO` | API | The practice rule for the first pull request |
| `RESEND_API_KEY`, `EMAIL_FROM` | API, worker | Email notifications and the daily digest |
| `POSTHOG_KEY`, `POSTHOG_HOST` | API, worker | The sign-up funnel |
| `SENTRY_DSN`, `ENVIRONMENT` | API, worker | Error reports |
| `ADMIN_LOGINS` | API | `/admin` |
| `INVITE_ONLY`, `INVITE_LOGINS`, `WAITLIST_URL` | API | The tester phase |
| `METRICS_TOKEN` | API | `/api/v1/metrics` for Prometheus |
| `SITE_URL`, `FEEDBACK_URL` | web (no prefix) | Sitemap and link previews; where "Send feedback" goes |

Make the keys with:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # TOKEN_KEYS
python -c "import secrets; print(secrets.token_urlsafe(32))"                                 # webhook secret, METRICS_TOKEN
```

Rotate `TOKEN_KEYS` by putting a new key in front (`new,old`); old tokens still decrypt.

## 4. Watching it

**Errors:** create a Sentry project (Python) and set `FIRSTPR_SENTRY_DSN` on the API and worker.
Errors in the browser are sent to `POST /api/v1/client-errors`, which forwards them to the same project.

**Uptime:** point an uptime checker (UptimeRobot, Better Stack) at `https://<domain>/api/v1/health`
every minute. It answers 503 when Postgres or Redis is down; a stopped worker shows as
`"worker": "stale"` in the answer and fires the `FirstPRWorkerStopped` alert.

**Metrics and alerts:** set `FIRSTPR_METRICS_TOKEN`, then scrape `/api/v1/metrics` with
`Authorization: Bearer <token>`. [`infra/monitoring/prometheus.yml`](../infra/monitoring/prometheus.yml)
is a scrape config and [`alerts.yml`](../infra/monitoring/alerts.yml) has the rules: API down,
error rate over 2%, worker stopped, queue backed up, GitHub budget under 10%, workspace failures.
Without the token the endpoint is a 404.

## 5. Backups and the restore drill

```sh
scripts/backup.sh                                   # VPS: dumps both databases into ./backups
DATABASE_URL="$RENDER_EXTERNAL_URL" scripts/backup.sh   # Render: from your laptop
```

Run it daily from cron (`15 3 * * * cd /srv/IssueRadar && scripts/backup.sh`) and copy `backups/`
somewhere else (`rclone`, S3). Practise a restore once before launch, on staging:

```sh
createdb restore_test
pg_restore --no-owner -d restore_test backups/firstpr-<stamp>.dump
psql restore_test -c "select count(*) from users"
```

The catalogue database can always be rebuilt by the worker; the platform database cannot.

## 6. Launch checklist

- [ ] Production GitHub App made, installed on your account, URLs on the real domain
- [ ] `FIRSTPR_PUBLIC_URL` is https and `FIRSTPR_COOKIE_SECURE` is true (the API refuses to start otherwise)
- [ ] `/api/v1/health` is 200 and the uptime check is green
- [ ] Sign in, finish onboarding, get a daily pick, Start working, open a pull request on the practice repo
- [ ] A webhook delivery shows 202 on the GitHub App's Advanced tab
- [ ] An email arrives, and its Unsubscribe link works
- [ ] A test error shows up in Sentry
- [ ] `/u/<you>` and `/i/...` show link previews (try the URL in a chat app)
- [ ] `/maintainers` reads right, and `.github/firstpr.yml` with `opt_out: true` removes a test repo within a day
- [ ] Delete account works on a throwaway GitHub account
- [ ] A backup was taken and restored
- [ ] `FIRSTPR_INVITE_ONLY=true` with the first testers in `FIRSTPR_INVITE_LOGINS`

## 7. Security notes

- Every response carries `X-Content-Type-Options`, `X-Frame-Options: DENY` and a CSP; the site
  adds `Strict-Transport-Security` through Caddy or Render.
- GitHub tokens are encrypted at rest; sessions live in Redis behind an HTTP-only cookie; every
  write checks a CSRF token.
- Nothing scheduled writes to GitHub. Forks, branches, Codespaces and pull requests only happen
  on a person's click.
- Maintainers can opt a repo out with `.github/firstpr.yml` (`opt_out: true`); the worker checks once a day.
- Report problems as described in [SECURITY.md](../SECURITY.md).
