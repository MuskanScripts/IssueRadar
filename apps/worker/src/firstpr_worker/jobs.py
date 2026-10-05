"""Background jobs: syncing the catalogue and people's own repos, and webhooks.

`ctx` is the arq job context. `on_startup` in main.py fills it with the
database, the engine's catalogue, the app's token source and so on; tests fill
it with fakes.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from firstpr_platform import accounts, picks, plan, workspaces
from firstpr_platform.db import (
    CatalogueRepo,
    GitHubAccount,
    IssueCard,
    Profile,
    RepoSync,
    Session,
    User,
    Watch,
    WebhookEvent,
    Workspace,
    utcnow,
)
from firstpr_platform.github_user import UserGitHub
from firstpr_worker.catalogue import APP_OWNER, Card, SyncResult, engine_user_id, pack_repos

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


async def _store_cards(ctx: dict[str, Any], by_repo: dict[str, list[Card]]) -> int:
    """Replace the issue cards of these repos with the engine's latest verdicts."""
    now = utcnow()
    stored = 0
    async with ctx["db"]() as db:
        for repo, cards in by_repo.items():
            existing = {
                row.number: row
                for row in await db.scalars(
                    select(IssueCard).where(func.lower(IssueCard.repo_full_name) == repo.lower())
                )
            }
            for card in cards:
                values = asdict(card)
                row = existing.pop(card.number, None)
                if row is None:
                    db.add(IssueCard(**values, changed_at=now, refreshed_at=now))
                else:
                    # "Changed" is what people notice: new activity, or claimed or freed.
                    if row.availability != card.availability or row.updated_at != card.updated_at:
                        row.changed_at = now
                    for key, value in values.items():
                        setattr(row, key, value)
                    row.refreshed_at = now
                stored += 1
            # Closed, or gone from GitHub since the last sync.
            for row in existing.values():
                await db.delete(row)
        await db.commit()
    return stored


async def _export(ctx: dict[str, Any], result: SyncResult) -> None:
    names = {o.full_name for o in result.outcomes if o.status in ("synced", "archived")}
    if names:
        by_repo = await asyncio.to_thread(ctx["catalogue"].cards, names)
        await _store_cards(ctx, by_repo)


async def refresh_cards(ctx: dict[str, Any]) -> int:
    """Rebuild every issue card from what the engine already stored (no GitHub calls)."""
    async with ctx["db"]() as db:
        sync_plan = await plan.build(db)
    names = sync_plan.app | {r for repos in sync_plan.by_user.values() for r in repos}
    by_repo = await asyncio.to_thread(ctx["catalogue"].cards, names)
    return await _store_cards(ctx, by_repo)


async def cards_if_empty(ctx: dict[str, Any]) -> bool:
    """Queue a rebuild when there are no cards yet, e.g. the first start after an upgrade."""
    async with ctx["db"]() as db:
        if await db.scalar(select(func.count()).select_from(IssueCard)):
            return False
    await ctx["redis"].enqueue_job("refresh_cards", _job_id="refresh-cards")
    return True


async def make_daily_picks(ctx: dict[str, Any]) -> int:
    """Hold today's pick for everyone active lately whose local day has none yet."""
    since = utcnow() - timedelta(days=ctx["settings"].active_days)
    async with ctx["db"]() as db:
        active = select(Session.user_id).where(Session.last_seen_at >= since)
        ids = list(
            await db.scalars(
                select(Profile.user_id).where(
                    Profile.onboarded_at.is_not(None), Profile.user_id.in_(active)
                )
            )
        )
    made = 0
    for user_id in ids:
        async with ctx["db"]() as db:
            if await picks.todays_pick(db, user_id) is not None:
                made += 1
    return made


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
    await _export(ctx, result)
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
    await _export(ctx, result)
    await _budget(ctx, f"user:{user_id}", result.budget)
    return f"{result.status}: {len(result.outcomes)} of {len(repos)} repos"


async def sync_active_users(ctx: dict[str, Any]) -> int:
    """Queue a personal sync for everyone who used the site recently and watches repos."""
    since = utcnow() - timedelta(days=ctx["settings"].active_days)
    async with ctx["db"]() as db:
        active = select(Session.user_id).where(Session.last_seen_at >= since).distinct()
        watching = select(Watch.user_id).distinct()
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


# ------------------------------------------------------------- workspaces

POLL_EVERY_SECONDS = 10
POLL_TRIES = 60


def _user_github(ctx: dict[str, Any], token: str) -> UserGitHub:
    return UserGitHub(
        token, api_url=ctx["settings"].github_api_url, transport=ctx.get("github_transport")
    )


async def _token_for(ctx: dict[str, Any], db: Any, user_id: int) -> tuple[str | None, str]:
    box, oauth = ctx.get("box"), ctx.get("oauth")
    user = await db.get(User, user_id)
    if user is None or box is None or oauth is None:
        return None, ""
    return await accounts.usable_token(db, user.github, box, oauth), user.github.login


async def start_workspace(ctx: dict[str, Any], workspace_id: int) -> str:
    """Fork, branch and Codespace for a workspace. Queued only by the user's click."""
    async with ctx["db"]() as db:
        ws = await db.get(Workspace, workspace_id)
        if ws is None or ws.status not in (workspaces.QUEUED, workspaces.FAILED):
            return "nothing to do"
        token, login = await _token_for(ctx, db, ws.user_id)
        if token is None:
            ws.status = workspaces.FAILED
            ws.note = "Reconnect your GitHub account, then try again."
            await db.commit()
            return "needs reconnecting"
        async with _user_github(ctx, token) as gh:
            await workspaces.start(db, ws, gh, login, sleep=ctx.get("sleep", asyncio.sleep))
        if ws.status == workspaces.WORKING and ws.codespace_name:
            await ctx["redis"].enqueue_job("poll_workspace", ws.id, 1, _defer_by=POLL_EVERY_SECONDS)
        return str(ws.status)


async def poll_workspace(ctx: dict[str, Any], workspace_id: int, tries: int) -> str:
    """Follow a starting Codespace closely for the first few minutes (reads only)."""
    async with ctx["db"]() as db:
        ws = await db.get(Workspace, workspace_id)
        if ws is None or ws.status != workspaces.WORKING:
            return "done"
        token, _ = await _token_for(ctx, db, ws.user_id)
        if token is None:
            return "needs reconnecting"
        async with _user_github(ctx, token) as gh:
            state = await workspaces.check_codespace(db, ws, gh)
        if ws.status == workspaces.WORKING and tries < POLL_TRIES:
            await ctx["redis"].enqueue_job(
                "poll_workspace", ws.id, tries + 1, _defer_by=POLL_EVERY_SECONDS
            )
        return state or "no codespace"


async def check_workspaces(ctx: dict[str, Any]) -> int:
    """Every few minutes: Codespace states, and pull requests opened on GitHub's own form.

    Only reads. Stopping idle Codespaces and deleting old ones is left to GitHub
    (idle timeout and retention period set when the Codespace was created).
    """
    async with ctx["db"]() as db:
        rows = list(
            await db.scalars(
                select(Workspace).where(
                    Workspace.status.in_((workspaces.WORKING, workspaces.READY))
                )
            )
        )
        checked = 0
        tokens: dict[int, str | None] = {}
        for ws in rows:
            if ws.user_id not in tokens:
                tokens[ws.user_id] = (await _token_for(ctx, db, ws.user_id))[0]
            token = tokens[ws.user_id]
            if token is None:
                continue
            async with _user_github(ctx, token) as gh:
                if ws.codespace_name and ws.codespace_state != "Deleted":
                    await workspaces.check_codespace(db, ws, gh)
                if ws.status == workspaces.READY and ws.fork_full_name and ws.branch:
                    pull = await gh.open_pull(
                        ws.repo_full_name, f"{ws.fork_full_name.split('/')[0]}:{ws.branch}"
                    )
                    if pull:
                        workspaces.record_pull(ws, pull)
                        await db.commit()
            checked += 1
    return checked
