"""Request dependencies: database session, Redis, the signed-in user, CSRF."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from typing import Any, Protocol

from fastapi import Depends, HTTPException, Request, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api import sessions
from firstpr_api.settings import Settings
from firstpr_platform.db import User


class Jobs(Protocol):
    """The worker's job queue (an arq pool). Jobs are named, so the API never
    imports worker code."""

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> Any: ...


def get_jobs(request: Request) -> Jobs:
    jobs: Jobs = request.app.state.jobs
    return jobs


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db() as db:
        yield db


async def current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> User:
    raw = request.cookies.get(sessions.SESSION_COOKIE)
    user, extended = await sessions.load(db, redis, raw, settings)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    if extended and raw:
        sessions.set_cookies(response, raw, settings)
    return user


def require_csrf(request: Request) -> None:
    """Double-submit check for every request that changes something."""
    cookie = request.cookies.get(sessions.CSRF_COOKIE, "")
    header = request.headers.get(sessions.CSRF_HEADER, "")
    if not cookie or not secrets.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="Missing or wrong CSRF token")


def require_admin(user: User = Depends(current_user)) -> User:  # noqa: B008
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return user
