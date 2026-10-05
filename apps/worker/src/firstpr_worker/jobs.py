"""Background jobs: syncing the catalogue and people's own repos, and webhooks.

`ctx` is the arq job context. `on_startup` in main.py fills it with the
database, the engine's catalogue, the app's token source and so on; tests fill
it with fakes.
"""

from __future__ import annotations

import json
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import distinct, func, select

from firstpr_platform import accounts, plan
from firstpr_platform.db import (
    CatalogueRepo,
    GitHubAccount,
    RepoSync,
    Session,
    User,
    Watch,
    WebhookEvent,
    utcnow,
)
from firstpr_worker.catalogue import APP_OWNER, SyncResult, engine_user_id, pack_repos

# Must match BUDGET_PREFIX in apps/api.
BUDGET_PREFIX = "firstpr:budget:"
BUDGET_TTL_SECONDS = 2 * 3600
REPO_EVENTS = {"issues", "issue_comment", "pull_request", "pull_request_review", "repository"}
SOON_SECONDS = 60


async def seed_catalogue(ctx: dict[str, Any]) -> int:
    """Fill an empty catalogue with the starter packs' repos."""
    async with ctx["db"]() as db:
        if await db.scalar(select(func.count()).select_from(CatalogueRepo)):
            return 0
        names = pack_repos()
        db.add_all(CatalogueRepo(full_name=name, source="pack") for name in names)
        await db.commit()
    return len(names)


async def _record(ctx: dict[str, Any], result: SyncResult, repos: set[str], kind: str) -> None:
    now = utcnow()
    done = {o.full_name.lower() for o in result.outcomes}
    async with ctx["db"]() as db:
        for outcome in result.outcomes:
            await db.merge(
                RepoSync(
                    full_name=outcome.full_name,
                    token_kind=kind,
                    status=outcome.status,
                    note=(outcome.note or None) and outcome.note[:500],
                    open_issues=outcome.open_issues,
                    synced_at=now,
                )
            )
        if result.status == "interrupted":
            for name in repos:
                if name.lower() not in done:
                    existing = await db.get(RepoSync, name)
                    await db.merge(
                        RepoSync(
                            full_name=name,
                            token_kind=kind,
                            status="paused",
                            note=(result.message or "Rate limit nearly used up")[:500],
                            open_issues=existing.open_issues if existing else 0,
                            synced_at=existing.synced_at if existing else now,
                        )
                    )
        await db.commit()


async def _budget(ctx: dict[str, Any], key: str, budget: dict[str, Any]) -> None:
    if budget:
        value = json.dumps({**budget, "checked_at": time.time()})
        await ctx["redis"].set(BUDGET_PREFIX + key, value, ex=BUDGET_TTL_SECONDS)


async def sync_catalogue(ctx: dict[str, Any]) -> str:
    """The shared catalogue, with the app's own installation token."""
    tokens = ctx.get("app_tokens")
    if tokens is None:
        return "skipped: the GitHub App is not set up"
    async with ctx["db"]() as db:
        sync_plan = await plan.build(db)
    token = await tokens.token()
    result = await ctx["catalogue"].sync(APP_OWNER, sync_plan.app, token, "app")
    await _record(ctx, result, sync_plan.app, plan.APP)
    await _budget(ctx, "app", result.budget)
    return f"{result.status}: {len(result.outcomes)} of {len(sync_plan.app)} repos"


async def sync_user(ctx: dict[str, Any], user_id: int) -> str:
    """Repos only this person watches, with their own token, on their behalf."""
    box, oauth = ctx.get("box"), ctx.get("oauth")
    if box is None or oauth is None:
        return "skipped: sign-in is not set up"
    owner = engine_user_id(user_id)
    async with ctx["db"]() as db:
        sync_plan = await plan.build(db)
        repos = sync_plan.by_user.get(user_id, set())
        if not repos:
            ctx["catalogue"].clear_watchlist(owner)
            return "nothing of their own to sync"
        user = await db.get(User, user_id)
        if user is None:
            return "no such user"
        token = await accounts.usable_token(db, user.github, box, oauth)
    if token is None:
        return "skipped: GitHub access needs reconnecting"
    result = await ctx["catalogue"].sync(owner, repos, token, f"user:{user_id}")
    await _record(ctx, result, repos, plan.USER)
    await _budget(ctx, f"user:{user_id}", result.budget)
    return f"{result.status}: {len(result.outcomes)} of {len(repos)} repos"


async def sync_active_users(ctx: dict[str, Any]) -> int:
    """Queue a personal sync for everyone who used the site recently and watches repos."""
    since = utcnow() - timedelta(days=ctx["settings"].active_days)
    async with ctx["db"]() as db:
        active = select(distinct(Session.user_id)).where(Session.last_seen_at >= since)
        watching = select(distinct(Watch.user_id))
        ids = list(await db.scalars(active.where(Session.user_id.in_(watching))))
    for user_id in ids:
        await ctx["redis"].enqueue_job("sync_user", user_id, _job_id=f"sync-user:{user_id}")
    return len(ids)


async def handle_webhook(ctx: dict[str, Any], delivery_id: str) -> str:
    async with ctx["db"]() as db:
        event = await db.get(WebhookEvent, delivery_id)
        if event is None or event.processed_at is not None:
            return "already handled"
        result = "ignored"
        if event.event == "github_app_authorization" and event.action == "revoked":
            account = await db.scalar(
                select(GitHubAccount).where(GitHubAccount.github_id == event.sender_github_id)
            )
            if account is not None:
                account.status = accounts.RECONNECT_NEEDED
                result = "account marked reconnect needed"
        elif event.event in REPO_EVENTS and event.repo_full_name:
            sync_plan = await plan.build(db)
            name = event.repo_full_name.lower()
            owners = [
                u for u, repos in sync_plan.by_user.items() if name in {r.lower() for r in repos}
            ]
            if name in {r.lower() for r in sync_plan.app}:
                await ctx["redis"].enqueue_job(
                    "sync_catalogue", _job_id="sync-catalogue", _defer_by=SOON_SECONDS
                )
                result = "catalogue sync queued"
            elif owners:
                await ctx["redis"].enqueue_job(
                    "sync_user", owners[0], _job_id=f"sync-user:{owners[0]}", _defer_by=SOON_SECONDS
                )
                result = "personal sync queued"
            else:
                result = "repo not tracked"
        event.processed_at = utcnow()
        event.result = result
        await db.commit()
    return result
