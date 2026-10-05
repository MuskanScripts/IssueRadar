"""The API app. Run with `uvicorn --factory firstpr_api.main:create_app`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from firstpr_api import __version__, health
from firstpr_api.settings import Settings


def create_app(
    settings: Settings | None = None, checks: dict[str, health.Check] | None = None
) -> FastAPI:
    """Build the app. Tests pass `checks` to run without Postgres or Redis."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if checks is not None:
            app.state.checks = checks
            yield
            return
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        redis = Redis.from_url(settings.redis_url)
        app.state.checks = health.default_checks(engine, redis, settings.worker_stale_after_seconds)
        try:
            yield
        finally:
            await redis.aclose()
            await engine.dispose()

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
    app.include_router(v1)
    return app
