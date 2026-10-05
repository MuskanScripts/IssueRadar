"""The API app. Run with `uvicorn --factory firstpr_api.main:create_app`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from firstpr_api import (
    __version__,
    admin,
    auth,
    health,
    issues,
    notifications,
    profile,
    progress,
    public,
    watches,
    webhooks,
    workspaces,
)
from firstpr_api.jobs import ArqJobs
from firstpr_api.settings import Settings
from firstpr_platform.analytics import Analytics
from firstpr_platform.crypto import TokenBox
from firstpr_platform.db import session_factory
from firstpr_platform.github_oauth import GitHubOAuth


def create_app(
    settings: Settings | None = None,
    *,
    checks: dict[str, health.Check] | None = None,
    engine: AsyncEngine | None = None,
    redis: Redis | None = None,
    github_transport: httpx.AsyncBaseTransport | None = None,
    jobs: Any = None,
) -> FastAPI:
    """Build the app. Tests pass their own engine, Redis, GitHub transport or checks."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        own_engine = engine is None
        own_redis = redis is None
        own_jobs = jobs is None
        db_engine = engine or create_async_engine(settings.database_url, pool_pre_ping=True)
        cache = redis or Redis.from_url(settings.redis_url)
        app.state.settings = settings
        app.state.db = session_factory(db_engine)
        app.state.redis = cache
        app.state.jobs = jobs or ArqJobs(settings.redis_url)
        app.state.checks = checks or health.default_checks(
            db_engine, cache, settings.worker_stale_after_seconds
        )
        app.state.github_transport = github_transport
        app.state.analytics = Analytics(settings.posthog_key, settings.posthog_host)
        app.state.token_box = None
        app.state.oauth = None
        if settings.sign_in_configured:
            app.state.token_box = TokenBox(settings.token_keys.get_secret_value())
            app.state.oauth = GitHubOAuth(
                settings.github_client_id,
                settings.github_client_secret.get_secret_value(),
                settings.callback_url,
                transport=github_transport,
                web_url=settings.github_web_url,
                api_url=settings.github_api_url,
            )
        try:
            yield
        finally:
            if own_jobs:
                await app.state.jobs.aclose()
            if own_redis:
                await cache.aclose()
            if own_engine:
                await db_engine.dispose()

    app = FastAPI(
        title="FirstPR API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(health.router)
    v1.include_router(auth.router)
    v1.include_router(watches.router)
    v1.include_router(profile.router)
    v1.include_router(issues.router)
    v1.include_router(workspaces.router)
    v1.include_router(notifications.router)
    v1.include_router(progress.router)
    v1.include_router(public.router)
    v1.include_router(admin.router)
    v1.include_router(webhooks.router)
    app.include_router(v1)
    return app
