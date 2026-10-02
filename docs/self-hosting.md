# Self-hosting

Three ways to run FirstPR on your own machine or server. All of them keep your
token in an environment variable and only read from GitHub.

## 1. pip (Windows, macOS, Linux)

```powershell
py -3.13 -m pip install firstpr
firstpr init                      # writes firstpr.yaml and skills.yaml here
$env:FIRSTPR_GITHUB_TOKEN = "your-read-only-token"
firstpr watch add modelcontextprotocol/python-sdk
firstpr daily
firstpr serve                     # dashboard at http://127.0.0.1:8765
```

The wheel includes the built dashboard, so Node is not needed.

### Run it every morning on Windows

Task Scheduler runs `firstpr daily` once a day. Store the token for your user
first (see [human-tasks.md](human-tasks.md#create-the-least-privileged-token)),
then:

```powershell
$folder = "$HOME\firstpr"           # where firstpr.yaml and skills.yaml live
$action = New-ScheduledTaskAction -Execute "firstpr.exe" -Argument "daily" -WorkingDirectory $folder
$trigger = New-ScheduledTaskTrigger -Daily -At 7:30am
Register-ScheduledTask -TaskName "FirstPR daily" -Action $action -Trigger $trigger
```

On macOS or Linux, a cron line or a systemd timer that runs `firstpr daily` in
that folder does the same job.

## 2. Docker Compose

Needs Docker with Compose. From a clone of this repo:

```powershell
Copy-Item .env.example .env        # then put your token in .env
notepad config\skills.yaml
docker compose up -d
docker compose exec app firstpr watch add modelcontextprotocol/python-sdk
```

- `app` serves the dashboard and API on http://127.0.0.1:8765. The port is
  bound to localhost only; put a reverse proxy with authentication in front
  if you want it elsewhere. The API has no login.
- `daily` runs `firstpr daily` once a day (sync, your pull requests, digest).
- The database and the digests live in the `data` volume, in `/data`. Copy
  the latest digests out with `docker compose cp daily:/data/digests .`
- Settings come from `./config` (mounted read-only). Secrets only come from
  `.env`.

To update: `docker compose pull; docker compose up -d`.

The image runs as a non-root user, has a health check on `/api/health`, and is
published as `ghcr.io/muskanscripts/issueradar` on every release.

## 3. GitHub Actions

No server at all. See [github-action.md](github-action.md).

## Where things are stored

| What | pip | Docker |
| --- | --- | --- |
| Database | your user data folder (`firstpr doctor` prints it), or `FIRSTPR_DB_URL` | `/data/firstpr.sqlite` in the volume |
| Digests | `./digests` | `/data/digests` in the volume |
| Settings | `firstpr.yaml`, `skills.yaml` in the working folder | `./config` |
| Token | `FIRSTPR_GITHUB_TOKEN` | `.env` |

`firstpr export` writes everything FirstPR stored about you to one JSON file.
Deleting the database file removes it all.
