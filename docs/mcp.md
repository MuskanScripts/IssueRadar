# Use FirstPR from an AI assistant (MCP)

`firstpr mcp` runs a [Model Context Protocol](https://modelcontextprotocol.io)
server over stdio. Any assistant that supports MCP can then ask your radar
for work that suits you, explain an issue, or check on your pull requests.

It is read-only. The tools read the same local database as the CLI and the
dashboard. They never dismiss, snooze, comment, or write to GitHub.

## Install

The server needs the optional `mcp` extra:

```powershell
python -m pip install "firstpr[mcp]"
# or, in a clone:
python -m pip install -e ".[mcp]"
```

Fill the database first, as usual:

```powershell
firstpr watch add modelcontextprotocol/python-sdk
firstpr sync
firstpr prs
```

## Connect a client

Most clients take a JSON entry with a command and arguments. Use the full path
to `firstpr` so the client finds it without your shell's PATH. On Windows,
`(Get-Command firstpr).Source` prints it.

```json
{
  "mcpServers": {
    "firstpr": {
      "command": "C:\\Users\\you\\IssueRadar\\.venv\\Scripts\\firstpr.exe",
      "args": ["mcp"]
    }
  }
}
```

VS Code (`.vscode/mcp.json`):

```json
{
  "servers": {
    "firstpr": {
      "type": "stdio",
      "command": "C:\\Users\\you\\IssueRadar\\.venv\\Scripts\\firstpr.exe",
      "args": ["mcp"]
    }
  }
}
```

Add `"--config", "path\\to\\firstpr.yaml"` or `"--skills", "path\\to\\skills.yaml"`
to `args` if you keep those files somewhere other than the folder the client
starts in. A profile saved from the dashboard is used first.

**Token.** Optional. Without one, `explain_issue` only works on issues that are
already synced. With `FIRSTPR_GITHUB_TOKEN` in the environment the client
starts the server with, it can fetch any public issue (GET only). Don't paste
the token into a config file you commit or share.

## Tools

| Tool | What it returns | Talks to GitHub |
| --- | --- | --- |
| `find_issues` | Free issues, best match first: level, time, type, repo health, rank and one line on why. Filters: `level`, `language`, `issue_type`, `time`, `repo`, `min_health`, `no_discussion`, `limit` (1 to 50, default 10). | No |
| `explain_issue` | Everything `firstpr explain` shows for one issue (`owner/repo#123` or a link): availability with reasons, level with reasons, repo health, CLA/DCO/AI-policy flags, stack fit and a checklist. | Only for an issue that isn't synced yet, and only GET requests |
| `my_prs` | Your tracked pull requests, most urgent first, with what each needs and nudge drafts. `needs_me_only`, `include_closed`. | No (run `firstpr prs` or `firstpr daily` to refresh) |

Every tool is marked read-only and non-destructive in its MCP annotations, and
returns structured JSON with a schema. When there is nothing to show, the
result has a `note` saying what to run.

The server's instructions tell the assistant that nudge drafts are for you to
send, never to post.

## Try it without a client

The MCP inspector lists the tools and lets you call them by hand:

```powershell
npx @modelcontextprotocol/inspector firstpr mcp
```

## Troubleshooting

- **The client shows no tools.** Run `firstpr mcp` in a terminal: it should sit
  waiting for input with nothing printed. Errors (a broken config, a missing
  extra) go to stderr, which most clients show in their logs.
- **"Nothing watched yet".** The database the server opened is empty. The client
  may start it in another folder or with another user; set `FIRSTPR_DB_URL` in
  the client's environment to point at your database (`firstpr doctor` prints
  its location).
