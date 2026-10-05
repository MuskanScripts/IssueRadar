"""XP from merges (once, even with duplicate webhooks), site minutes from Redis to the
calendar, and commits counted on the user's own day."""

from __future__ import annotations

from typing import Any

from fake_user_github import FakeUserGitHub
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from test_jobs import add_user
from test_pull_jobs import REPO, pull

from firstpr_platform import workspaces
from firstpr_platform.crypto import TokenBox
from firstpr_platform.db import DailyActivity, Profile, User, Workspace, XpTransaction
from firstpr_worker import jobs


def workspace(sync_db: OrmSession, user_id: int, **values: Any) -> Workspace:
    fields: dict[str, Any] = {
        "user_id": user_id,
        "repo_full_name": REPO,
        "number": 7,
        "issue_title": "Fix",
        "mode": "local",
        "status": workspaces.PR_OPEN,
        "steps": [],
        "pr_number": 5,
        "pr_url": "u",
        "pr_state": "open",
    }
    ws = Workspace(**{**fields, **values})
    sync_db.add(ws)
    sync_db.commit()
    return ws


def xp(sync_db: OrmSession, user_id: int) -> int:
    sync_db.expire_all()
    user = sync_db.get(User, user_id)
    assert user is not None
    return user.xp


async def test_a_merge_pays_once_even_when_the_webhook_comes_twice(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    user = add_user(sync_db, box, "ready")
    workspace(sync_db, user.id)
    fake = ctx["catalogue"]
    fake.pulls = [pull(review="APPROVED")]
    await jobs.track_pull(ctx, user.id, REPO, 5)
    assert xp(sync_db, user.id) == 20  # approved
    fake.pulls = [pull(merged=True)]
    for _ in range(3):  # the merge webhook, delivered more than once
        await jobs.track_pull(ctx, user.id, REPO, 5)
    assert xp(sync_db, user.id) == 120
    reasons = sorted(r for (r,) in sync_db.execute(select(XpTransaction.reason)).all())
    assert reasons == ["pr_approved", "pr_merged"]


async def test_old_merges_found_by_search_are_not_paid(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    user = add_user(sync_db, box, "ready")
    ctx["catalogue"].pulls = [pull(number=9, merged=True)]  # merged before FirstPR knew it
    await jobs.track_user(ctx, user.id)
    assert xp(sync_db, user.id) == 0
    ctx["catalogue"].pulls = [pull(number=10)]
    await jobs.track_user(ctx, user.id)
    ctx["catalogue"].pulls = [pull(number=10, merged=True)]  # merged while FirstPR watched
    await jobs.track_user(ctx, user.id)
    assert xp(sync_db, user.id) == 100


async def test_practice_pays_once(ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox) -> None:
    user = add_user(sync_db, box, "ready")
    workspace(sync_db, user.id, practice=True)
    ctx["catalogue"].pulls = [pull()]
    await jobs.track_pull(ctx, user.id, REPO, 5)
    await jobs.track_user(ctx, user.id)
    assert xp(sync_db, user.id) == 30


async def test_site_minutes_move_from_redis_to_the_calendar_once(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    user = add_user(sync_db, box, "ready")
    redis = ctx["redis"]
    await redis.set(f"{jobs.ACTIVITY_PREFIX}{user.id}:2026-10-05", 12)
    await redis.set(f"{jobs.ACTIVITY_PREFIX}{user.id}:2026-10-06", 3)
    await redis.sadd(jobs.ACTIVITY_DIRTY, user.id)
    assert await jobs.flush_activity(ctx) == 15
    assert await jobs.flush_activity(ctx) == 0
    rows = {r.day: r.web_minutes for r in sync_db.scalars(select(DailyActivity))}
    assert rows == {"2026-10-05": 12, "2026-10-06": 3}


async def test_commits_count_on_the_users_own_day_and_only_once(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox, user_github: FakeUserGitHub
) -> None:
    user = add_user(sync_db, box, "ready")
    sync_db.add(Profile(user_id=user.id, level="beginner", packs=[], timezone="Asia/Kolkata"))
    workspace(
        sync_db,
        user.id,
        fork_full_name="ready/one",
        branch="firstpr/7",
        base_sha="a" * 40,
        status=workspaces.READY,
        pr_url=None,
        pr_number=None,
    )
    user_github.ahead_by = 2
    user_github.commit_date = "2026-10-05T18:20:00Z"  # 23:50 in India
    await jobs.check_workspaces(ctx)
    await jobs.check_workspaces(ctx)
    sync_db.expire_all()
    rows = {r.day: r.commits for r in sync_db.scalars(select(DailyActivity))}
    assert rows == {"2026-10-05": 2}
