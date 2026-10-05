"""The heartbeat job, with a fake Redis."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from firstpr_worker.main import HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS, WorkerSettings, heartbeat


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, int | None]] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = (value, ex)
        return True


def test_heartbeat_writes_the_time_with_an_expiry() -> None:
    redis = FakeRedis()
    ctx: dict[str, Any] = {"redis": redis}
    before = time.time()
    written = asyncio.run(heartbeat(ctx))
    value, ttl = redis.values[HEARTBEAT_KEY]
    assert before <= float(value) == written <= time.time()
    assert ttl == HEARTBEAT_TTL_SECONDS


def test_heartbeat_runs_every_minute() -> None:
    (job,) = WorkerSettings.cron_jobs
    assert job.coroutine is heartbeat
    assert job.second == 0 and job.minute is None
