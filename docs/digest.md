# The daily digest

```powershell
firstpr digest                     # preview in the terminal; nothing is remembered
firstpr digest --format markdown   # preview as Markdown (or html)
firstpr digest --send              # deliver through every switched-on channel
```

## What's in it

1. **Free for you**: the top 5 ranked free issues you haven't been sent yet.
2. **Your pull requests**: your open PRs and what each needs (from the PR tracker),
   plus any that were merged or closed in the last 24 hours. The very first digest
   with PRs shows only the open ones, so it doesn't start with a backlog.
3. **New since yesterday**: other free issues that first appeared in the last 24 hours.
4. **Watchlist alerts**: a watched repo was archived, had no push for 60 days, or failed to sync.
5. **Quiet day**: when there's nothing new and nothing was sent yet today, a short note instead.

An item is sent once. It comes back only if what you'd see changed (its
availability, level or title for issues; its status for pull requests). Hide
items with:

```powershell
firstpr dismiss https://github.com/owner/repo/issues/123            # never again
firstpr snooze https://github.com/owner/repo/issues/123 --days 7    # back in a week
```

Running `firstpr digest --send` twice in a row sends nothing the second time.

## Channels

RSS and Markdown are on by default and need no setup. They write to the
`digests/` folder where you run the command:

- `digests/latest.md` and `digests/YYYY-MM-DD.md`
- `digests/feed.xml`, an RSS feed (newest 30 digests) you can add to any feed reader

The others are off until you switch them on in `firstpr.yaml`. Secrets never go
in the file; they come from environment variables.

### Email (SMTP)

```yaml
digest:
  channels:
    email:
      enabled: true
      smtp_host: smtp.example.com
      smtp_port: 587
      username: you@example.com
      sender: you@example.com
      recipient: you@example.com
```

```powershell
$env:FIRSTPR_SMTP_PASSWORD = "an app password, not your main password"
```

The email has a plain-text and an HTML part.

### Telegram

Create a bot with @BotFather, send it a message, then find your chat id.

```yaml
digest:
  channels:
    telegram:
      enabled: true
      chat_id: "123456789"
```

```powershell
$env:FIRSTPR_TELEGRAM_TOKEN = "123456:ABC..."
```

### Discord and Slack

Create an incoming webhook in the channel's settings, then:

```yaml
digest:
  channels:
    discord:
      enabled: true
    slack:
      enabled: true
```

```powershell
$env:FIRSTPR_DISCORD_WEBHOOK = "https://discord.com/api/webhooks/..."
$env:FIRSTPR_SLACK_WEBHOOK = "https://hooks.slack.com/services/..."
```

Long digests are split into several messages to stay under each service's limit.

## Safety

The delivery code refuses to send anything to a GitHub address, and a test
checks that. Nudge drafts for quiet pull requests are shown for you to copy;
they are never posted.
