"""Workspace jobs: setup after a click, following the Codespace, and the rule that
scheduled jobs never write to GitHub."""

from __future__ import annotations

from typing import Any

from fake_user_github import FakeUserGitHub
from sqlalchemy.orm import Session as OrmSession
from test_jobs import add_user

from firstpr_platform import workspaces
from firstpr_platform.crypto import TokenBox
from firstpr_platform.db import CatalogueRepo, Profile, Workspace, utcnow
from firstpr_worker import jobs
from firstpr_worker.main import WorkerSettings


def add_workspace(sync_db: OrmSession, user_id: int, **values: Any) -> Workspace:
    fields: dict[str, Any] = {
        "user_id": user_id,
        "repo_full_name": "a/one",
        "number": 7,
        "issue_title": "Fix the docs",
        "mode": "codespace",
        "status": workspaces.QUEUED,
        "steps": workspaces.new_steps("codespace"),
    }
    ws = Workspace(**{**fields, **values})
    sync_db.add(ws)
    sync_db.commit()
    return ws


async def test_setup_runs_after_the_click(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox, user_github: FakeUserGitHub
) -> None:
    user = add_user(sync_db, box, "ready")
    ws = add_workspace(sync_db, user.id)
    user_github.codespace_state = "Starting"
    assert await jobs.start_workspace(ctx, ws.id) == workspaces.WORKING
    assert ctx["redis"].queued[-1][0] == "poll_workspace"

    user_github.codespace_state = "Available"
    assert await jobs.poll_workspace(ctx, ws.id, 1) == "Available"
    sync_db.expire_all()
    done = sync_db.get(Workspace, ws.id)
    assert done is not None and done.status == workspaces.READY
    # A second run of the job does nothing.
    assert await jobs.start_workspace(ctx, ws.id) == "nothing to do"


async def test_the_regular_check_finds_pull_requests_opened_on_github(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox, user_github: FakeUserGitHub
) -> None:
    user = add_user(sync_db, box, "ready")
    ws = add_workspace(sync_db, user.id)
    await jobs.start_workspace(ctx, ws.id)
    user_github.pulls.append(
        {
            "number": 3,
            "html_url": "https://github.com/a/one/pull/3",
            "head": "ready:firstpr/7-fix-the-docs",
        }
    )
    assert await jobs.check_workspaces(ctx) == 1
    sync_db.expire_all()
    found = sync_db.get(Workspace, ws.id)
    assert found is not None and found.status == workspaces.PR_OPEN and found.pr_number == 3


async def test_scheduled_jobs_never_write_to_github(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox, user_github: FakeUserGitHub
) -> None:
    """Writes happen only after a click. Every scheduled job is run here, with
    workspaces in every state, and GitHub must see reads only."""
    user = add_user(sync_db, box, "ready")
    sync_db.add(CatalogueRepo(full_name="a/one", source="pack"))
    sync_db.add(
        Profile(user_id=user.id, level="beginner", packs=[], timezone="UTC", onboarded_at=utcnow())
    )
    sync_db.commit()
    for number, status in enumerate(
        [
            workspaces.QUEUED,
            workspaces.WORKING,
            workspaces.READY,
            workspaces.FAILED,
            workspaces.PR_OPEN,
            workspaces.CLOSED,
        ],
        start=1,
    ):
        add_workspace(
            sync_db,
            user.id,
            number=number,
            status=status,
            fork_full_name="ready/one",
            branch=f"firstpr/{number}",
            codespace_name=f"cs-{number}",
        )
    user_github.codespaces["cs-2"] = {"name": "cs-2", "web_url": "https://cs-2.github.dev"}

    scheduled = {c.coroutine.__name__ for c in WorkerSettings.cron_jobs}  # type: ignore[attr-defined]
    assert scheduled == {
        "heartbeat",
        "sync_catalogue",
        "sync_active_users",
        "make_daily_picks",
        "check_workspaces",
        "track_active_users",
        "send_digests",
        "flush_activity",
        "check_opt_outs",
    }
    await jobs.sync_catalogue(ctx)
    await jobs.sync_active_users(ctx)
    await jobs.make_daily_picks(ctx)
    await jobs.check_workspaces(ctx)
    for ws_id in range(1, 7):
        await jobs.poll_workspace(ctx, ws_id, 1)
    await jobs.refresh_cards(ctx)
    await jobs.track_active_users(ctx)
    await jobs.track_user(ctx, user.id)  # what track_active_users queues
    await jobs.send_digests(ctx)
    await jobs.flush_activity(ctx)
    await jobs.check_opt_outs(ctx)
    assert any(method == "GET" for method, _ in user_github.calls)
    assert user_github.writes == []
