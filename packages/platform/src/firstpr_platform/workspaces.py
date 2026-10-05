"""Getting a user from an issue to a place where they can code.

The worker runs `start` after the user clicked Start working: check the app is
installed on their account, fork the repo (or reuse their fork), bring the fork
up to date, create a branch, and, in Codespace mode, start a Codespace. Each
step is saved as it happens, so the workspace page can show it live.

When a Codespace cannot start, the workspace falls back to working locally
with clone instructions instead of failing.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_platform.db import Workspace, utcnow
from firstpr_platform.github_user import GitHubError, UserGitHub

CODESPACE = "codespace"
LOCAL = "local"
# Workspace statuses.
QUEUED = "queued"
WORKING = "working"
READY = "ready"
FAILED = "failed"
PR_OPEN = "pr_open"
CLOSED = "closed"
LIVE = (QUEUED, WORKING, READY, FAILED, PR_OPEN)
# A Codespace that is not up after this long gets the local fallback shown next to it.
CODESPACE_PATIENCE = timedelta(minutes=10)
INSTALLATIONS_URL = "https://github.com/settings/installations"

Sleep = Callable[[float], Awaitable[None]]

STEP_LABELS = {
    "install": "Check FirstPR can work in your GitHub account",
    "fork": "Fork the repository",
    "sync": "Bring your fork up to date",
    "branch": "Create a branch for this issue",
    "codespace": "Start a Codespace",
}


def new_steps(mode: str) -> list[dict[str, str]]:
    keys = ["install", "fork", "sync", "branch"] + (["codespace"] if mode == CODESPACE else [])
    return [{"key": k, "label": STEP_LABELS[k], "state": "pending", "detail": ""} for k in keys]


def branch_name(number: int, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].rstrip("-")
    return f"firstpr/{number}-{slug}" if slug else f"firstpr/{number}"


async def open_prs(db: AsyncSession, user_id: int) -> int:
    count = await db.scalar(
        select(func.count(Workspace.id)).where(
            Workspace.user_id == user_id,
            Workspace.status == PR_OPEN,
            # Merged or closed ones (seen by the PR tracker) no longer count.
            Workspace.pr_state.in_(("open", "draft")),
        )
    )
    return count or 0


async def practice_done(db: AsyncSession, user_id: int) -> bool:
    found = await db.scalar(
        select(Workspace.id).where(
            Workspace.user_id == user_id,
            Workspace.practice.is_(True),
            Workspace.pr_url.is_not(None),
        )
    )
    return found is not None


class StepFailed(Exception):
    def __init__(self, key: str, detail: str, help_url: str | None = None) -> None:
        super().__init__(detail)
        self.key = key
        self.detail = detail
        self.help_url = help_url


def _set(ws: Workspace, key: str, state: str, detail: str = "") -> None:
    steps = [dict(s) for s in ws.steps]
    for step in steps:
        if step["key"] == key:
            step["state"] = state
            step["detail"] = detail
    ws.steps = steps  # a new list, so the JSON column is saved


def _explain(error: GitHubError, what: str) -> StepFailed:
    if error.not_installed:
        need = f" GitHub says it needs: {error.accepted}." if error.accepted else ""
        return StepFailed(
            what,
            "FirstPR's GitHub App cannot do this in your account yet. Give it access to all "
            f"repositories on GitHub, then try again.{need}",
            INSTALLATIONS_URL,
        )
    return StepFailed(what, f"GitHub said no: {error.message}")


async def _wait_for_repo(gh: UserGitHub, name: str, sleep: Sleep, seconds: int = 90) -> bool:
    """A new fork takes a few seconds to appear."""
    for _ in range(seconds // 3):
        if await gh.repo(name) is not None:
            return True
        await sleep(3)
    return await gh.repo(name) is not None


async def start(
    db: AsyncSession,
    ws: Workspace,
    gh: UserGitHub,
    login: str,
    sleep: Sleep = asyncio.sleep,
) -> None:
    """Run every step that is not done yet. Safe to run again after a failure."""
    current = "install"

    async def step(key: str, state: str, detail: str = "") -> None:
        nonlocal current
        current = key
        _set(ws, key, state, detail)
        await db.commit()

    ws.status, ws.note, ws.help_url = WORKING, None, None
    try:
        await step("install", "running")
        if not await gh.app_installed(login):
            raise StepFailed(
                "install",
                "Install FirstPR's GitHub App on your account first, so it can fork and "
                "create branches for you.",
            )
        await step("install", "done")

        await step("fork", "running")
        upstream = await gh.repo(ws.repo_full_name)
        if upstream is None:
            raise StepFailed("fork", f"{ws.repo_full_name} is gone from GitHub.")
        ws.base_branch = str(upstream["default_branch"])
        name = ws.repo_full_name.split("/")[1]
        mine = await gh.repo(f"{login}/{name}")
        parent = str((mine or {}).get("parent", {}).get("full_name", ""))
        if mine and mine.get("fork") and parent.lower() == ws.repo_full_name.lower():
            ws.fork_full_name = str(mine["full_name"])
            await step("fork", "done", f"Using your fork {ws.fork_full_name}")
        else:
            made = await gh.fork(ws.repo_full_name)
            ws.fork_full_name = str(made["full_name"])
            if not await _wait_for_repo(gh, ws.fork_full_name, sleep):
                raise StepFailed(
                    "fork",
                    f"GitHub made {ws.fork_full_name}, but FirstPR cannot see it. Give the "
                    "FirstPR app access to all repositories, then try again.",
                    INSTALLATIONS_URL,
                )
            await step("fork", "done", f"Forked to {ws.fork_full_name}")
        fork = ws.fork_full_name

        await step("sync", "running")
        try:
            await gh.sync_fork(fork, ws.base_branch)
            await step("sync", "done")
        except GitHubError as error:
            if error.status != 409:
                raise
            # The fork's main branch has commits of its own. Branch from upstream anyway.
            await step("sync", "skipped", "Your fork has its own changes; branching from upstream")
        sha = await gh.branch_sha(fork, ws.base_branch)
        upstream_sha = await gh.branch_sha(ws.repo_full_name, ws.base_branch)
        ws.base_sha = upstream_sha or sha

        await step("branch", "running")
        ws.branch = ws.branch or branch_name(ws.number, ws.issue_title)
        if await gh.branch_sha(fork, ws.branch) is None:
            if ws.base_sha is None:
                raise StepFailed("branch", f"Could not read {ws.base_branch} on {fork}.")
            await gh.create_branch(fork, ws.branch, ws.base_sha)
        await step("branch", "done", ws.branch)

        if ws.mode == CODESPACE:
            await step("codespace", "running")
            existing = await gh.codespace(ws.codespace_name) if ws.codespace_name else None
            try:
                space = existing or await gh.create_codespace(fork, ws.branch)
            except GitHubError as error:
                fall_back(ws, f"The Codespace could not be created: {error.message}")
                await db.commit()
                return
            ws.codespace_name = str(space["name"])
            ws.codespace_url = space.get("web_url")
            ws.codespace_state = space.get("state")
            ws.codespace_checked_at = utcnow()
            await db.commit()
            await check_codespace(db, ws, gh)
        else:
            ws.status = READY
            await db.commit()
    except StepFailed as failed:
        _set(ws, failed.key, "failed", failed.detail)
        ws.status, ws.note, ws.help_url = FAILED, failed.detail, failed.help_url
        await db.commit()
    except GitHubError as error:
        explained = _explain(error, current)
        _set(ws, current, "failed", explained.detail)
        ws.status, ws.note, ws.help_url = FAILED, explained.detail, explained.help_url
        await db.commit()


def record_pull(ws: Workspace, pull: dict[str, Any]) -> None:
    ws.pr_number = int(pull["number"])
    ws.pr_url = str(pull["html_url"])
    ws.pr_state = "draft" if pull.get("draft") else "open"
    ws.pr_opened_at = ws.pr_opened_at or utcnow()
    ws.status = PR_OPEN


def fall_back(ws: Workspace, why: str) -> None:
    """Keep the user going on their own computer instead of showing an error."""
    _set(ws, "codespace", "failed", why)
    ws.mode = LOCAL
    ws.status = READY
    why = why.strip()
    if not why.endswith((".", "!", "?")):
        why += "."
    ws.note = f"{why} You can still work on this issue on your own computer, as shown below."


async def check_codespace(db: AsyncSession, ws: Workspace, gh: UserGitHub) -> str | None:
    """Read the Codespace's state from GitHub (read-only) and update the workspace."""
    if not ws.codespace_name:
        return None
    space = await gh.codespace(ws.codespace_name)
    ws.codespace_checked_at = utcnow()
    if space is None:
        ws.codespace_state = "Deleted"
        if ws.status == WORKING:
            fall_back(ws, "The Codespace is gone.")
        await db.commit()
        return ws.codespace_state
    state = str(space.get("state") or "Unknown")
    ws.codespace_state = state
    ws.codespace_url = space.get("web_url") or ws.codespace_url
    if ws.status == WORKING:
        if state in ("Available", "Shutdown", "ShuttingDown"):
            _set(ws, "codespace", "done", f"{ws.codespace_name} is ready")
            ws.status = READY
        elif state in ("Failed", "Unavailable", "Deleted"):
            fall_back(ws, f"The Codespace did not start (GitHub says: {state}).")
        elif utcnow() - ws.created_at > CODESPACE_PATIENCE and ws.note is None:
            ws.note = (
                "The Codespace is taking longer than usual. It may still open; if not, "
                "work on your own computer as shown below."
            )
    await db.commit()
    return state
