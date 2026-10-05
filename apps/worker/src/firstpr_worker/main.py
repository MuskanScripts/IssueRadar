"""The worker. Run with `arq firstpr_worker.main.WorkerSettings`.

For now it only writes a heartbeat every minute, which the API's health
check reads. The sync, scoring and XP jobs come in later steps.
"""

from __future__ import annotations

import os
import time
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

# Must match HEARTBEAT_KEY in apps/api.
HEARTBEAT_KEY = "firstpr:worker:heartbeat"
HEARTBEAT_TTL_SECONDS = 3600


async def heartbeat(ctx: dict[str, Any]) -> float:
    now = time.time()
    await ctx["redis"].set(HEARTBEAT_KEY, str(now), ex=HEARTBEAT_TTL_SECONDS)
    return now


async def startup(ctx: dict[str, Any]) -> None:
    await heartbeat(ctx)


class WorkerSettings:
    functions: ClassVar = [heartbeat]
    cron_jobs: ClassVar = [cron(heartbeat, second=0, run_at_startup=False)]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("FIRSTPR_REDIS_URL", "redis://localhost:6379/0")
    )
