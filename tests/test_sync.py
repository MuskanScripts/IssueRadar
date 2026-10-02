from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from fake_github import API, FakeGitHub, example_issue, example_pull, example_repo, load_fixture
from issueradar.config import Settings, load_settings
from issueradar.github import GitHubClient
from issueradar.storage import Database
from issueradar.storage.etag_cache import SqlEtagCache
from issueradar.storage.models import Issue, PullRequest, Repo, SyncRun
from issueradar.sync import SyncService, watchlist
from issueradar.sync.service import NOT_OPEN

LIST = {"state": "open", "sort": "created", "direction": "asc"}


def serve_repo(
    fake: FakeGitHub,
    name: str,
    issues: list[dict],
    pulls: list[dict] | None = None,
    *,
    page_size: int = 100,
    **repo_changes: object,
) -> None:
    fake.add(f"/repos/{name}", example_repo(name, **repo_changes))
    fake.add_list(f"/repos/{name}/issues", issues, LIST, page_size=page_size)
    fake.add_list(f"/repos/{name}/pulls", pulls or [], LIST, page_size=page_size)


async def sync(db: Database, settings: Settings, fake: FakeGitHub):  # type: ignore[no-untyped-def]
    async with GitHubClient(
        settings.github, "t", cache=SqlEtagCache(db.sessions), transport=fake.transport()
    ) as client:
        return await SyncService(db, client, settings).run()


def settings_with(tmp_path: Path, yaml_text: str) -> Settings:
    path = tmp_path / "firstpr.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return load_settings(path)


def count(db: Database, model: type) -> int:
    with db.sessions() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


async def test_first_sync_stores_data_and_second_sync_uses_etags(
    db: Database, settings: Settings
) -> None:
    fake = FakeGitHub()
    pr_as_issue = {**example_issue(9), "pull_request": {"url": "x"}}
    serve_repo(
        fake,
        "a/one",
        [example_issue(1), example_issue(2), pr_as_issue],
        [example_pull(9, "Fixes #2")],
    )
    serve_repo(fake, "a/two", [example_issue(1, id=30_000_000_001)])
    watchlist.add(db, "a/one")
    watchlist.add(db, "a/two")

    first = await sync(db, settings, fake)
    assert first.status == "completed"
    assert [(o.full_name, o.open_issues, o.open_pull_requests) for o in first.outcomes] == [
        ("a/one", 2, 1),
        ("a/two", 1, 0),
    ]
    assert count(db, Issue) == 3  # the PR that appeared in /issues was filtered out
    with db.sessions() as session:
        pr = session.scalar(select(PullRequest))
        assert pr is not None and pr.closing_issues == [2]
    assert (fake.count_200, fake.count_304) == (6, 0)
    remaining_after_first = fake.remaining

    second = await sync(db, settings, fake)
    assert second.status == "completed"
    assert (fake.count_200, fake.count_304) == (6, 6)  # every request was a free 304
    assert fake.remaining == remaining_after_first
    assert count(db, Issue) == 3
    with db.sessions() as session:
        runs = session.scalars(select(SyncRun).order_by(SyncRun.id)).all()
        assert [(r.requests, r.not_modified) for r in runs] == [(6, 0), (6, 6)]


async def test_quota_exhaustion_mid_sync_resumes_without_data_loss(
    db: Database, tmp_path: Path
) -> None:
    settings = settings_with(tmp_path, "github:\n  budget:\n    safety_margin: 0\n")
    fake = FakeGitHub(limit=5000, remaining=4)  # enough for a/one (3) and one more request
    for i, name in enumerate(["a/one", "a/two", "a/three"]):
        serve_repo(fake, name, [example_issue(1, id=40_000_000_000 + i)])
        watchlist.add(db, name)

    first = await sync(db, settings, fake)
    assert first.status == "interrupted"
    assert "resets at" in (first.message or "")
    assert [o.full_name for o in first.outcomes] == ["a/one"]
    assert count(db, Issue) == 1
    with db.sessions() as session:
        run = session.scalar(select(SyncRun))
        assert run is not None
        assert (run.status, run.repos_done) == ("interrupted", ["a/one"])

    fake.remaining = 5000  # the hour has passed
    second = await sync(db, settings, fake)
    assert second.resumed is True
    assert second.status == "completed"
    assert [o.full_name for o in second.outcomes] == ["a/two", "a/three"]
    assert count(db, Issue) == 3
    assert count(db, Repo) == 3
    with db.sessions() as session:
        runs = session.scalars(select(SyncRun)).all()
        assert len(runs) == 1  # the same run was continued
        assert runs[0].status == "completed"
        assert runs[0].repos_done == ["a/one", "a/two", "a/three"]


async def test_one_failing_repo_does_not_fail_the_run(db: Database, settings: Settings) -> None:
    fake = FakeGitHub()
    serve_repo(fake, "a/one", [example_issue(1)])
    serve_repo(fake, "a/three", [example_issue(1, id=50_000_000_003)])
    for name in ["a/one", "a/missing", "a/three"]:
        watchlist.add(db, name)

    report = await sync(db, settings, fake)
    assert report.status == "completed"
    assert [(o.full_name, o.status) for o in report.outcomes] == [
        ("a/one", "synced"),
        ("a/missing", "failed"),
        ("a/three", "synced"),
    ]
    with db.sessions() as session:
        missing = session.scalar(select(Repo).where(Repo.full_name == "a/missing"))
        assert missing is not None and "Not found" in (missing.sync_error or "")
        run = session.scalar(select(SyncRun))
        assert run is not None and list(run.repos_failed) == ["a/missing"]


async def test_issue_that_leaves_the_open_list_is_marked(db: Database, settings: Settings) -> None:
    fake = FakeGitHub()
    serve_repo(fake, "a/one", [example_issue(1), example_issue(2)])
    watchlist.add(db, "a/one")
    await sync(db, settings, fake)

    serve_repo(fake, "a/one", [example_issue(2)])  # #1 was closed or transferred
    await sync(db, settings, fake)
    with db.sessions() as session:
        states = {n: st for n, st in session.execute(select(Issue.number, Issue.state))}
    assert states == {1: NOT_OPEN, 2: "open"}


async def test_truncated_list_does_not_mark_unseen_issues(db: Database, tmp_path: Path) -> None:
    settings = settings_with(
        tmp_path, "github:\n  rest:\n    per_page: 2\nsync:\n  max_pages_per_list: 1\n"
    )
    fake = FakeGitHub()
    serve_repo(fake, "a/one", [example_issue(n) for n in (1, 2, 3)], page_size=2)
    watchlist.add(db, "a/one")
    report = await sync(db, settings, fake)
    assert report.outcomes[0].note == "only the first 2 open issues were fetched"
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Issue)) == 2
        assert not session.scalars(select(Issue).where(Issue.state == NOT_OPEN)).all()


async def test_renamed_repo_updates_the_watchlist(db: Database, settings: Settings) -> None:
    fake = FakeGitHub()
    serve_repo(fake, "new-owner/tool", [example_issue(1)])
    fake.add("/repos/old-owner/tool", example_repo("new-owner/tool"))  # GitHub redirects
    watchlist.add(db, "old-owner/tool")
    report = await sync(db, settings, fake)
    assert report.outcomes[0].note == "moved to new-owner/tool"
    assert watchlist.list_watched(db) == ["new-owner/tool"]


async def test_archived_repo_is_stored_but_not_listed(db: Database, settings: Settings) -> None:
    fake = FakeGitHub()
    serve_repo(fake, "a/old", [example_issue(1)], archived=True)
    watchlist.add(db, "a/old")
    report = await sync(db, settings, fake)
    assert report.outcomes[0].status == "archived"
    assert len(fake.requests) == 1
    assert count(db, Issue) == 0


async def test_recorded_repo_syncs_end_to_end(db: Database, settings: Settings) -> None:
    """Real recorded responses for MuskanScripts/IssueRadar (11 open Dependabot PRs)."""
    fake = FakeGitHub()
    for name in ("repo", "issues-open", "pulls-open"):
        fixture = load_fixture(f"recorded/muskanscripts-issueradar-{name}.json")
        fake.add(fixture["request"]["url"], fixture["response"]["body"])
    watchlist.add(db, "MuskanScripts/IssueRadar")
    report = await sync(db, settings, fake)
    assert report.status == "completed"
    assert (report.outcomes[0].open_issues, report.outcomes[0].open_pull_requests) == (0, 11)
    assert all(str(r.url).startswith(API) for r in fake.requests)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("octocat/Hello-World", "octocat/Hello-World"),
        ("https://github.com/octocat/Hello-World", "octocat/Hello-World"),
        ("https://github.com/octocat/Hello-World.git", "octocat/Hello-World"),
    ],
)
def test_watchlist_accepts_names_and_urls(value: str, expected: str) -> None:
    assert watchlist.normalise_repo(value) == expected


@pytest.mark.parametrize("value", ["octocat", "a/b/c", "https://example.com/a/b", ""])
def test_watchlist_rejects_garbage(value: str) -> None:
    with pytest.raises(watchlist.WatchlistError):
        watchlist.normalise_repo(value)


def test_watchlist_add_is_idempotent_and_remove_works(db: Database) -> None:
    assert watchlist.add(db, "a/one") == ("a/one", True)
    assert watchlist.add(db, "A/ONE") == ("a/one", False)
    assert watchlist.remove(db, "a/one") is True
    assert watchlist.list_watched(db) == []
