"""End to end: sync with enrichment, then find, explain and eval. Fake GitHub only."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fake_github import FakeGitHub
from issueradar import evaluation
from issueradar.cli import app
from issueradar.config import Settings
from issueradar.engine.rules import load_rules
from issueradar.engine.stack import SkillProfile
from issueradar.models import Availability, Tier
from issueradar.radar import Filters, Radar
from issueradar.storage import Database
from issueradar.sync.enrich import timeline_signal
from scenario import REPO, cross_ref, run_sync


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
