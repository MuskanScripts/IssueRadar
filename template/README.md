# My FirstPR radar

This repo runs [FirstPR](https://github.com/MuskanScripts/IssueRadar) once a day
on GitHub Actions. It looks at the repositories in `watchlist.txt`, skips issues
someone has already claimed, ranks the rest for your level and stack, checks on
your open pull requests, and writes a short digest.

It only reads from GitHub. It never comments, opens issues or touches the
repositories you watch.

## Set it up (about five minutes)

1. Click **Use this template** and create your own copy (public or private).
2. Edit `watchlist.txt`: one repo per line.
3. Edit `skills.yaml`: your languages, frameworks and how well you know them.
4. Optional: turn on email, Telegram, Discord or Slack in `firstpr.yaml` and add
   the matching secret under **Settings > Secrets and variables > Actions**.
5. Go to **Actions > Daily digest > Run workflow** to try it now.

## Where the digest shows up

- On the run's summary page (open the run in the Actions tab).
- As a downloadable `firstpr-digest` artifact with `latest.md` and `feed.xml`.
- In any channel you turned on in `firstpr.yaml`.

## Token

The built-in `GITHUB_TOKEN` can read public repositories, so nothing is needed
to start. Search has a lower limit with it. If you watch many repos, create a
fine-grained token with **no extra permissions** (public repositories,
read-only) and save it as the secret `FIRSTPR_GITHUB_TOKEN`. The workflow picks
it up on its own.

PR tracking follows the account that owns this repo. Change it with the
`author` input in `.github/workflows/daily-digest.yml`.

## Change the time

Edit the `cron` line in `.github/workflows/daily-digest.yml`. It is in UTC.
GitHub may start scheduled runs a few minutes late, and turns schedules off
in repos with no activity for 60 days. Running the workflow by hand turns it
back on.
