"""`GET /api/v1/health`: is the API able to reach what it needs?

The database and Redis are required: without them the API answers 503. The
worker is reported but not required, so a stopped worker shows up without
taking the site down.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from firstpr_api import __version__

Check = Callable[[], Awaitable[str]]

# Must match HEARTBEAT_KEY in apps/worker.
HEARTBEAT_KEY = "firstpr:worker:heartbeat"
REQUIRED = ("database", "redis")
TIMEOUT_SECONDS = 2.0

router = APIRouter()


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    checks: dict[str, str]


def default_checks(engine: AsyncEngine, redis: Redis, stale_after: int) -> dict[str, Check]:
    async def database() -> str:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"

    async def redis_ping() -> str:
        await redis.ping()
        return "ok"

    async def worker() -> str:
        raw = await redis.get(HEARTBEAT_KEY)
        if raw is None:
            return "missing"
        return "ok" if time.time() - float(raw) <= stale_after else "stale"

    return {"database": database, "redis": redis_ping, "worker": worker}


async def run_check(check: Check) -> str:
    try:
        return await asyncio.wait_for(check(), timeout=TIMEOUT_SECONDS)
    except TimeoutError:
        return "error: timed out"
    except Exception as exc:
        # The type only: connection strings and hosts stay out of a public endpoint.
        return f"error: {type(exc).__name__}"


@router.get("/health", response_model=Health)
async def health(request: Request, response: Response) -> Health:
    checks: dict[str, Check] = request.app.state.checks
    names = list(checks)
    results = dict(
        zip(names, await asyncio.gather(*(run_check(checks[n]) for n in names)), strict=True)
    )
    ok = all(results.get(name) == "ok" for name in REQUIRED)
    if not ok:
        response.status_code = 503
    return Health(status="ok" if ok else "degraded", version=__version__, checks=results)
