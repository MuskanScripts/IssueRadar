"""The worker. Run with `arq firstpr_worker.main.WorkerSettings`.

Every minute it writes a heartbeat the API's health check reads. Every 30
minutes it syncs the shared catalogue with the app's token, and 15 minutes
later it queues a personal sync for each active user with repos of their own.
After each sync it rebuilds the issue cards the API reads, and every 15
minutes it holds a daily pick for active users whose local day has none yet.
Workspaces are set up when a user clicks Start working, and every 5 minutes
their Codespaces and pull requests are checked (reads only).
Webhooks from GitHub are handled as they arrive.
"""

from __future__ import annotations

import os
import time
from typing import Any, ClassVar

from arq import cron, func
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import create_async_engine

from firstpr_platform.crypto import TokenBox
from firstpr_platform.db import session_factory
from firstpr_platform.github_app import AppTokenSource
from firstpr_platform.github_oauth import GitHubOAuth
from firstpr_worker.catalogue import Catalogue
from firstpr_worker.jobs import (
    cards_if_empty,
    check_workspaces,
    handle_webhook,
    make_daily_picks,
    poll_workspace,
    refresh_cards,
    seed_catalogue,
    start_workspace,
    sync_active_users,
    sync_catalogue,
    sync_user,
)
from firstpr_worker.settings import Settings

# Must match HEARTBEAT_KEY in apps/api.
HEARTBEAT_KEY = "firstpr:worker:heartbeat"
HEARTBEAT_TTL_SECONDS = 3600


async def heartbeat(ctx: dict[str, Any]) -> float:
    now = time.time()
    await ctx["redis"].set(HEARTBEAT_KEY, str(now), ex=HEARTBEAT_TTL_SECONDS)
    return now


async def startup(ctx: dict[str, Any]) -> None:
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["db"] = session_factory(engine)
    ctx["catalogue"] = Catalogue(settings.catalogue_database_url, settings.budget_pause_share)
    ctx["app_tokens"] = None
    if settings.app_configured:
        ctx["app_tokens"] = AppTokenSource(
            settings.github_app_id,
            # .env files carry the key on one line with \n for each line break.
            settings.github_app_private_key.get_secret_value().replace("\\n", "\n"),
            settings.github_installation_id,
        )
    ctx["box"] = ctx["oauth"] = None
    if settings.users_configured:
        ctx["box"] = TokenBox(settings.token_keys.get_secret_value())
        ctx["oauth"] = GitHubOAuth(
            settings.github_client_id,
            settings.github_client_secret.get_secret_value(),
            redirect_uri="",  # only used for refreshing tokens here
        )
    await heartbeat(ctx)
    await seed_catalogue(ctx)
    await cards_if_empty(ctx)


async def shutdown(ctx: dict[str, Any]) -> None:
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


# keep_result=0 frees a job's id as soon as it finishes, so the API and webhooks
# can queue the same sync again ("sync this soon") without waiting a day.
_SYNC = {"keep_result": 0, "max_tries": 3, "timeout": 30 * 60}


class WorkerSettings:
    functions: ClassVar = [
        heartbeat,
        func(sync_catalogue, **_SYNC),  # type: ignore[arg-type]
        func(sync_user, **_SYNC),  # type: ignore[arg-type]
        func(sync_active_users, keep_result=0),
        func(handle_webhook, keep_result=0, max_tries=5),
        func(refresh_cards, keep_result=0, timeout=30 * 60),
        func(make_daily_picks, keep_result=0),
        func(start_workspace, keep_result=0, max_tries=1, timeout=10 * 60),
        func(poll_workspace, keep_result=0, max_tries=1),
        func(check_workspaces, keep_result=0, timeout=10 * 60),
    ]
    cron_jobs: ClassVar = [
        cron(heartbeat, second=0, run_at_startup=False),
        cron(sync_catalogue, minute={0, 30}, second=10, unique=True, keep_result=0),
        cron(sync_active_users, minute={15, 45}, second=10, unique=True, keep_result=0),
        cron(make_daily_picks, minute={5, 20, 35, 50}, second=10, unique=True, keep_result=0),
        cron(check_workspaces, minute=set(range(2, 60, 5)), second=0, unique=True, keep_result=0),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("FIRSTPR_REDIS_URL", "redis://localhost:6379/0")
    )
