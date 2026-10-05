"""Workspaces: Start working on an issue, follow the setup live, see your changes,
and open the pull request.

Every endpoint that changes something on GitHub is a POST the user's own click
sends (with the CSRF header): starting, retrying, creating the pull request,
deleting the Codespace. The slow part of starting (fork, branch, Codespace)
runs in the worker; this module queues it and streams its progress.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api.auth import safe_return
from firstpr_api.deps import Jobs, current_user, get_db, get_jobs, get_settings, require_csrf
from firstpr_api.settings import Settings
from firstpr_platform import accounts, picks
from firstpr_platform import workspaces as ws_flow
from firstpr_platform.analytics import user_id
from firstpr_platform.db import ACTIVE, IssueCard, Reservation, User, Workspace, utcnow
from firstpr_platform.github_oauth import GitHubAuthError
from firstpr_platform.github_user import GitHubError, UserGitHub

router = APIRouter()

# How long the live stream stays open, and how often it looks for changes.
STREAM_SECONDS = 15 * 60
STREAM_EVERY = 2.0


class Step(BaseModel):
    key: str
    label: str
    state: str
    detail: str


class Codespace(BaseModel):
    name: str
    url: str | None
    state: str | None


class PullRequestOut(BaseModel):
    number: int | None
    url: str
    state: str | None


class WorkspaceOut(BaseModel):
    id: int
    repo: str
    number: int
    issue_title: str
    issue_url: str | None
    practice: bool
    mode: str
    status: str
    steps: list[Step]
    note: str | None
    help_url: str | None
    fork: str | None
    branch: str | None
    base_branch: str | None
    clone_url: str | None
    codespace: Codespace | None
    pull_request: PullRequestOut | None
    created_at: datetime
    updated_at: datetime


class WorkspaceList(BaseModel):
    items: list[WorkspaceOut]
    practice_repo: str | None
    practice_done: bool
    open_prs: int
    open_pr_limit: int


class StartIn(BaseModel):
    repo: str
    number: int
    mode: Literal["codespace", "local"] = "codespace"


class RetryIn(BaseModel):
    mode: Literal["codespace", "local"] | None = None


class CloseIn(BaseModel):
    delete_codespace: bool = False


class Commit(BaseModel):
    sha: str
    message: str


class ChangedFile(BaseModel):
    filename: str
    status: str
    additions: int
    deletions: int


class Changes(BaseModel):
    ahead_by: int
    commits: list[Commit]
    files: list[ChangedFile]
    compare_url: str | None
    pull_request: PullRequestOut | None


class Draft(BaseModel):
    title: str
    body: str
    base: str
    head: str
    from_template: bool


class PullIn(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(default="", max_length=60_000)
    draft: bool = False


class PullResult(BaseModel):
    opened: bool
    # When GitHub does not let FirstPR open it: GitHub's own form, filled in, to click.
    manual_url: str | None
    workspace: WorkspaceOut


def out(ws: Workspace) -> WorkspaceOut:
    return WorkspaceOut(
        id=ws.id,
        repo=ws.repo_full_name,
        number=ws.number,
        issue_title=ws.issue_title,
        issue_url=ws.issue_url,
        practice=ws.practice,
        mode=ws.mode,
        status=ws.status,
        steps=[Step(**s) for s in ws.steps],
        note=ws.note,
        help_url=ws.help_url,
        fork=ws.fork_full_name,
        branch=ws.branch,
        base_branch=ws.base_branch,
        clone_url=f"https://github.com/{ws.fork_full_name}.git" if ws.fork_full_name else None,
        codespace=Codespace(name=ws.codespace_name, url=ws.codespace_url, state=ws.codespace_state)
        if ws.codespace_name
        else None,
        pull_request=PullRequestOut(number=ws.pr_number, url=ws.pr_url, state=ws.pr_state)
        if ws.pr_url
        else None,
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )


def _problem(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message, **extra})


async def _mine(db: AsyncSession, user: User, workspace_id: int) -> Workspace:
    ws = await db.get(Workspace, workspace_id)
    if ws is None or ws.user_id != user.id:
        raise HTTPException(404, "No such workspace")
    return ws


async def _github(request: Request, db: AsyncSession, user: User) -> UserGitHub:
    oauth, box = request.app.state.oauth, request.app.state.token_box
    if oauth is None or box is None:
        raise HTTPException(503, "Sign-in is not set up on this server")
    try:
        token = await accounts.usable_token(db, user.github, box, oauth)
    except GitHubAuthError:
        token = None
    if token is None:
        raise _problem(409, "reconnect", "Reconnect your GitHub account first.")
    settings: Settings = request.app.state.settings
    return UserGitHub(
        token, api_url=settings.github_api_url, transport=request.app.state.github_transport
    )


def _install_url(settings: Settings, return_to: str) -> str | None:
    if not settings.github_app_slug:
        return None
    base = settings.github_web_url.rstrip("/")
    return f"{base}/apps/{settings.github_app_slug}/installations/new?state={quote(return_to)}"


def _card_query(repo: str, number: int) -> Any:
    return select(IssueCard).where(
        func.lower(IssueCard.repo_full_name) == repo.lower(), IssueCard.number == number
    )


def _is_practice(settings: Settings, repo: str) -> bool:
    return bool(settings.practice_repo) and repo.lower() == settings.practice_repo.lower()


# ------------------------------------------------------------------ list


@router.get("/workspaces", response_model=WorkspaceList)
async def list_workspaces(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> WorkspaceList:
    rows = await db.scalars(
        select(Workspace)
        .where(Workspace.user_id == user.id, Workspace.status != ws_flow.CLOSED)
        .order_by(Workspace.updated_at.desc())
    )
    return WorkspaceList(
        items=[out(ws) for ws in rows],
        practice_repo=settings.practice_repo or None,
        practice_done=await ws_flow.practice_done(db, user.id),
        open_prs=await ws_flow.open_prs(db, user.id),
        open_pr_limit=settings.max_open_prs,
    )


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: int,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> WorkspaceOut:
    return out(await _mine(db, user, workspace_id))


# ----------------------------------------------------------------- start


@router.post(
    "/workspaces",
    response_model=WorkspaceOut,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def start_working(
    body: StartIn,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    jobs: Jobs = Depends(get_jobs),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> WorkspaceOut:
    card = await db.scalar(_card_query(body.repo, body.number))
    if card is None:
        raise HTTPException(404, "We do not track this issue, or it was closed.")
    existing = await db.scalar(
        select(Workspace).where(
            Workspace.user_id == user.id,
            func.lower(Workspace.repo_full_name) == card.repo_full_name.lower(),
            Workspace.number == card.number,
        )
    )
    if existing is not None and existing.status != ws_flow.CLOSED:
        return out(existing)

    if card.availability not in picks.OPEN_STATES:
        # Claimed or with a PR now. Fine only when it is this user's own earlier start.
        mine = await db.scalar(
            select(Reservation.id).where(
                Reservation.card_id == card.id,
                Reservation.user_id == user.id,
                Reservation.status == ACTIVE,
            )
        )
        if mine is None:
            raise _problem(409, "taken", "This issue is not free any more. Pick another one.")
    try:
        await picks.hold_for_work(db, user.id, card)
    except picks.HeldByOther:
        raise _problem(
            409, "taken", "Someone else is working on this issue. Pick another one."
        ) from None

    async with await _github(request, db, user) as gh:
        try:
            installed = await gh.app_installed(user.github.login)
        except GitHubError:
            installed = False
        except httpx.HTTPError:
            raise HTTPException(502, "GitHub did not answer. Try again in a minute.") from None
    if not installed:
        await picks.release_work(db, user.id, card.id)
        path = f"/issues/{card.repo_full_name}/{card.number}"
        raise _problem(
            409,
            "install_needed",
            "FirstPR needs to be installed on your GitHub account to fork the repo and "
            "create a branch for you. You do this once.",
            install_url=_install_url(settings, path),
        )

    ws = existing or Workspace(
        user_id=user.id, repo_full_name=card.repo_full_name, number=card.number
    )
    ws.issue_title = card.title
    ws.issue_url = card.url
    ws.practice = _is_practice(settings, card.repo_full_name)
    ws.mode = body.mode
    ws.status = ws_flow.QUEUED
    ws.steps = ws_flow.new_steps(body.mode)
    ws.note = ws.help_url = None
    db.add(ws)
    await db.commit()
    taste = await picks.load_taste(db, user.id)
    await picks.log(db, user.id, card, "issue", "started", picks.fit(card, taste, utcnow()))
    await db.commit()
    await jobs.enqueue_job("start_workspace", ws.id, _job_id=f"workspace:{ws.id}")
    count = await db.scalar(select(func.count(Workspace.id)).where(Workspace.user_id == user.id))
    if count == 1:
        await request.app.state.analytics.capture("first_pick_started", user_id(user.id))
    return out(ws)


@router.post(
    "/workspaces/{workspace_id}/retry",
    response_model=WorkspaceOut,
    dependencies=[Depends(require_csrf)],
)
async def retry(
    workspace_id: int,
    body: RetryIn,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    jobs: Jobs = Depends(get_jobs),  # noqa: B008
) -> WorkspaceOut:
    ws = await _mine(db, user, workspace_id)
    if ws.status in (ws_flow.QUEUED, ws_flow.WORKING, ws_flow.PR_OPEN, ws_flow.CLOSED):
        raise HTTPException(409, "This workspace cannot be set up again right now.")
    mode = body.mode or ws.mode
    if mode == ws_flow.CODESPACE and ws.mode == ws_flow.LOCAL:
        ws.codespace_name = ws.codespace_url = ws.codespace_state = None
    ws.mode = mode
    ws.status = ws_flow.QUEUED
    ws.steps = ws_flow.new_steps(mode)
    ws.note = ws.help_url = None
    await db.commit()
    await jobs.enqueue_job("start_workspace", ws.id, _job_id=f"workspace:{ws.id}")
    return out(ws)


@router.get("/workspaces/{workspace_id}/events")
async def events(
    workspace_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> StreamingResponse:
    """Server-sent events: the workspace each time it changes, until setup is over."""
    await _mine(db, user, workspace_id)
    factory = request.app.state.db

    async def stream() -> Any:
        last = ""
        for _ in range(int(STREAM_SECONDS / STREAM_EVERY)):
            if await request.is_disconnected():
                return
            async with factory() as fresh:
                ws = await fresh.get(Workspace, workspace_id)
                if ws is None:
                    return
                data = out(ws).model_dump_json()
                status = ws.status
            if data != last:
                yield f"event: workspace\ndata: {data}\n\n"
                last = data
            if status not in (ws_flow.QUEUED, ws_flow.WORKING):
                return
            await asyncio.sleep(STREAM_EVERY)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------- changes and PR


def _head(ws: Workspace) -> str:
    return f"{(ws.fork_full_name or '').split('/')[0]}:{ws.branch}"


async def _adopt_open_pull(ws: Workspace, gh: UserGitHub) -> None:
    """A pull request opened on GitHub's own form counts as opened here too."""
    if ws.pr_url or not ws.fork_full_name or not ws.branch:
        return
    pull = await gh.open_pull(ws.repo_full_name, _head(ws))
    if pull:
        ws_flow.record_pull(ws, pull)


def _need_branch(ws: Workspace) -> None:
    if not ws.fork_full_name or not ws.branch or not ws.base_sha:
        raise HTTPException(409, "The workspace is not set up yet.")


@router.get("/workspaces/{workspace_id}/changes", response_model=Changes)
async def changes(
    workspace_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Changes:
    """What the user pushed to their branch: the "I finished" check."""
    ws = await _mine(db, user, workspace_id)
    _need_branch(ws)
    async with await _github(request, db, user) as gh:
        try:
            diff = await gh.compare(ws.fork_full_name or "", ws.base_sha or "", ws.branch or "")
            await _adopt_open_pull(ws, gh)
        except GitHubError as error:
            raise HTTPException(502, f"GitHub said no: {error.message}") from None
    await db.commit()
    web = request.app.state.settings.github_web_url.rstrip("/")
    return Changes(
        ahead_by=diff.ahead_by,
        commits=[
            Commit(
                sha=str(c.get("sha", ""))[:7],
                message=str(c.get("commit", {}).get("message", "")).split("\n")[0],
            )
            for c in diff.commits
        ],
        files=[
            ChangedFile(
                filename=str(f.get("filename")),
                status=str(f.get("status")),
                additions=int(f.get("additions") or 0),
                deletions=int(f.get("deletions") or 0),
            )
            for f in diff.files
        ],
        compare_url=f"{web}/{ws.fork_full_name}/compare/{ws.base_sha}...{ws.branch}",
        pull_request=out(ws).pull_request,
    )


def _default_body(ws: Workspace, template: str | None) -> str:
    rest = template or "## What I changed\n\n\n## How I tested it\n\n"
    return f"Fixes #{ws.number}\n\n{rest.strip()}\n"


@router.get("/workspaces/{workspace_id}/pull-request/draft", response_model=Draft)
async def draft(
    workspace_id: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Draft:
    ws = await _mine(db, user, workspace_id)
    _need_branch(ws)
    async with await _github(request, db, user) as gh:
        try:
            template = await gh.pr_template(ws.repo_full_name)
        except httpx.HTTPError:
            template = None
    return Draft(
        title=ws.issue_title,
        body=_default_body(ws, template),
        base=ws.base_branch or "main",
        head=_head(ws),
        from_template=template is not None,
    )


def _manual_url(settings: Settings, ws: Workspace, body: PullIn) -> str:
    base = settings.github_web_url.rstrip("/")
    query = urlencode({"expand": "1", "title": body.title, "body": body.body})
    return f"{base}/{ws.repo_full_name}/compare/{ws.base_branch}...{_head(ws)}?{query}"


@router.post(
    "/workspaces/{workspace_id}/pull-request",
    response_model=PullResult,
    dependencies=[Depends(require_csrf)],
)
async def create_pull_request(
    workspace_id: int,
    body: PullIn,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    jobs: Jobs = Depends(get_jobs),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> PullResult:
    """Open the pull request. Only ever sent by the user's own click."""
    ws = await _mine(db, user, workspace_id)
    _need_branch(ws)
    if ws.pr_url:
        return PullResult(opened=True, manual_url=None, workspace=out(ws))
    if settings.practice_repo and not ws.practice and not await ws_flow.practice_done(db, user.id):
        raise _problem(
            409,
            "practice_first",
            f"Open your practice pull request on {settings.practice_repo} first. It takes a "
            "few minutes and shows you the whole flow without bothering real maintainers.",
            practice_repo=settings.practice_repo,
        )
    if await ws_flow.open_prs(db, user.id) >= settings.max_open_prs:
        raise _problem(
            409,
            "too_many_open",
            f"You already have {settings.max_open_prs} pull requests waiting for review. "
            "Finish one of those before opening another.",
        )
    async with await _github(request, db, user) as gh:
        try:
            diff = await gh.compare(ws.fork_full_name or "", ws.base_sha or "", ws.branch or "")
            if diff.ahead_by == 0:
                raise _problem(409, "no_commits", f"Push at least one commit to {ws.branch} first.")
            await _adopt_open_pull(ws, gh)
            if ws.pr_url:
                await db.commit()
                return PullResult(opened=True, manual_url=None, workspace=out(ws))
            pull = await gh.create_pull(
                ws.repo_full_name,
                _head(ws),
                ws.base_branch or "main",
                body.title,
                body.body,
                body.draft,
            )
        except GitHubError as error:
            if error.status == 422 and "already exists" in error.message.lower():
                await _adopt_open_pull(ws, gh)
                await db.commit()
                return PullResult(opened=bool(ws.pr_url), manual_url=None, workspace=out(ws))
            # Usually: the app is not installed on the upstream repo, so GitHub does not
            # let it open pull requests there. GitHub's own form works for the user.
            return PullResult(
                opened=False, manual_url=_manual_url(settings, ws, body), workspace=out(ws)
            )
    ws_flow.record_pull(ws, pull)
    # Show it on My pull requests straight away, with its status.
    await jobs.enqueue_job(
        "track_pull",
        user.id,
        ws.repo_full_name,
        ws.pr_number,
        _job_id=f"track-pull:{user.id}:{ws.repo_full_name.lower()}#{ws.pr_number}",
    )
    card = await db.scalar(_card_query(ws.repo_full_name, ws.number))
    if card is not None:
        await picks.log(db, user.id, card, "issue", "pr_opened")
    await db.commit()
    return PullResult(opened=True, manual_url=None, workspace=out(ws))


@router.post(
    "/workspaces/{workspace_id}/close",
    response_model=WorkspaceOut,
    dependencies=[Depends(require_csrf)],
)
async def close(
    workspace_id: int,
    body: CloseIn,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> WorkspaceOut:
    """Stop working on this issue. The issue goes back to everyone."""
    ws = await _mine(db, user, workspace_id)
    if body.delete_codespace and ws.codespace_name:
        async with await _github(request, db, user) as gh:
            try:
                await gh.delete_codespace(ws.codespace_name)
            except GitHubError as error:
                if error.status != 404:
                    raise HTTPException(502, f"GitHub said no: {error.message}") from None
        ws.codespace_state = "Deleted"
    if not ws.pr_url:
        card = await db.scalar(_card_query(ws.repo_full_name, ws.number))
        if card is not None:
            await picks.release_work(db, user.id, card.id)
    ws.status = ws_flow.CLOSED
    await db.commit()
    return out(ws)


# ------------------------------------------------------ app installation


@router.get("/github/installed")
async def installed(state: str | None = None) -> RedirectResponse:
    """GitHub sends people here after they installed the app (the app's Setup URL)."""
    return RedirectResponse(safe_return(state), status_code=302)
