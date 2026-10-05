"""`/api/v1/health` with fake checks, plus one run against real Postgres and Redis."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from firstpr_api import health
from firstpr_api.main import create_app
from firstpr_api.settings import Settings


def ok() -> health.Check:
    async def check() -> str:
        return "ok"

    return check


def fails(exc: Exception) -> health.Check:
    async def check() -> str:
        raise exc

    return check


def get(checks: dict[str, health.Check]) -> Any:
    with TestClient(create_app(checks=checks)) as client:
        return client.get("/api/v1/health")


def test_all_ok() -> None:
    resp = get({"database": ok(), "redis": ok(), "worker": ok()})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["checks"] == {"database": "ok", "redis": "ok", "worker": "ok"}


def test_database_down_is_503_without_leaking_details() -> None:
    secret = ConnectionError("could not connect to db.internal:5432 as user firstpr")
    resp = get({"database": fails(secret), "redis": ok(), "worker": ok()})
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"
    assert resp.json()["checks"]["database"] == "error: ConnectionError"
    assert "db.internal" not in resp.text


def test_slow_check_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "TIMEOUT_SECONDS", 0.05)

    async def slow() -> str:
        await asyncio.sleep(1)
        return "ok"

    resp = get({"database": ok(), "redis": slow, "worker": ok()})
    assert resp.status_code == 503
    assert resp.json()["checks"]["redis"] == "error: timed out"


def test_stopped_worker_is_reported_but_not_required() -> None:
    async def stale() -> str:
        return "stale"

    resp = get({"database": ok(), "redis": ok(), "worker": stale})
    assert resp.status_code == 200
    assert resp.json()["checks"]["worker"] == "stale"


class FakeRedis:
    def __init__(self, value: str | None) -> None:
        self.value = value

    async def get(self, key: str) -> str | None:
        assert key == health.HEARTBEAT_KEY
        return self.value

    async def ping(self) -> bool:
        return True


@pytest.mark.parametrize(
    ("heartbeat", "expected"),
    [(None, "missing"), (time.time() - 30, "ok"), (time.time() - 600, "stale")],
)
def test_worker_heartbeat_age(heartbeat: float | None, expected: str) -> None:
    redis = FakeRedis(None if heartbeat is None else str(heartbeat))
    checks = health.default_checks(engine=None, redis=redis, stale_after=180)  # type: ignore[arg-type]
    assert asyncio.run(checks["worker"]()) == expected


@pytest.mark.skipif(
    not os.environ.get("FIRSTPR_TEST_DATABASE_URL"),
    reason="set FIRSTPR_TEST_DATABASE_URL and FIRSTPR_TEST_REDIS_URL to run against real services",
)
def test_real_services() -> None:
    settings = Settings(
        database_url=os.environ["FIRSTPR_TEST_DATABASE_URL"],
        redis_url=os.environ["FIRSTPR_TEST_REDIS_URL"],
    )
    with TestClient(create_app(settings)) as client:
        resp = client.get("/api/v1/health")
    assert resp.status_code == 200, resp.text
    assert resp.json()["checks"]["database"] == "ok"
    assert resp.json()["checks"]["redis"] == "ok"
