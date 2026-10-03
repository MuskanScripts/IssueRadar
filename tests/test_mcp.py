"""The MCP server, through the SDK's in-process client. Fake GitHub only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from mcp import Client
from typer.testing import CliRunner

from fake_github import FakeGitHub, example_issue
from issueradar.cli import app
from issueradar.config import Settings
from issueradar.engine.rules import load_rules
from issueradar.github import GitHubClient
from issueradar.mcp_server import create_server
from issueradar.storage import Database
from issueradar.storage.models import TrackedPullRequest
from scenario import REPO, build, iso


def server(db: Database, settings: Settings, **kw: Any):  # type: ignore[no-untyped-def]
    return create_server(db, settings, load_rules(), **kw)


async def call(srv: Any, tool: str, args: dict[str, Any] | None = None) -> Any:
    async with Client(srv) as client:
        return await client.call_tool(tool, args or {})


async def test_tools_are_read_only(db: Database, settings: Settings) -> None:
    async with Client(server(db, settings)) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == {"find_issues", "explain_issue", "my_prs"}
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.output_schema is not None  # structured results


async def test_find_issues(db: Database, settings: Settings, synced: FakeGitHub) -> None:
    srv = server(db, settings)
    result = await call(srv, "find_issues")
    assert not result.is_error
    found = result.structured_content["issues"]
    assert {i["issue"] for i in found} == {f"{REPO}#1", f"{REPO}#3", f"{REPO}#4"}
    assert all(i["availability"] in ("free", "likely_free") for i in found)
    assert found[0]["why"]

    beginners = await call(srv, "find_issues", {"level": ["beginner"], "limit": 1})
    picked = beginners.structured_content["issues"]
    assert len(picked) == 1 and picked[0]["level"] == "beginner"

    bad = await call(srv, "find_issues", {"level": ["expert"]})
    assert bad.is_error


async def test_find_issues_says_what_to_do_when_nothing_is_watched(
    db: Database, settings: Settings
) -> None:
    result = await call(server(db, settings), "find_issues")
    assert result.structured_content["issues"] == []
    assert "watch add" in result.structured_content["note"]


async def test_explain_stored_issue(db: Database, settings: Settings, synced: FakeGitHub) -> None:
    requests_before = len(synced.requests)
    result = await call(server(db, settings), "explain_issue", {"issue": f"{REPO}#3"})
    assert not result.is_error
    data = result.structured_content
    assert data["availability"] == "likely_free"
    assert any("20 days ago" in r for r in data["availability_reasons"])
    assert data["checklist"]
    assert len(synced.requests) == requests_before  # stored: GitHub isn't asked


async def test_explain_errors_are_tool_errors(db: Database, settings: Settings) -> None:
    srv = server(db, settings)
    not_an_issue = await call(srv, "explain_issue", {"issue": "hello"})
    assert not_an_issue.is_error and "not an issue link" in not_an_issue.content[0].text
    no_token = await call(srv, "explain_issue", {"issue": f"https://github.com/{REPO}/issues/1"})
    assert no_token.is_error and "token" in no_token.content[0].text


async def test_explain_fetches_one_issue_read_only(db: Database, settings: Settings) -> None:
    fake = FakeGitHub()
    build(fake)
    fake.add(
        f"/repos/{REPO}/issues/1",
        example_issue(1, title="Fix typo in the README", updated_at=iso(1), comments=0),
    )
    srv = server(
        db,
        settings,
        client_factory=lambda: GitHubClient(settings.github, "t", transport=fake.transport()),
    )
    result = await call(srv, "explain_issue", {"issue": f"https://github.com/{REPO}/issues/1"})
    assert not result.is_error, result.content
    assert result.structured_content["title"] == "Fix typo in the README"
    assert fake.requests and {r.method for r in fake.requests} == {"GET"}


async def test_my_prs(db: Database, settings: Settings) -> None:
    srv = server(db, settings)
    empty = (await call(srv, "my_prs")).structured_content
    assert empty["pull_requests"] == [] and "firstpr prs" in empty["note"]

    now = datetime.now(UTC)
    with db.sessions.begin() as session:
        for n, state, status in (
            (1, "open", "changes_requested"),
            (2, "open", "waiting_for_review"),
            (3, "closed", "merged"),
            (4, "open", "stale"),
        ):
            session.add(
                TrackedPullRequest(
                    user_id=1,
                    repo_full_name="o/r",
                    number=n,
                    title=f"PR {n}",
                    state=state,
                    status=status,
                    needs_you="Something" if n != 2 else "Waiting for a first review.",
                    nudge="Hi, just checking in." if status == "stale" else None,
                    opened_at=now - timedelta(days=9),
                    checked_at=now,
                )
            )
    open_prs = (await call(srv, "my_prs")).structured_content
    assert [p["number"] for p in open_prs["pull_requests"]] == [1, 4, 2]  # most urgent first
    assert open_prs["last_checked"] is not None and open_prs["note"] is None

    mine = (await call(srv, "my_prs", {"needs_me_only": True})).structured_content
    assert {p["number"] for p in mine["pull_requests"]} == {1, 4}
    assert next(p for p in mine["pull_requests"] if p["number"] == 4)["nudge"]

    everything = (await call(srv, "my_prs", {"include_closed": True})).structured_content
    assert len(everything["pull_requests"]) == 4


def test_cli_mcp_reports_config_errors_on_stderr(tmp_path: Any) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("ranking: [", encoding="utf-8")
    result = CliRunner().invoke(app, ["mcp", "--config", str(broken)])
    assert result.exit_code == 2
    assert result.stdout == ""  # stdout belongs to the protocol


async def test_stdio_end_to_end(db: Database, tmp_path: Any) -> None:
    """Start `firstpr mcp` as a real subprocess and talk to it over stdin/stdout,
    the way an assistant does. Anything else printed to stdout would break this."""
    import os
    import sys

    from mcp import StdioServerParameters

    env = {k: v for k, v in os.environ.items() if "TOKEN" not in k}
    env["FIRSTPR_DB_URL"] = db.url
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "issueradar.cli", "mcp"], env=env, cwd=str(tmp_path)
    )
    async with Client(params) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        result = await client.call_tool("find_issues", {})
    assert names == {"find_issues", "explain_issue", "my_prs"}
    assert result.structured_content["issues"] == []
