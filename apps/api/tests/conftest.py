"""Shared test setup: SQLite instead of Postgres, fakeredis, and a fake GitHub."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import fakeredis
import httpx
import pytest
from fake_user_github import FakeUserGitHub
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession

from firstpr_api.main import create_app
from firstpr_api.settings import Settings
from firstpr_platform.crypto import TokenBox
from firstpr_platform.db import Base, CatalogueRepo, IssueCard


class FakeGitHub:
    """Just enough of github.com and api.github.com for sign-in."""

    def __init__(self) -> None:
        self.valid_tokens: set[str] = set()
        self.refresh_works = True
        self.issued = 0
        self.requests: list[httpx.Request] = []
        self.user = {"id": 4242, "login": "MuskanScripts", "name": "Muskan", "email": None}
        self.repos = {
            "pallets/flask": {"full_name": "pallets/flask", "private": False},
            "vitejs/vite": {"full_name": "vitejs/vite", "private": False},
            "muskanscripts/notes": {"full_name": "MuskanScripts/notes", "private": True},
        }
        # "owner/name#number" -> the issue as GitHub returns it.
        self.issues: dict[str, dict[str, Any]] = {}
        # Forks, branches, Codespaces and pull requests for workspaces.
        self.work = FakeUserGitHub()

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
        path = request.url.path
        if (
            path.startswith(("/user/installations", "/user/codespaces"))
            or path.removeprefix("/repos/").lower() in self.work.repos
            or (path.startswith("/repos/") and "/issues/" not in path and path.count("/") > 3)
        ):
            return self.work.handler(request)
        if "/issues/" in url and url.startswith("https://api.github.com/repos/"):
            repo, number = url.removeprefix("https://api.github.com/repos/").split("/issues/")
            issue = self.issues.get(f"{repo.lower()}#{number}")
            if issue is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json=issue)
        if url.startswith("https://api.github.com/repos/"):
            name = url.removeprefix("https://api.github.com/repos/")
            repo = self.repos.get(name.lower())
            if repo is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json=repo)
        if url == "https://api.github.com/user/emails":
            return httpx.Response(
                200, json=[{"email": "muskan@example.com", "primary": True, "verified": True}]
            )
        return httpx.Response(404, json={"message": "Not Found"})


class FakeJobs:
    """Records what the API puts on the worker's queue."""

    def __init__(self) -> None:
        self.queued: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> None:
        self.queued.append((function, args, kwargs))

    async def aclose(self) -> None:
        pass


@pytest.fixture
def jobs() -> FakeJobs:
    return FakeJobs()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        github_client_id="Iv1.test",
        github_client_secret="test-secret",
        token_keys=TokenBox.new_key(),
        cookie_secure=False,
        public_url="http://testserver",
        github_verify_every_seconds=300,
        github_webhook_secret="webhook-test-secret",
        max_watches_per_user=3,
        github_app_slug="firstpr-dev",
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
def client(
    settings: Settings, sync_db: OrmSession, github: FakeGitHub, jobs: FakeJobs
) -> Iterator[TestClient]:
    app = create_app(
        settings,
        redis=fakeredis.FakeAsyncRedis(),
        github_transport=httpx.MockTransport(github.handler),
        jobs=jobs,
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


def add_card(
    db: OrmSession, repo: str = "pallets/flask", number: int = 1, **values: Any
) -> IssueCard:
    """An issue card as the worker would write it, plus its repo in the catalogue."""
    now = datetime.now(UTC)
    if db.get(CatalogueRepo, repo) is None:
        db.add(CatalogueRepo(full_name=repo, source="pack"))
    card = IssueCard(
        repo_full_name=repo,
        number=number,
        title=values.pop("title", f"Issue {number} in {repo}"),
        url=f"https://github.com/{repo}/issues/{number}",
        labels=values.pop("labels", ["good first issue"]),
        repo_description="A repo",
        language=values.pop("language", "Python"),
        languages=values.pop("languages", ["python"]),
        frameworks=values.pop("frameworks", []),
        domains=values.pop("domains", []),
        paths=[],
        stars=100,
        comments=values.pop("comments", 0),
        opened_at=now - timedelta(days=10),
        updated_at=values.pop("updated_at", now - timedelta(days=1)),
        availability=values.pop("availability", "free"),
        availability_reasons=["Free: no assignee and no linked pull request"],
        tier=values.pop("tier", "beginner"),
        difficulty_score=20,
        time_bucket="half_a_day",
        issue_type="bug",
        difficulty_reasons=["Labelled good first issue"],
        discussion_first=False,
        health=values.pop("health", 80),
        health_reasons=["Maintainers reply within a week"],
        checklist=["Read the CONTRIBUTING guide before writing code."],
        repo_notes=None,
        changed_at=values.pop("changed_at", now),
        refreshed_at=values.pop("refreshed_at", now),
        **values,
    )
    db.add(card)
    db.commit()
    return card


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("firstpr_csrf") or ""}
