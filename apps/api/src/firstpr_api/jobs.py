"""Putting jobs on the worker's queue (arq on Redis)."""

from __future__ import annotations

from typing import Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings


class ArqJobs:
    """Connects on first use, so the API starts even if Redis is slow to come up."""

    def __init__(self, redis_url: str) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> Any:
        if self._pool is None:
            self._pool = await create_pool(self._settings)
        return await self._pool.enqueue_job(function, *args, **kwargs)

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
