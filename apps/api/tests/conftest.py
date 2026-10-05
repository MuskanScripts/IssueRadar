"""Shared test setup: SQLite instead of Postgres, fakeredis, and a fake GitHub."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import fakeredis
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession

from firstpr_api.crypto import TokenBox
from firstpr_api.db import Base
from firstpr_api.main import create_app
from firstpr_api.settings import Settings


class FakeGitHub:
    """Just enough of github.com and api.github.com for sign-in."""

    def __init__(self) -> None:
        self.valid_tokens: set[str] = set()
        self.refresh_works = True
        self.issued = 0
        self.requests: list[httpx.Request] = []
        self.user = {"id": 4242, "login": "MuskanScripts", "name": "Muskan", "email": None}

    def _tokens(self) -> dict[str, Any]:
        self.issued += 1
        token = f"ghu_test_{self.issued}"
        self.valid_tokens.add(token)
        return {
            "access_token": token,
            "expires_in": 28800,
            "refresh_token": f"ghr_test_{self.issued}",
            "refresh_token_expires_in": 15897600,
            "token_type": "bearer",
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url == "https://github.com/login/oauth/access_token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            if form.get("grant_type") == "refresh_token":
                if self.refresh_works and form.get("refresh_token", "").startswith("ghr_test_"):
                    return httpx.Response(200, json=self._tokens())
                return httpx.Response(200, json={"error": "bad_refresh_token"})
            if form.get("code") == "good-code" and form.get("code_verifier"):
                return httpx.Response(200, json=self._tokens())
            return httpx.Response(200, json={"error": "bad_verification_code"})
        auth = request.headers.get("authorization", "").removeprefix("Bearer ")
        if auth not in self.valid_tokens:
            return httpx.Response(401, json={"message": "Bad credentials"})
        if url == "https://api.github.com/user":
            return httpx.Response(
                200, json={**self.user, "avatar_url": "https://example.com/a.png"}
            )
        if url == "https://api.github.com/user/emails":
            return httpx.Response(
                200, json=[{"email": "muskan@example.com", "primary": True, "verified": True}]
            )
        return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        github_client_id="Iv1.test",
        github_client_secret="test-secret",  # noqa: S106 - test value
        token_keys=TokenBox.new_key(),
        cookie_secure=False,
        public_url="http://testserver",
        github_verify_every_seconds=300,
    )


@pytest.fixture
def sync_db(settings: Settings) -> Iterator[OrmSession]:
    engine = create_engine(settings.database_url.replace("+aiosqlite", ""))
    Base.metadata.create_all(engine)
    with OrmSession(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def client(settings: Settings, sync_db: OrmSession, github: FakeGitHub) -> Iterator[TestClient]:
    app = create_app(
        settings,
        redis=fakeredis.FakeAsyncRedis(),
        github_transport=httpx.MockTransport(github.handler),
    )
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


def sign_in(client: TestClient, return_to: str | None = None) -> httpx.Response:
    """Run the whole flow: /login, then GitHub sends the browser to /callback."""
    params = {"return_to": return_to} if return_to else {}
    login = client.get("/api/v1/auth/github/login", params=params, follow_redirects=False)
    assert login.status_code == 302, login.text
    state = parse_qs(httpx.URL(login.headers["location"]).query.decode())["state"][0]
    return client.get(
        "/api/v1/auth/github/callback",
        params={"code": "good-code", "state": state},
        follow_redirects=False,
    )


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("firstpr_csrf") or ""}
