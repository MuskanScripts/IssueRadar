"""Running the site: security headers, error counts, metrics for alerts, reports
of errors from the browser, and deleting an account.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta

import sentry_sdk
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api import sessions
from firstpr_api.deps import (
    Jobs,
    current_user,
    get_db,
    get_jobs,
    get_redis,
    get_settings,
    require_csrf,
)
from firstpr_api.settings import Settings
from firstpr_platform.db import Base, Session, User, Workspace, utcnow

log = logging.getLogger("firstpr.api")
router = APIRouter()

ERROR_PREFIX = "firstpr:errors:"
REQUEST_PREFIX = "firstpr:requests:"
# Must match BUDGET_PREFIX in the worker.
BUDGET_PREFIX = "firstpr:budget:"
CLIENT_ERROR_PREFIX = "firstpr:ratelimit:client-error:"

# The JSON API never needs to be framed or to run scripts.
API_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def _minute() -> int:
    return int(time.time() // 60)


async def security_and_counts(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware: security headers on every answer, and a per-minute count of
    requests and server errors for /metrics."""
    try:
        response = await call_next(request)
    except Exception:
        await _count(request, 500)
        raise
    for name, value in API_HEADERS.items():
        response.headers.setdefault(name, value)
    if request.url.path.startswith("/api/docs"):
        # The docs page loads its scripts from a CDN.
        del response.headers["Content-Security-Policy"]
    await _count(request, response.status_code)
    return response


async def _count(request: Request, status: int) -> None:
    redis: Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        return
    minute = _minute()
    try:
        await redis.incr(f"{REQUEST_PREFIX}{minute}")
        await redis.expire(f"{REQUEST_PREFIX}{minute}", 3600)
        if status >= 500:
            await redis.incr(f"{ERROR_PREFIX}{minute}")
            await redis.expire(f"{ERROR_PREFIX}{minute}", 3600)
    except Exception:
        log.debug("could not count the request")


# ----------------------------------------------------------- delete account


class DeleteIn(BaseModel):
    # Typing the GitHub login confirms it, so a stray click cannot delete an account.
    confirm: str = Field(min_length=1, max_length=100)


@router.delete("/me", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_account(
    body: DeleteIn,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
    jobs: Jobs = Depends(get_jobs),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> Response:
    """Delete my data: the account and everything stored about it, at once.

    Fork, branches, Codespaces and pull requests on GitHub are the user's own and
    stay there. Revoking the app on github.com is up to them (the page says how).
    """
    if body.confirm.strip().lower() != user.handle.lower():
        raise HTTPException(422, "Type your GitHub login to confirm.")
    user_id = user.id
    hashes = list(await db.scalars(select(Session.id_hash).where(Session.user_id == user_id)))
    # Every table with a user_id, children first, so it works with or without
    # ON DELETE CASCADE.
    for table in reversed(Base.metadata.sorted_tables):
        if "user_id" in table.c and table.name != "users":
            await db.execute(delete(table).where(table.c.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    for key_hash in hashes:
        await redis.delete(sessions.CACHE_PREFIX + key_hash)
    async for key in redis.scan_iter(match=f"firstpr:*:{user_id}*"):
        await redis.delete(key)
    await jobs.enqueue_job("forget_user", user_id)
    log.info("account deleted: user %s", user_id)
    response = Response(status_code=204)
    sessions.clear_cookies(response, settings)
    return response


# ---------------------------------------------------------------- metrics


def _gauge(lines: list[str], name: str, help_text: str, value: float, **labels: str) -> None:
    if not any(line.startswith(f"# HELP {name} ") for line in lines):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
    tags = ",".join(f'{k}="{v}"' for k, v in labels.items())
    lines.append(f"{name}{{{tags}}} {value}" if tags else f"{name} {value}")


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> PlainTextResponse:
    """Prometheus metrics for alerts: GitHub budget left, job queue age, error
    rate, workspace failures, and whether the database and worker are up."""
    token = settings.metrics_token.get_secret_value()
    given = request.headers.get("authorization", "").removeprefix("Bearer ")
    if not token or not secrets.compare_digest(token, given):
        raise HTTPException(404, "Not Found")  # looks like nothing is here
    lines: list[str] = []
    now = _minute()
    window = [now - i for i in range(1, 6)]  # the last 5 whole minutes
    requests_5m = errors_5m = 0
    for m in window:
        requests_5m += int(await redis.get(f"{REQUEST_PREFIX}{m}") or 0)
        errors_5m += int(await redis.get(f"{ERROR_PREFIX}{m}") or 0)
    _gauge(lines, "firstpr_requests_5m", "API requests in the last 5 minutes", requests_5m)
    _gauge(
        lines, "firstpr_errors_5m", "API answers with status 5xx in the last 5 minutes", errors_5m
    )
    _gauge(
        lines,
        "firstpr_error_ratio_5m",
        "Share of API answers that were 5xx in the last 5 minutes",
        round(errors_5m / requests_5m, 4) if requests_5m else 0.0,
    )
    async for key in redis.scan_iter(match=f"{BUDGET_PREFIX}*"):
        name = key.decode() if isinstance(key, bytes) else str(key)
        raw = await redis.get(name)
        data = json.loads(raw) if raw else {}
        if data.get("limit"):
            _gauge(
                lines,
                "firstpr_github_budget_left_ratio",
                "Share of a GitHub token's hourly limit left at its last sync",
                round((data.get("remaining") or 0) / data["limit"], 4),
                token=name.removeprefix(BUDGET_PREFIX).split(":")[0],
            )
    oldest = await redis.zrange("arq:queue", 0, 0, withscores=True)
    age = max(0.0, time.time() - oldest[0][1] / 1000) if oldest else 0.0
    _gauge(
        lines,
        "firstpr_queue_oldest_job_seconds",
        "How long the oldest queued job has waited",
        round(age, 1),
    )
    day_ago = utcnow() - timedelta(hours=24)
    failed = await db.scalar(
        select(func.count(Workspace.id)).where(
            Workspace.status == "failed", Workspace.updated_at >= day_ago
        )
    )
    _gauge(
        lines,
        "firstpr_workspace_failures_24h",
        "Workspaces whose setup stopped in the last 24 hours",
        failed or 0,
    )
    beat = await redis.get("firstpr:worker:heartbeat")
    _gauge(
        lines,
        "firstpr_worker_heartbeat_age_seconds",
        "Seconds since the worker's last heartbeat",
        round(time.time() - float(beat), 1) if beat else 1e9,
    )
    users = await db.scalar(select(func.count(User.id)))
    _gauge(lines, "firstpr_users", "Signed-up users", users or 0, environment=settings.environment)
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


# ------------------------------------------------------- browser errors


class ClientError(BaseModel):
    message: str = Field(max_length=500)
    path: str = Field(max_length=300)
    digest: str | None = Field(default=None, max_length=100)


@router.post("/client-errors", status_code=204)
async def client_error(
    body: ClientError,
    request: Request,
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> None:
    """Errors from the web page, passed on to Sentry (or the log). Limited per IP."""
    ip = request.client.host if request.client else "unknown"
    key = f"{CLIENT_ERROR_PREFIX}{ip}:{_minute()}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 120)
    if count > 10:
        return
    log.warning("browser error on %s: %s", body.path, body.message)
    sentry_sdk.capture_message(f"Browser error on {body.path}: {body.message}", level="error")
