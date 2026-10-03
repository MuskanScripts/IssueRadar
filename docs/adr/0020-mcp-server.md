# 0020. MCP server: stdio, read-only, an optional extra

- Status: accepted
- Date: 2026-10-03

## Context

M8 asks for read-only MCP tools (`find_issues`, `explain_issue`, `my_prs`) on
the official Python SDK. Version 2 of the SDK replaced `FastMCP` with
`MCPServer`, adds tool annotations and structured output, and brings its own
dependencies (OpenTelemetry, JWT, an HTTP stack) that most users of the CLI
never need.

## Decision

- One module, `issueradar/mcp_server.py`, built on `MCPServer`. The tools call
  the same `Radar`, single-issue sync and PR store as the CLI and API, and
  return the API's own models (`IssueOut`, `PullOut`), so all three surfaces
  agree.
- Only the three tools in the brief. All are annotated read-only and
  non-destructive. Dismiss, snooze and feedback stay in the CLI and dashboard,
  where a person clicks them.
- `explain_issue` may fetch one issue that isn't synced, through the read-only
  GitHub client, and only when a token is present. The other tools read the
  local database only.
- stdio transport only (`firstpr mcp`). No network listener, so no auth to get
  wrong. The command sends every human-readable message to stderr.
- The SDK is an optional extra, `firstpr[mcp]`, pinned to `>=2.3,<3`. The
  `dev` extra includes it so CI tests the server on every push.

## Consequences

- Tests use the SDK's in-process client, plus one test that starts `firstpr
  mcp` as a subprocess and talks over real stdio.
- `my_prs` shows the last stored state. Refreshing is `firstpr prs` or the
  daily job; the tool says when it last checked.
- The Docker image does not include the extra. Assistants run the server
  locally, next to the user's database.
