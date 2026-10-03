from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from fake_github import FakeGitHub
from issueradar.api.app import create_app
from issueradar.config import Settings
from issueradar.engine.rules import load_rules
from issueradar.storage import Database
from scenario import REPO


def client(db: Database, settings: Settings, **kw: object) -> TestClient:
    return TestClient(create_app(db, settings, load_rules(), **kw))  # type: ignore[arg-type]


def test_meta_and_openapi(db: Database, settings: Settings) -> None:
    c = client(db, settings, demo=True)
    meta = c.get("/api/meta").json()
    assert meta["demo"] is True and meta["name"]
    paths = c.get("/api/openapi.json").json()["paths"]
    assert "/api/issues" in paths and "/api/prs" in paths
    # Nothing in the API can write to GitHub: the only non-GET routes touch local state.
    writes = {p for p, ops in paths.items() for m in ops if m != "get"}
    assert writes == {
        "/api/issues/{owner}/{name}/{number}/dismiss",
        "/api/issues/{owner}/{name}/{number}/snooze",
        "/api/issues/{owner}/{name}/{number}/feedback",
        "/api/profile",
        "/api/views",
    }


async def test_issues_filters_and_detail(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    c = client(db, settings)
    issues = c.get("/api/issues").json()
    assert {i["number"] for i in issues} == {1, 3, 4}
    beginners = c.get("/api/issues", params={"level": "beginner"}).json()
    assert all(i["tier"] == "beginner" for i in beginners)
    assert c.get("/api/issues", params={"level": "expert"}).status_code == 422
    everything = c.get("/api/issues", params={"all": "true"}).json()
    assert len(everything) == 9
    detail = c.get(f"/api/issues/{REPO}/3").json()
    assert detail["availability"] == "likely_free"
    assert any("20 days ago" in r for r in detail["availability_reasons"])
    assert detail["checklist"][0].startswith("Read")
    assert c.get(f"/api/issues/{REPO}/999").status_code == 404


async def test_dismiss_snooze_feedback(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    c = client(db, settings)
    assert c.post(f"/api/issues/{REPO}/1/dismiss").status_code == 204
    assert c.post(f"/api/issues/{REPO}/4/snooze", json={"days": 3}).status_code == 204
    assert c.post(f"/api/issues/{REPO}/3/feedback", json={"verdict": "harder"}).status_code == 204
    assert c.post(f"/api/issues/{REPO}/3/feedback", json={"verdict": "meh"}).status_code == 422
    digest = c.get("/api/digest").json()
    assert f"{REPO}#1" not in digest["markdown"] and f"{REPO}#3" in digest["markdown"]


async def test_repos_settings_profile_views(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    c = client(db, settings)
    repos = c.get("/api/repos").json()
    assert repos[0]["full_name"] == REPO and repos[0]["free_issues"] == 3
    assert repos[0]["health"] is not None
    s = c.get("/api/settings").json()
    assert s["last_sync"]["status"] == "completed" and s["channels"]["rss"] is True
    profile = {
        "stretch": True,
        "languages": {"python": "strong"},
        "frameworks": {},
        "domains": {},
        "prefer_issue_types": [],
    }
    assert c.put("/api/profile", json=profile).status_code == 200
    assert c.get("/api/profile").json()["languages"] == {"python": "strong"}
    ranked = c.get("/api/issues").json()
    assert any("stretch on" in r for r in ranked[0]["stack_reasons"])
    views = [{"name": "Weekend Python", "filters": {"language": ["python"]}}]
    assert c.put("/api/views", json=views).json() == views
    assert c.get("/api/views").json() == views


def test_insights_from_tracked_prs(db: Database, settings: Settings) -> None:
    from datetime import UTC, datetime, timedelta

    from issueradar.storage.models import TrackedPullRequest

    now = datetime.now(UTC)
    with db.sessions.begin() as session:
        for n, status, review_hours in (
            (1, "merged", 5),
            (2, "merged", 15),
            (3, "closed_unmerged", None),
            (4, "waiting_for_review", None),
        ):
            session.add(
                TrackedPullRequest(
                    user_id=1,
                    repo_full_name="o/r",
                    number=n,
                    title="t",
                    state="open" if n == 4 else "closed",
                    status=status,
                    needs_you="",
                    opened_at=now - timedelta(days=3),
                    first_review_at=(now - timedelta(days=3) + timedelta(hours=review_hours))
                    if review_hours
                    else None,
                )
            )
    data = client(db, settings).get("/api/insights").json()
    assert (data["opened"], data["merged"], data["closed_unmerged"], data["open_now"]) == (
        4,
        2,
        1,
        1,
    )
    assert round(data["merge_rate"], 3) == 0.667
    assert data["median_hours_to_first_review"] == 10.0


def test_serves_built_dashboard(db: Database, settings: Settings, tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>x</title>", "utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", "utf-8")
    c = client(db, settings, web_dist=tmp_path)
    assert c.get("/repos").text.startswith("<!doctype html>")  # client-side route
    assert c.get("/assets/app.js").status_code == 200
    assert c.get("/../../etc/passwd").text.startswith("<!doctype html>")
