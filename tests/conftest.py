from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

from issueradar.brand import BRAND
from issueradar.config import Settings, load_settings
from issueradar.storage import Database, open_database

sys.path.insert(0, str(Path(__file__).parent))  # lets tests import fake_github

pytest_plugins = ["scenario"]  # the `synced` fixture


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may reach GitHub or the user's real database."""
    monkeypatch.setenv(BRAND.env("DB_URL"), f"sqlite:///{(tmp_path / 'cli.sqlite').as_posix()}")
    monkeypatch.delenv(BRAND.env("GITHUB_TOKEN"), raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    async def no_network(self: object, request: httpx.Request) -> httpx.Response:
        raise RuntimeError(f"Tests must not touch the network: {request.method} {request.url}")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)


@pytest.fixture
def settings() -> Settings:
    return load_settings()


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return open_database(f"sqlite:///{(tmp_path / 'test.sqlite').as_posix()}")


class FakeSleep:
    """Records waits instead of sleeping."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


@pytest.fixture
def fake_sleep() -> FakeSleep:
    return FakeSleep()
