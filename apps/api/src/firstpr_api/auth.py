"""Sign in with GitHub, sign out, and who is signed in."""

from __future__ import annotations

import json
import secrets
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api import accounts, sessions
from firstpr_api.crypto import TokenBox
from firstpr_api.db import User
from firstpr_api.deps import current_user, get_db, get_redis, get_settings, require_csrf
from firstpr_api.github_oauth import GitHubAuthError, GitHubOAuth, pkce_pair
from firstpr_api.settings import Settings

STATE_COOKIE = "firstpr_oauth"
STATE_PREFIX = "firstpr:oauth:"
STATE_SECONDS = 600
LOGIN_LIMIT_PREFIX = "firstpr:ratelimit:login:"
DEFAULT_RETURN = "/home"

router = APIRouter()


def safe_return(path: str | None) -> str:
    """Only paths on this site, so the sign-in can't bounce people elsewhere."""
    if not path or not path.startswith("/") or path.startswith(("//", "/\\")):
        return DEFAULT_RETURN
    return path


def _oauth(request: Request) -> GitHubOAuth:
    oauth: GitHubOAuth | None = request.app.state.oauth
    if oauth is None:
        raise HTTPException(status_code=503, detail="Sign-in is not set up on this server")
    return oauth


def _box(request: Request) -> TokenBox:
    box: TokenBox | None = request.app.state.token_box
    if box is None:
        raise HTTPException(status_code=503, detail="Sign-in is not set up on this server")
    return box


@router.get("/auth/github/login")
async def login(
    request: Request,
    return_to: str | None = None,
    redis: Redis = Depends(get_redis),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> RedirectResponse:
    oauth = _oauth(request)
    ip = request.client.host if request.client else "unknown"
    attempts = await redis.incr(LOGIN_LIMIT_PREFIX + ip)
    if attempts == 1:
        await redis.expire(LOGIN_LIMIT_PREFIX + ip, 600)
    if attempts > settings.login_attempts_per_10_minutes:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later.")

    state = secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    await redis.set(
        STATE_PREFIX + state,
        json.dumps({"verifier": verifier, "return_to": safe_return(return_to)}),
        ex=STATE_SECONDS,
    )
    resp = RedirectResponse(oauth.authorize_url(state, challenge), status_code=302)
    resp.set_cookie(
        STATE_COOKIE,
        state,
        max_age=STATE_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )
    return resp


@router.get("/auth/github/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> RedirectResponse:
    oauth, box = _oauth(request), _box(request)

    def back(reason: str) -> RedirectResponse:
        resp = RedirectResponse(f"/?signin={reason}", status_code=302)
        resp.delete_cookie(STATE_COOKIE, path="/api/v1/auth")
        return resp

    if error:
        return back("cancelled")
    # The state must match the cookie set on this browser, and is single-use.
    cookie_state = request.cookies.get(STATE_COOKIE, "")
    if not code or not state or not secrets.compare_digest(cookie_state, state):
        return back("expired")
    saved = await redis.getdel(STATE_PREFIX + state)
    if saved is None:
        return back("expired")
    pending = json.loads(saved)

    try:
        tokens = await oauth.exchange(code, pending["verifier"])
        gh = await oauth.get_user(tokens.access_token)
    except (GitHubAuthError, httpx.HTTPError):
        return back("failed")

    user = await accounts.upsert(db, gh, tokens, box)
    # A new session on every sign-in; an old cookie on this browser is dropped.
    await sessions.revoke(db, redis, request.cookies.get(sessions.SESSION_COOKIE))
    raw = await sessions.create(db, redis, user.id, settings, request.headers.get("user-agent"))
    resp = RedirectResponse(safe_return(pending.get("return_to")), status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/api/v1/auth")
    sessions.set_cookies(resp, raw, settings)
    return resp


@router.post("/auth/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> Response:
    await sessions.revoke(db, redis, request.cookies.get(sessions.SESSION_COOKIE))
    resp = Response(status_code=204)
    sessions.clear_cookies(resp, settings)
    return resp


class GitHubStatus(BaseModel):
    login: str
    status: Literal["connected", "reconnect_needed"]


class Me(BaseModel):
    id: int
    handle: str
    name: str | None
    email: str | None
    avatar_url: str | None
    github: GitHubStatus


@router.get("/me", response_model=Me)
async def me(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> Me:
    oauth: GitHubOAuth | None = request.app.state.oauth
    box: TokenBox | None = request.app.state.token_box
    # `user` was loaded with this request's `db` (FastAPI shares the dependency).
    account = user.github
    if oauth is not None and box is not None:
        await accounts.verify(db, account, box, oauth, settings.github_verify_every_seconds)
    status: Literal["connected", "reconnect_needed"] = (
        "connected" if account.status == accounts.CONNECTED else "reconnect_needed"
    )
    return Me(
        id=user.id,
        handle=user.handle,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        github=GitHubStatus(login=account.login, status=status),
    )
