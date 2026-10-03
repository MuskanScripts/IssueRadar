"""A small fake repo with one issue of every kind, synced through the real code."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fake_github import FakeGitHub, example_issue, example_pull, example_repo
from issueradar.config import Settings
from issueradar.engine.rules import load_rules
from issueradar.github import GitHubClient
from issueradar.radar import Radar
from issueradar.storage import Database
from issueradar.storage.etag_cache import SqlEtagCache
from issueradar.sync import SyncService, watchlist
from issueradar.sync.enrich import Enricher

NOW = datetime.now(UTC)
LIST = {"state": "open", "sort": "created", "direction": "asc"}
REPO = "a/one"


def iso(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def gh_comment(
    cid: int, body: str, *, login: str = "dev", assoc: str = "NONE", days: float = 1
) -> dict:
    return {
        "id": cid,
        "body": body,
        "author_association": assoc,
        "created_at": iso(days),
        "user": {"login": login, "type": "User"},
    }


def cross_ref(number: int, *, state: str = "open", repo: str = REPO) -> dict[str, Any]:
    return {
        "event": "cross-referenced",
        "created_at": iso(1),
        "source": {
            "type": "issue",
            "issue": {
                "number": number,
                "state": state,
                "repository": {"full_name": repo},
                "pull_request": {"url": "x", "merged_at": None},
                "user": {"login": "dev", "type": "User"},
            },
        },
    }


def build(fake: FakeGitHub) -> None:
    def issue(n: int, title: str, comments: int = 0, **kw: Any) -> dict[str, Any]:
        return example_issue(n, title=title, comments=comments, updated_at=iso(1), **kw)

    issues = [
        issue(
            1,
            "Fix typo in the README",
            body="The word 'recieve' in README.md is misspelled.",
            labels=[{"name": "good first issue"}],
        ),
        issue(2, "Client hangs on close", comments=1),
        issue(3, "Add retry setting", comments=1),
        issue(4, "Document the CLI flags", comments=1, labels=[{"name": "documentation"}]),
        issue(5, "Crash on empty config"),
        issue(6, "Support streaming responses", comments=0),
        issue(7, "Assigned already", assignees=[{"login": "lead"}]),
        issue(8, "Fixed by an open PR"),
        issue(9, "Needs triage first", labels=[{"name": "needs triage"}]),
    ]
    fake.add(
        f"/repos/{REPO}", example_repo(REPO, pushed_at=iso(1), language="Python", topics=["mcp"])
    )
    fake.add_list(f"/repos/{REPO}/issues", issues, LIST, page_size=100)
    fake.add_list(f"/repos/{REPO}/pulls", [example_pull(50, "Fixes #8")], LIST, page_size=100)
    fake.add(
        "/search/issues?per_page=100&q=repo%3Aa%2Fone+is%3Aissue+is%3Aopen+linked%3Apr",
        {"total_count": 1, "incomplete_results": False, "items": [{"number": 5}]},
    )
    fake.add(
        f"/repos/{REPO}/issues/2/comments?per_page=100",
        [gh_comment(1, "Can I work on this?", days=3)],
    )
    fake.add(
        f"/repos/{REPO}/issues/3/comments?per_page=100",
        [gh_comment(2, "I'd like to work on this", days=20)],
    )
    fake.add(
        f"/repos/{REPO}/issues/4/comments?per_page=100",
        [gh_comment(3, "Feel free to take this!", login="lead", assoc="OWNER", days=2)],
    )
    for n in (1, 2, 3, 4, 6, 9):
        fake.add(f"/repos/{REPO}/issues/{n}/timeline?per_page=100", [])
    fake.add(f"/repos/{REPO}/issues/6/timeline?per_page=100", [cross_ref(60)])
    fake.add(
        f"/repos/{REPO}/community/profile",
        {
            "files": {
                "contributing": {
                    "url": f"https://api.github.com/repos/{REPO}/contents/CONTRIBUTING.md"
                },
                "issue_template": {"url": "x"},
                "pull_request_template": None,
            }
        },
    )
    fake.add(
        f"/repos/{REPO}/contents/CONTRIBUTING.md",
        {
            "encoding": "base64",
            "content": "UGxlYXNlIHNpZ24gb3VyIENMQSBiZWZvcmUgY29udHJpYnV0aW5nLg==",
        },
    )
    closed = [
        example_pull(
            40 + i,
            "",
            state="closed",
            author_association="CONTRIBUTOR",
            merged_at=iso(10) if i < 3 else None,
            closed_at=iso(10),
        )
        for i in range(4)
    ]
    fake.add(f"/repos/{REPO}/pulls?direction=desc&per_page=100&sort=updated&state=closed", closed)
    fake.add(f"/repos/{REPO}/languages", {"Python": 9000, "Shell": 100})
    fake.add(
        f"/repos/{REPO}/contents",
        [
            {
                "type": "file",
                "name": "pyproject.toml",
                "url": f"https://api.github.com/repos/{REPO}/contents/pyproject.toml",
            }
        ],
    )
    fake.add(
        f"/repos/{REPO}/contents/pyproject.toml",
        {
            "encoding": "base64",
            "content": "W3Byb2plY3RdCmRlcGVuZGVuY2llcyA9IFsiZmFzdGFwaSIsICJweWRhbnRpYyJdCg==",
        },
    )


async def run_sync(db: Database, settings: Settings, fake: FakeGitHub):  # type: ignore[no-untyped-def]
    rules = load_rules()
    async with GitHubClient(
        settings.github, "t", cache=SqlEtagCache(db.sessions), transport=fake.transport()
    ) as client:
        service = SyncService(
            db,
            client,
            settings,
            enricher=Enricher(db, client, settings, rules),
            radar=Radar(db, settings, rules, None),
        )
        return await service.run()


@pytest.fixture
async def synced(db: Database, settings: Settings) -> FakeGitHub:
    fake = FakeGitHub()
    build(fake)
    watchlist.add(db, REPO)
    report = await run_sync(db, settings, fake)
    assert report.status == "completed", report
    return fake
