# Run FirstPR on GitHub Actions

The easiest way to get a daily digest without leaving a computer on. A
scheduled workflow in a repo of your own runs FirstPR once a day and puts the
digest on the run page, in a downloadable artifact, and in any channel you
turn on.

## Use the template (recommended)

1. Create a new repo from the template:
   [MuskanScripts/firstpr-radar-template](https://github.com/MuskanScripts/firstpr-radar-template)
   (**Use this template**). Private is fine.
2. Edit `watchlist.txt` (one repo per line) and `skills.yaml`.
3. **Actions > Daily digest > Run workflow** to try it straight away.

The template's files live in [`template/`](../template) in this repo, so you can
also copy them by hand into any repo you like.

## Add it to an existing workflow

```yaml
- uses: actions/checkout@v4
- uses: MuskanScripts/IssueRadar@v0
  with:
    token: ${{ secrets.FIRSTPR_GITHUB_TOKEN || github.token }}
    watchlist: watchlist.txt
```

### Inputs

| Input | Default | What it does |
| --- | --- | --- |
| `token` | `github.token` | Token for reading GitHub. See "Which token" below. |
| `watchlist` | `watchlist.txt` | One repo per line. `#` starts a comment. Removing a line stops watching that repo. |
| `config` | `firstpr.yaml` | Your settings. Skipped if missing. |
| `skills` | `skills.yaml` | Your skill profile. Skipped if missing. |
| `author` | the repo owner | Whose pull requests to track. Empty skips PR tracking. |
| `version` | empty | A PyPI version to install, for example `0.1.0`. Empty uses the code that ships with the action tag. |
| `python-version` | `3.13` | Python to run with. |
| `upload-artifact` | `true` | Upload `digests/` as the `firstpr-digest` artifact. |

Output: `digest`, the path of the Markdown digest (`digests/latest.md`).

### Delivery secrets

Channels are turned on in `firstpr.yaml`. Their secrets are passed as `env`
on the step, and only the names below are read:

```yaml
  env:
    FIRSTPR_SMTP_PASSWORD: ${{ secrets.FIRSTPR_SMTP_PASSWORD }}
    FIRSTPR_TELEGRAM_TOKEN: ${{ secrets.FIRSTPR_TELEGRAM_TOKEN }}
    FIRSTPR_DISCORD_WEBHOOK: ${{ secrets.FIRSTPR_DISCORD_WEBHOOK }}
    FIRSTPR_SLACK_WEBHOOK: ${{ secrets.FIRSTPR_SLACK_WEBHOOK }}
```

## What happens on each run

1. Installs FirstPR into the runner's Python.
2. Restores the database from the Actions cache (ETags, what was already sent,
   your PR history). Without it every run would be a cold start and you would
   get the same issues every day.
3. Applies `watchlist.txt`, then runs `firstpr daily`: sync, your pull
   requests, digest.
4. Saves the database back to the cache, even if a step failed.
5. Uploads `digests/` as an artifact and writes the digest to the run summary.

The job fails (red) if any step had a problem, but the digest and the database
are still saved, so the next run picks up where this one stopped.

## Which token

The built-in `GITHUB_TOKEN` works for public repos, and the template uses it
when there is no `FIRSTPR_GITHUB_TOKEN` secret. It has a lower rate limit and
GitHub does not document exactly what it may read outside its own repo. The
[self-test workflow](../.github/workflows/action-selftest.yml) runs the action
with nothing but `GITHUB_TOKEN` against this repo and
`modelcontextprotocol/python-sdk` on every change, and records the result in
[RESULTS.md](../RESULTS.md).

For more than a handful of repos, create a fine-grained token with **no extra
permissions** (public repositories, read-only, steps in
[human-tasks.md](human-tasks.md#create-the-least-privileged-token)) and save it
as the repo secret `FIRSTPR_GITHUB_TOKEN`. See [ADR 0006](adr/0006-pat-for-action-template.md).

`GITHUB_TOKEN` cannot call `/user`, so PR tracking needs `author`. The template
fills it with the repo owner.

## Things to know

- Scheduled runs use UTC and may start a few minutes late.
- GitHub turns off schedules in repos with no activity for 60 days. Running
  the workflow by hand turns it back on.
- Caches unused for 7 days are deleted. After a long pause the first run is a
  cold start: it may repeat a few issues you already saw.
- The action only reads. Its job token needs `contents: read` and nothing else.
