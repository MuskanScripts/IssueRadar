"""Worker test setup: SQLite for the platform database, fakes for the rest."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session as OrmSession

from firstpr_platform.crypto import TokenBox
from firstpr_platform.db import Base, session_factory
from firstpr_worker.catalogue import Card, SyncResult
from firstpr_worker.settings import Settings
from issueradar.sync.service import RepoOutcome


def make_card(repo: str, number: int, **values: Any) -> Card:
    fields: dict[str, Any] = {
        "repo_full_name": repo,
        "number": number,
        "title": f"Issue {number}",
        "url": None,
        "labels": [],
        "repo_description": None,
        "language": "Python",
        "languages": ["python"],
        "frameworks": [],
        "domains": [],
        "paths": [],
        "stars": 1,
        "comments": 0,
        "opened_at": None,
        "updated_at": None,
        "availability": "free",
        "availability_reasons": [],
        "tier": "beginner",
        "difficulty_score": 10,
        "time_bucket": "under_an_hour",
        "issue_type": "docs",
        "difficulty_reasons": [],
        "discussion_first": False,
        "health": 70,
        "health_reasons": [],
    }
    return Card(**{**fields, **values})


class FakeCatalogue:
    """Stands in for the engine: records what it was asked to sync."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, set[str], str, str]] = []
        self.cleared: list[int] = []
        self.interrupt_after: int | None = None
        # What cards() returns for each repo; repos not listed have no open issues.
        self.issues: dict[str, list[Card]] = {}

    def cards(self, repos: set[str]) -> dict[str, list[Card]]:
        return {name: list(self.issues.get(name, [])) for name in repos}

    def clear_watchlist(self, owner: int) -> None:
        self.cleared.append(owner)

    async def sync(self, owner: int, repos: set[str], token: str, identity: str) -> SyncResult:
        self.calls.append((owner, set(repos), token, identity))
        names = sorted(repos, key=str.lower)
        if self.interrupt_after is not None:
            done = names[: self.interrupt_after]
            outcomes = [RepoOutcome(n, "synced", open_issues=3) for n in done]
            budget = {"limit": 5000, "remaining": 900, "paused": True}
            return SyncResult("interrupted", outcomes, "Rate limit nearly used up", budget)
        outcomes = [RepoOutcome(n, "synced", open_issues=3) for n in names]
        return SyncResult(
            "completed", outcomes, None, {"limit": 5000, "remaining": 4800, "paused": False}
        )


class FakeTokens:
    async def token(self) -> str:
        return "ghs_app_token"


class FakeQueue:
    """ctx["redis"]: a real fake Redis, plus a record of queued jobs."""

    def __init__(self) -> None:
        self.redis = fakeredis.FakeAsyncRedis()
        self.queued: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def set(self, *args: Any, **kwargs: Any) -> Any:
        return await self.redis.set(*args, **kwargs)

    async def get(self, key: str) -> Any:
        return await self.redis.get(key)

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> None:
        self.queued.append((function, args, kwargs))


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"


@pytest.fixture
def sync_db(db_url: str) -> Iterator[OrmSession]:
    engine = create_engine(db_url.replace("+aiosqlite", ""))
    Base.metadata.create_all(engine)
    with OrmSession(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def box() -> TokenBox:
    return TokenBox(TokenBox.new_key())


@pytest.fixture
async def ctx(db_url: str, sync_db: OrmSession, box: TokenBox) -> AsyncIterator[dict[str, Any]]:
    engine = create_async_engine(db_url)
    yield {
        "settings": Settings(database_url=db_url),
        "db": session_factory(engine),
        "catalogue": FakeCatalogue(),
        "app_tokens": FakeTokens(),
        "box": box,
        "oauth": object(),  # tokens in these tests are fresh, so it is never called
        "redis": FakeQueue(),
    }
    await engine.dispose()
