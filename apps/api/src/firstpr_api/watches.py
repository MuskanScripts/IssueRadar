"""The repos a signed-in user watches."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api.deps import Jobs, current_user, get_db, get_jobs, get_settings, require_csrf
from firstpr_api.settings import Settings
from firstpr_platform import accounts, plan
from firstpr_platform.db import RepoSync, User, Watch
from firstpr_platform.github_oauth import GitHubAuthError

router = APIRouter()


class LastSync(BaseModel):
    status: str
    synced_at: datetime
    open_issues: int


class WatchOut(BaseModel):
    full_name: str
    added_at: datetime
    synced_with: Literal["app", "you"]
    last_sync: LastSync | None


class WatchIn(BaseModel):
    repo: str


async def _list(db: AsyncSession, user: User) -> list[WatchOut]:
    sync_plan = await plan.build(db)
    rows = await db.scalars(select(Watch).where(Watch.user_id == user.id).order_by(Watch.id))
    out = []
    for watch in rows:
        last = await db.get(RepoSync, watch.repo_full_name)
        out.append(
            WatchOut(
                full_name=watch.repo_full_name,
                added_at=watch.created_at,
                synced_with="app"
                if sync_plan.token_kind(watch.repo_full_name) == plan.APP
                else "you",
                last_sync=LastSync(
                    status=last.status, synced_at=last.synced_at, open_issues=last.open_issues
                )
                if last
                else None,
            )
        )
    return out


@router.get("/me/watches", response_model=list[WatchOut])
async def list_watches(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[WatchOut]:
    return await _list(db, user)


@router.post(
    "/me/watches",
    response_model=list[WatchOut],
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def add_watch(
    body: WatchIn,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    jobs: Jobs = Depends(get_jobs),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> list[WatchOut]:
    name = plan.normalise_repo(body.repo)
    if name is None:
        raise HTTPException(422, "Use owner/name or a github.com link, for example pallets/flask.")
    count = await db.scalar(select(func.count(Watch.id)).where(Watch.user_id == user.id))
    if (count or 0) >= settings.max_watches_per_user:
        raise HTTPException(409, f"You can watch up to {settings.max_watches_per_user} repos.")
    oauth, box = request.app.state.oauth, request.app.state.token_box
    if oauth is None or box is None:
        raise HTTPException(503, "Sign-in is not set up on this server")
    token = await accounts.usable_token(db, user.github, box, oauth)
    if token is None:
        raise HTTPException(409, "Reconnect your GitHub account first.")
    try:
        repo = await oauth.get_repo(token, name)
    except GitHubAuthError:
        await accounts.mark_reconnect(db, user.github)
        raise HTTPException(409, "Reconnect your GitHub account first.") from None
    except httpx.HTTPError:
        raise HTTPException(502, "GitHub did not answer. Try again in a minute.") from None
    if repo is None:
        raise HTTPException(404, f"{name} does not exist, or GitHub does not show it to you.")
    if repo.get("private"):
        raise HTTPException(422, "Private repos are not supported. FirstPR is for open source.")
    full_name = str(repo["full_name"])
    exists = await db.scalar(
        select(Watch).where(
            Watch.user_id == user.id, func.lower(Watch.repo_full_name) == full_name.lower()
        )
    )
    if exists is None:
        db.add(Watch(user_id=user.id, repo_full_name=full_name))
        await db.commit()
        # Sync it soon instead of waiting up to 30 minutes for the next run.
        await jobs.enqueue_job("sync_user", user.id, _job_id=f"sync-user:{user.id}", _defer_by=5)
    return await _list(db, user)


@router.delete(
    "/me/watches/{owner}/{name}",
    response_model=list[WatchOut],
    dependencies=[Depends(require_csrf)],
)
async def remove_watch(
    owner: str,
    name: str,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[WatchOut]:
    await db.execute(
        delete(Watch).where(
            Watch.user_id == user.id, func.lower(Watch.repo_full_name) == f"{owner}/{name}".lower()
        )
    )
    await db.commit()
    return await _list(db, user)
