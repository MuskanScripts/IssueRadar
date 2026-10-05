"""Background jobs: syncing the catalogue and people's own repos, and webhooks.

`ctx` is the arq job context. `on_startup` in main.py fills it with the
database, the engine's catalogue, the app's token source and so on; tests fill
it with fakes.
"""

from __future__ import annotations

import asyncio
import json
import time
import zlib
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from firstpr_platform import accounts, notify, picks, plan, workspaces
from firstpr_platform.db import (
    CatalogueRepo,
    GitHubAccount,
    IssueCard,
    Notification,
    Profile,
    RepoSync,
    Session,
    TrackedPull,
    User,
    Watch,
    WebhookEvent,
    Workspace,
    utcnow,
)
from firstpr_platform.github_user import UserGitHub
from firstpr_worker.catalogue import (
    APP_OWNER,
    Card,
    SyncResult,
    Tracked,
    engine_user_id,
    pack_repos,
)

# Must match BUDGET_PREFIX in apps/api.
BUDGET_PREFIX = "firstpr:budget:"
BUDGET_TTL_SECONDS = 2 * 3600
REPO_EVENTS = {"issues", "issue_comment", "pull_request", "pull_request_review", "repository"}
# Events that can change a pull request's status.
PULL_EVENTS = {
    "pull_request",
    "pull_request_review",
    "pull_request_review_comment",
    "issue_comment",
    "check_suite",
    "check_run",
    "status",
}
SOON_SECONDS = 60
# A review should show up in FirstPR within a minute of the webhook.
PULL_SOON_SECONDS = 5


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


def _pull_numbers(event: WebhookEvent) -> set[int]:
    """Which pull requests a delivery is about. Empty means "any in this repo"."""
    try:
        payload = json.loads(event.payload)
    except ValueError:
        return set()
    if event.event in ("pull_request", "pull_request_review", "pull_request_review_comment"):
        number = (payload.get("pull_request") or {}).get("number")
        return {int(number)} if number else set()
    if event.event == "issue_comment":
        issue = payload.get("issue") or {}
        # Comments on pull requests come as issue comments with a "pull_request" key.
        is_pull = "pull_request" in issue and issue.get("number")
        return {int(issue["number"])} if is_pull else set()
    if event.event in ("check_suite", "check_run"):
        holder = payload.get(event.event) or {}
        return {int(p["number"]) for p in holder.get("pull_requests") or [] if p.get("number")}
    return set()


async def _queue_tracked_pulls(ctx: dict[str, Any], db: Any, event: WebhookEvent) -> int:
    """Check tracked pull requests this delivery is about, a few seconds from now."""
    numbers = _pull_numbers(event)
    query = select(TrackedPull).where(
        func.lower(TrackedPull.repo_full_name) == (event.repo_full_name or "").lower(),
        TrackedPull.state == "open",
    )
    if numbers:
        query = query.where(TrackedPull.number.in_(numbers))
    elif event.event != "status":
        return 0
    rows = list(await db.scalars(query))
    for row in rows:
        await ctx["redis"].enqueue_job(
            "track_pull",
            row.user_id,
            row.repo_full_name,
            row.number,
            _job_id=f"track-pull:{row.user_id}:{row.repo_full_name.lower()}#{row.number}",
            _defer_by=PULL_SOON_SECONDS,
        )
    return len(rows)


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
        elif (
            event.event in PULL_EVENTS
            and event.repo_full_name
            and (queued := await _queue_tracked_pulls(ctx, db, event))
        ):
            result = f"{queued} pull request(s) to check"
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
        await _workspace_problem(ctx, db, ws)
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


async def _workspace_problem(ctx: dict[str, Any], db: Any, ws: Workspace) -> None:
    """Tell the user when setup stopped, or the Codespace fell back to local."""
    if ws.status != workspaces.FAILED and not any(
        s["key"] == "codespace" and s["state"] == "failed" for s in ws.steps
    ):
        return
    stopped = ws.status == workspaces.FAILED
    note = await notify.add(
        db,
        ws.user_id,
        "workspace_problem",
        f"{'Setup stopped' if stopped else 'No Codespace'} for {ws.repo_full_name}#{ws.number}",
        ws.note or "Open the workspace to see what happened.",
        dedupe_key=f"ws:{ws.id}:{ws.status}:{zlib.crc32((ws.note or '').encode())}",
        link=f"/workspaces/{ws.id}",
    )
    if note is not None:
        await _email_now(ctx, db, ws.user_id, [note])


# ---------------------------------------------------------- pull requests

TRACK_EVERY_HOURS = 2
DIGEST_HOUR = 8  # local time
TIMELINE_KEEP = 10


async def _email_now(ctx: dict[str, Any], db: Any, user_id: int, notes: list[Notification]) -> None:
    mailer: notify.Mailer | None = ctx.get("mailer")
    urgent = [n for n in notes if n.kind in notify.IMMEDIATE]
    if mailer is not None and urgent:
        await mailer.send_to_user(db, user_id, urgent)


async def _store_pulls(
    ctx: dict[str, Any], db: Any, user_id: int, found: list[Tracked]
) -> list[Notification]:
    """Save each pull request's status; a change of status becomes a notification."""
    now = utcnow()
    existing = {
        (row.repo_full_name.lower(), row.number): row
        for row in await db.scalars(select(TrackedPull).where(TrackedPull.user_id == user_id))
    }
    changes: list[tuple[str, str | None, Tracked]] = []
    for item in found:
        facts, status = item.facts, item.status
        key = (facts.repo.lower(), facts.number)
        row = existing.get(key)
        old = row.status if row else None
        if row is None:
            row = TrackedPull(user_id=user_id, repo_full_name=facts.repo, number=facts.number)
            db.add(row)
            existing[key] = row
        row.title = facts.title
        row.url = facts.url
        row.state = facts.state
        row.merged = facts.merged
        row.draft = facts.draft
        row.status = status.status.value
        row.needs_you = status.needs_you
        row.reasons = list(status.reasons)
        row.nudge = item.nudge
        row.days_quiet = status.days_quiet
        row.opened_at = facts.opened_at
        row.closed_at = facts.closed_at
        row.timeline = [
            {"at": a.at.isoformat(), "text": a.text} for a in item.activity[-TIMELINE_KEEP:]
        ]
        row.checked_at = now
        if old != row.status:
            row.changed_at = now
            changes.append((row.status, old, item))
        # Keep the workspace in step, so "open pull requests" counts only open ones.
        ws = await db.scalar(
            select(Workspace).where(
                Workspace.user_id == user_id,
                func.lower(Workspace.repo_full_name) == facts.repo.lower(),
                Workspace.pr_number == facts.number,
            )
        )
        if ws is not None:
            ws.pr_state = (
                "merged"
                if facts.merged
                else ("closed" if facts.state == "closed" else ("draft" if facts.draft else "open"))
            )
    await db.commit()

    notes: list[Notification] = []
    for new, old, item in changes:
        # Only changes count: the first time a pull request is seen is not news.
        if old is None or new not in notify.PR_KINDS:
            continue
        kind, title = notify.PR_KINDS[new]
        note = await notify.add(
            db,
            user_id,
            kind,
            title.format(title=item.facts.title),
            f"{item.facts.repo}#{item.facts.number}: {item.status.needs_you}",
            dedupe_key=f"pr:{item.facts.repo.lower()}#{item.facts.number}:{old}>{new}:"
            f"{utcnow():%Y-%m-%dT%H}",
            link="/pulls",
            external_url=item.facts.url,
        )
        if note is not None:
            notes.append(note)
    await _email_now(ctx, db, user_id, notes)
    return notes


async def _track(ctx: dict[str, Any], user_id: int, only: tuple[str, int] | None = None) -> str:
    async with ctx["db"]() as db:
        token, login = await _token_for(ctx, db, user_id)
        if token is None:
            return "skipped: no usable GitHub token"
        if only is not None:
            known = [only]
        else:
            rows = await db.execute(
                select(TrackedPull.repo_full_name, TrackedPull.number).where(
                    TrackedPull.user_id == user_id, TrackedPull.state == "open"
                )
            )
            made = await db.execute(
                select(Workspace.repo_full_name, Workspace.pr_number).where(
                    Workspace.user_id == user_id, Workspace.pr_number.is_not(None)
                )
            )
            known = [*((r, n) for r, n in made.all() if n is not None)]
            known += [(r, n) for r, n in rows.all()]
        result = await ctx["catalogue"].track(
            token,
            f"user:{user_id}",
            login,
            known,
            discover=only is None,
            now=utcnow(),
        )
        notes = await _store_pulls(ctx, db, user_id, result.pulls)
    return f"{len(result.pulls)} pull requests, {len(notes)} new notifications"


async def track_user(ctx: dict[str, Any], user_id: int) -> str:
    """All of a user's pull requests: the ones FirstPR knows, and a search for others."""
    return await _track(ctx, user_id)


async def track_pull(ctx: dict[str, Any], user_id: int, repo: str, number: int) -> str:
    """One pull request, soon after a webhook said something happened on it."""
    return await _track(ctx, user_id, (repo, number))


async def track_active_users(ctx: dict[str, Any]) -> int:
    """Every 2 hours: pull requests of everyone who used the site lately (reads only)."""
    since = utcnow() - timedelta(days=ctx["settings"].active_days)
    async with ctx["db"]() as db:
        ids = list(
            await db.scalars(
                select(Session.user_id).where(Session.last_seen_at >= since).distinct()
            )
        )
    for user_id in ids:
        await ctx["redis"].enqueue_job("track_user", user_id, _job_id=f"track-user:{user_id}")
    return len(ids)


async def send_digests(ctx: dict[str, Any]) -> int:
    """Hourly: at 8 in the morning, local time, one email with what changed. Only when
    something did, and only for people with email and the digest on."""
    mailer: notify.Mailer | None = ctx.get("mailer")
    if mailer is None or not mailer.configured:
        return 0
    now = utcnow()
    since = now - timedelta(hours=24)
    sent = 0
    async with ctx["db"]() as db:
        users = list(
            await db.scalars(
                select(Notification.user_id)
                .where(Notification.emailed_at.is_(None), Notification.created_at >= since)
                .distinct()
            )
        )
        for user_id in users:
            taste = await picks.load_taste(db, user_id)
            local = now.astimezone(picks.zone(taste))
            settings = await notify.prefs(db, user_id)
            today = local.date().isoformat()
            if (
                local.hour != DIGEST_HOUR
                or not settings.digest
                or settings.last_digest_day == today
            ):
                continue
            notes = [n for n in await notify.unemailed(db, user_id) if n.created_at >= since]
            if await mailer.send_to_user(db, user_id, notes):
                settings.last_digest_day = today
                await db.commit()
                sent += 1
    return sent
