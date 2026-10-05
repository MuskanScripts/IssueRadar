"""Settings read from FIRSTPR_* environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIRSTPR_")

    database_url: str = "postgresql+psycopg://firstpr:firstpr@localhost:5432/firstpr"
    redis_url: str = "redis://localhost:6379/0"
    # The worker writes a heartbeat every minute; older than this means it stopped.
    worker_stale_after_seconds: int = 180
