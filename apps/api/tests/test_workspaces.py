"""Start working, the live steps, changes, the pull request, and the rules around them."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from conftest import FakeGitHub, FakeJobs, add_card, csrf, sign_in
from firstpr_api import workspaces as api_workspaces
from firstpr_platform import workspaces
from firstpr_platform.db import Reservation, Workspace
from firstpr_platform.github_user import UserGitHub

REPO = "pallets/flask"


@pytest.fixture
def ready(client: TestClient, sync_db: OrmSession, github: FakeGitHub) -> TestClient:
    """Signed in and onboarded, with one free issue on a repo GitHub knows."""
    add_card(sync_db, REPO, 7, title="Docs: fix the broken link")
    github.work.upstream(REPO)
    sign_in(client)
    resp = client.put("/api/v1/me/profile", json={}, headers=csrf(client))
    assert resp.status_code == 200
    return client


def start(client: TestClient, mode: str = "codespace") -> Any:
    return client.post(
        "/api/v1/workspaces", json={"repo": REPO, "number": 7, "mode": mode}, headers=csrf(client)
    )


def run_worker(sync_db: OrmSession, github: FakeGitHub, workspace_id: int) -> None:
    """What the worker's start_workspace job does, against the same database."""

    async def go() -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        from firstpr_platform.db import session_factory

        url = str(sync_db.get_bind().url).replace("sqlite://", "sqlite+aiosqlite://")
        engine = create_async_engine(url)
        async with session_factory(engine)() as db:
            ws = await db.get(Workspace, workspace_id)
            assert ws is not None

            async def no_sleep(_: float) -> None:
                return None

            async with UserGitHub("ghu_test_1", transport=github.work.transport()) as gh:
                await workspaces.start(db, ws, gh, "MuskanScripts", sleep=no_sleep)
        await engine.dispose()

    asyncio.run(go())
    sync_db.expire_all()


def test_start_needs_a_click_and_queues_the_setup(
    ready: TestClient, jobs: FakeJobs, sync_db: OrmSession, github: FakeGitHub
) -> None:
    assert ready.post("/api/v1/workspaces", json={"repo": REPO, "number": 7}).status_code == 403
    resp = start(ready)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued" and [s["key"] for s in body["steps"]] == [
        "install",
        "fork",
        "sync",
        "branch",
        "codespace",
    ]
    assert jobs.queued[-1][0] == "start_workspace"
    hold = sync_db.scalar(select(Reservation))
    assert hold is not None and hold.started_at is not None
    # Nothing was written to GitHub by the API itself.
    assert github.work.writes == []
    # Starting again returns the same workspace.
    assert start(ready).json()["id"] == body["id"]


def test_install_first(ready: TestClient, github: FakeGitHub, sync_db: OrmSession) -> None:
    github.work.installed = False
    resp = start(ready)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "install_needed"
    assert detail["install_url"].startswith("https://github.com/apps/firstpr-dev/installations/new")
    assert "state=/issues/pallets/flask/7" in detail["install_url"]
    # The issue is not kept for someone who could not start.
    assert sync_db.scalar(select(Reservation).where(Reservation.status == "active")) is None
    back = ready.get(
        "/api/v1/github/installed",
        params={"installation_id": 1, "state": "/issues/pallets/flask/7"},
        follow_redirects=False,
    )
    assert back.headers["location"] == "/issues/pallets/flask/7"
    evil = ready.get(
        "/api/v1/github/installed", params={"state": "https://evil.example"}, follow_redirects=False
    )
    assert evil.headers["location"] == "/home"


def test_taken_issues_cannot_be_started(ready: TestClient, sync_db: OrmSession) -> None:
    add_card(sync_db, REPO, 8, availability="claimed")
    resp = ready.post("/api/v1/workspaces", json={"repo": REPO, "number": 8}, headers=csrf(ready))
    assert resp.status_code == 409 and resp.json()["detail"]["code"] == "taken"


def test_live_steps_stream_and_the_whole_way_to_a_pull_request(
    ready: TestClient, sync_db: OrmSession, github: FakeGitHub
) -> None:
    ws_id = start(ready).json()["id"]
    run_worker(sync_db, github, ws_id)
    page = ready.get(f"/api/v1/workspaces/{ws_id}").json()
    assert page["status"] == "ready" and page["codespace"]["url"].endswith(".github.dev")
    assert page["clone_url"] == "https://github.com/MuskanScripts/flask.git"

    events = ready.get(f"/api/v1/workspaces/{ws_id}/events")
    assert events.headers["content-type"].startswith("text/event-stream")
    assert events.text.startswith("event: workspace\ndata: ") and '"status":"ready"' in events.text

    # "I finished" before any commit: nothing to show, and no pull request yet.
    assert ready.get(f"/api/v1/workspaces/{ws_id}/changes").json()["ahead_by"] == 0
    pull = {"title": "Fix the broken link", "body": "Fixes #7"}
    early = ready.post(f"/api/v1/workspaces/{ws_id}/pull-request", json=pull, headers=csrf(ready))
    assert early.status_code == 409 and early.json()["detail"]["code"] == "no_commits"

    github.work.ahead_by = 2
    github.work.template = "## Checklist\n- [ ] tests"
    changes = ready.get(f"/api/v1/workspaces/{ws_id}/changes").json()
    assert changes["ahead_by"] == 2 and changes["files"][0]["filename"] == "docs/a.md"
    assert changes["commits"][0]["message"] == "Change 1"
    draft = ready.get(f"/api/v1/workspaces/{ws_id}/pull-request/draft").json()
    assert draft["body"].startswith("Fixes #7") and "Checklist" in draft["body"]
    assert draft["head"] == "MuskanScripts:firstpr/7-docs-fix-the-broken-link"

    writes_before = len(github.work.writes)
    assert ready.post(f"/api/v1/workspaces/{ws_id}/pull-request", json=pull).status_code == 403
    opened = ready.post(
        f"/api/v1/workspaces/{ws_id}/pull-request", json=pull, headers=csrf(ready)
    ).json()
    assert opened["opened"] and opened["workspace"]["status"] == "pr_open"
    assert opened["workspace"]["pull_request"]["url"].endswith("/pull/100")
    assert github.work.writes[writes_before:] == [("POST", "/repos/pallets/flask/pulls")]
    # Clicking again does not open a second one.
    again = ready.post(
        f"/api/v1/workspaces/{ws_id}/pull-request", json=pull, headers=csrf(ready)
    ).json()
    assert again["opened"] and len(github.work.pulls) == 1


def test_when_github_refuses_the_pull_request_its_own_form_is_offered(
    ready: TestClient, sync_db: OrmSession, github: FakeGitHub
) -> None:
    ws_id = start(ready, mode="local").json()["id"]
    run_worker(sync_db, github, ws_id)
    github.work.ahead_by = 1
    github.work.pull_error = (403, "Resource not accessible by integration")
    resp = ready.post(
        f"/api/v1/workspaces/{ws_id}/pull-request",
        json={"title": "Fix it", "body": "Fixes #7"},
        headers=csrf(ready),
    ).json()
    assert resp["opened"] is False
    assert resp["manual_url"].startswith(
        "https://github.com/pallets/flask/compare/main...MuskanScripts:firstpr/7-"
    )
    assert "title=Fix+it" in resp["manual_url"]
    # Once the user opened it on GitHub, FirstPR picks it up.
    github.work.pull_error = None
    github.work.pulls.append(
        {
            "number": 5,
            "html_url": "https://github.com/pallets/flask/pull/5",
            "head": "MuskanScripts:firstpr/7-docs-fix-the-broken-link",
        }
    )
    changes = ready.get(f"/api/v1/workspaces/{ws_id}/changes").json()
    assert changes["pull_request"]["url"].endswith("/pull/5")


def test_practice_first_and_at_most_three_open(
    ready: TestClient, sync_db: OrmSession, github: FakeGitHub
) -> None:
    ws_id = start(ready, mode="local").json()["id"]
    run_worker(sync_db, github, ws_id)
    github.work.ahead_by = 1
    settings = ready.app.state.settings  # type: ignore[attr-defined]
    pull = {"title": "Fix", "body": "Fixes #7"}

    settings.practice_repo = "MuskanScripts/firstpr-practice"
    blocked = ready.post(f"/api/v1/workspaces/{ws_id}/pull-request", json=pull, headers=csrf(ready))
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "practice_first"
    listing = ready.get("/api/v1/workspaces").json()
    assert listing["practice_repo"] == "MuskanScripts/firstpr-practice"
    assert listing["practice_done"] is False

    settings.practice_repo = ""
    user_id = sync_db.scalar(select(Workspace.user_id))
    for n in range(3):
        sync_db.add(
            Workspace(
                user_id=user_id,
                repo_full_name=f"a/b{n}",
                number=n,
                issue_title="x",
                mode="local",
                status="pr_open",
                steps=[],
                pr_url=f"https://x/{n}",
            )
        )
    sync_db.commit()
    full = ready.post(f"/api/v1/workspaces/{ws_id}/pull-request", json=pull, headers=csrf(ready))
    assert full.status_code == 409 and full.json()["detail"]["code"] == "too_many_open"


def test_close_releases_the_issue_and_can_delete_the_codespace(
    ready: TestClient, sync_db: OrmSession, github: FakeGitHub
) -> None:
    ws_id = start(ready).json()["id"]
    run_worker(sync_db, github, ws_id)
    name = ready.get(f"/api/v1/workspaces/{ws_id}").json()["codespace"]["name"]
    closed = ready.post(
        f"/api/v1/workspaces/{ws_id}/close", json={"delete_codespace": True}, headers=csrf(ready)
    ).json()
    assert closed["status"] == "closed" and name not in github.work.codespaces
    assert sync_db.scalar(select(Reservation).where(Reservation.status == "active")) is None
    assert ready.get("/api/v1/workspaces").json()["items"] == []


def test_a_started_pick_cannot_be_swapped(ready: TestClient, sync_db: OrmSession) -> None:
    today = ready.get("/api/v1/me/today").json()
    assert today["pick"]["number"] == 7 and today["started"] is False
    start(ready)
    assert ready.get("/api/v1/me/today").json()["started"] is True
    swap = ready.post("/api/v1/me/today/another", headers=csrf(ready))
    assert swap.status_code == 409


def test_someone_elses_workspace_is_not_found(ready: TestClient, sync_db: OrmSession) -> None:
    sync_db.add(
        Workspace(
            user_id=999,
            repo_full_name="a/b",
            number=1,
            issue_title="x",
            mode="local",
            status="ready",
            steps=[],
        )
    )
    sync_db.commit()
    other_id = sync_db.scalar(select(Workspace.id).where(Workspace.user_id == 999))
    assert ready.get(f"/api/v1/workspaces/{other_id}").status_code == 404
    assert ready.get(f"/api/v1/workspaces/{other_id}/events").status_code == 404


def test_stream_settings_are_sane() -> None:
    assert api_workspaces.STREAM_EVERY <= 5 and api_workspaces.STREAM_SECONDS >= 300
