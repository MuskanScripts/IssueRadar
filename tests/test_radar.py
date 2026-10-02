"""End to end: sync with enrichment, then find, explain and eval. Fake GitHub only."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from fake_github import FakeGitHub, example_issue, example_pull, example_repo
from issueradar import evaluation
from issueradar.cli import app
from issueradar.config import Settings
from issueradar.engine.rules import load_rules
from issueradar.engine.stack import SkillProfile
from issueradar.github import GitHubClient
from issueradar.models import Availability, Tier
from issueradar.radar import Filters, Radar
from issueradar.storage import Database
from issueradar.storage.etag_cache import SqlEtagCache
from issueradar.sync import SyncService, watchlist
from issueradar.sync.enrich import Enricher, timeline_signal

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


def radar(db: Database, settings: Settings, profile: SkillProfile | None = None) -> Radar:
    return Radar(db, settings, load_rules(), profile)


async def test_states_after_enrichment(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    r = radar(db, settings)
    states = {n: r.report_for(REPO, n).availability.state for n in range(1, 10)}  # type: ignore[union-attr]
    assert states == {
        1: Availability.FREE,
        2: Availability.CLAIMED,
        3: Availability.LIKELY_FREE,
        4: Availability.FREE,  # maintainer invitation is not a claim
        5: Availability.HAS_PR,  # linked:pr search
        6: Availability.HAS_PR,  # timeline cross-reference
        7: Availability.CLAIMED,  # assignee
        8: Availability.HAS_PR,  # "Fixes #8" in an open PR
        9: Availability.NOT_READY,
    }


async def test_finalists_skip_issues_already_taken(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    paths = {r.url.path for r in synced.requests}
    assert f"/repos/{REPO}/issues/7/comments" not in paths  # assigned
    assert f"/repos/{REPO}/issues/5/timeline" not in paths  # linked PR found by search
    assert f"/repos/{REPO}/issues/8/timeline" not in paths  # closing reference


async def test_health_and_flags(db: Database, settings: Settings, synced: FakeGitHub) -> None:
    report = radar(db, settings).report_for(REPO, 1)
    assert report is not None and report.health_score is not None
    assert any("3 of 4 recent outside pull requests accepted" in r for r in report.health_reasons)
    assert report.flags["cla"] is True
    assert report.frameworks == ["fastapi", "pydantic"]
    assert report.domains == ["agents-and-mcp"]


async def test_second_sync_rereads_nothing_unchanged(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    before = len(synced.requests)
    await run_sync(db, settings, synced)
    new = synced.requests[before:]
    assert not [r for r in new if r.url.path.endswith("/comments")]  # issues unchanged
    assert synced.statuses[before:].count(200) <= 1  # only the search (not cacheable)


async def test_find_ranks_free_issues_and_filters(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    profile = SkillProfile(languages={"python": "learning"})
    results = radar(db, settings, profile).find(Filters())
    numbers = [r.number for r in results]
    assert set(numbers) == {1, 3, 4}  # free and likely free only
    assert numbers[0] in (1, 4)  # beginner work ranks above the stale claim
    beginners = radar(db, settings, profile).find(Filters(tiers=[Tier.BEGINNER]))
    assert {r.difficulty.tier for r in beginners} == {Tier.BEGINNER}
    assert radar(db, settings).find(Filters(frameworks=["react"])) == []


async def test_snapshots_written(db: Database, settings: Settings, synced: FakeGitHub) -> None:
    from sqlalchemy import func, select

    from issueradar.storage.models import ScoreSnapshot

    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ScoreSnapshot)) == 9


async def test_eval_scores_labels(
    db: Database, settings: Settings, synced: FakeGitHub, tmp_path: Path
) -> None:
    sheet = tmp_path / "labels.csv"
    rows = [  # test data only: these labels describe the fake repo above
        (1, "yes", "beginner"),
        (2, "no", "intermediate"),
        (3, "yes", ""),
        (5, "no", "intermediate"),
        (4, "", "beginner"),
    ]
    with sheet.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(evaluation.COLUMNS)
        for n, free, tier in rows:
            writer.writerow(
                [f"https://github.com/{REPO}/issues/{n}", "", free, tier, "", "test", ""]
            )
        writer.writerow(["https://github.com/a/missing/issues/1", "", "yes", "", "", "", ""])
    report = evaluation.run(radar(db, settings), sheet)
    assert report.rows == 6 and report.missing == ["https://github.com/a/missing/issues/1"]
    assert (report.strict.tp, report.strict.fp, report.strict.fn, report.strict.tn) == (1, 0, 1, 2)
    assert (report.lenient.tp, report.lenient.fn) == (2, 0)
    assert report.lenient.precision == 1.0 and report.lenient.recall == 1.0
    assert report.labelled_tier == 4


async def test_eval_sample_has_no_predictions(
    db: Database, settings: Settings, synced: FakeGitHub, tmp_path: Path
) -> None:
    out = tmp_path / "sheet.csv"
    count = evaluation.sample(radar(db, settings), out, per_repo=3)
    assert count == 3
    text = out.read_text("utf-8")
    assert text.splitlines()[0] == ",".join(evaluation.COLUMNS)
    assert "free" not in text.lower().split("\n", 1)[1]


def test_timeline_signal_parsing() -> None:
    kind, key, data, _ = timeline_signal(cross_ref(9, repo="x/y"), 0)  # type: ignore[misc]
    assert (kind, key, data["is_pr"], data["state"]) == ("cross_reference", "x/y#9", True, "open")
    assert timeline_signal({"event": "labeled"}, 0) is None
    assert timeline_signal({"event": "connected", "id": 5}, 0)[0] == "connected"  # type: ignore[index]


async def test_explain_cli_on_stored_issue(
    db: Database, settings: Settings, synced: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIRSTPR_DB_URL", db.url)
    result = CliRunner().invoke(app, ["explain", f"https://github.com/{REPO}/issues/3"])
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    assert "Likely free" in out
    assert "20 days ago" in out
    assert "Level" in out and "Repo health" in out
    assert "CLA" in out


async def test_find_cli(
    db: Database, settings: Settings, synced: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIRSTPR_DB_URL", db.url)
    result = CliRunner().invoke(app, ["find", "--level", "beginner"])
    assert result.exit_code == 0, result.stdout
    assert "a/one#1" in result.stdout
    bad = CliRunner().invoke(app, ["find", "--level", "expert"])
    assert bad.exit_code == 2 and "Unknown level" in bad.stdout


def test_explain_rejects_pull_request_links() -> None:
    result = CliRunner().invoke(app, ["explain", "https://github.com/a/b/pull/3"])
    assert result.exit_code == 2
    assert "pull request" in result.stdout
