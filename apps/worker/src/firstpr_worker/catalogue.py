"""Running the engine's sync for one token and a set of repos.

The engine (packages/core) already knows how to sync repos cheaply: stable
ordering so pages come back as 304s, one transaction per repo, and resuming an
interrupted run. Here it is pointed at a Postgres database and told which repos
each token is responsible for, through the engine's own per-user watchlists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import delete, select

from issueradar.config.settings import Settings, load_settings
from issueradar.engine.rules import RepoRules, load_packs, load_rules
from issueradar.github import GitHubClient
from issueradar.radar import Radar
from issueradar.storage.db import Database, open_database
from issueradar.storage.etag_cache import SqlEtagCache
from issueradar.storage.models import LOCAL_USER_ID, User, Watchlist
from issueradar.sync.enrich import Enricher
from issueradar.sync.service import RepoOutcome, SyncService

APP_OWNER = LOCAL_USER_ID
# Platform user 7 is engine user 1_000_007, so they never collide with the app's own list.
USER_OFFSET = 1_000_000


def engine_user_id(platform_user_id: int) -> int:
    return USER_OFFSET + platform_user_id


@dataclass
class SyncResult:
    status: str  # completed, interrupted
    outcomes: list[RepoOutcome]
    message: str | None
    budget: dict[str, Any]


def pack_repos() -> list[str]:
    """Every repo in the starter packs: the first catalogue."""
    seen: dict[str, str] = {}
    for pack in load_packs().values():
        for repo in pack.repos:
            seen.setdefault(repo.lower(), repo)
    return sorted(seen.values(), key=str.lower)


class Catalogue:
    def __init__(
        self, url: str, pause_share: float, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.db: Database = open_database(url)
        self.transport = transport  # tests point the engine at a fake GitHub
        base = load_settings()
        budget = base.github.budget.model_copy(update={"safety_margin": pause_share})
        self.settings: Settings = base.model_copy(
            update={"github": base.github.model_copy(update={"budget": budget})}
        )
        self.rules: dict[str, RepoRules] = load_rules()

    def set_watchlist(self, owner: int, repos: set[str]) -> None:
        """Make the engine's watchlist for `owner` exactly `repos`."""
        with self.db.sessions.begin() as session:
            if session.get(User, owner) is None:
                session.add(User(id=owner, login=None))
            current = {
                w.repo_full_name.lower(): w
                for w in session.scalars(select(Watchlist).where(Watchlist.user_id == owner))
            }
            wanted = {r.lower(): r for r in repos}
            for key in current.keys() - wanted.keys():
                session.delete(current[key])
            for key in wanted.keys() - current.keys():
                session.add(Watchlist(user_id=owner, repo_full_name=wanted[key]))

    def clear_watchlist(self, owner: int) -> None:
        with self.db.sessions.begin() as session:
            session.execute(delete(Watchlist).where(Watchlist.user_id == owner))

    async def sync(
        self, owner: int, repos: set[str], token: str, cache_identity: str
    ) -> SyncResult:
        self.set_watchlist(owner, repos)
        if not repos:
            return SyncResult("completed", [], None, {})
        async with GitHubClient(
            self.settings.github,
            token,
            cache=SqlEtagCache(self.db.sessions),
            cache_identity=cache_identity,
            transport=self.transport,
        ) as client:
            service = SyncService(
                self.db,
                client,
                self.settings,
                user_id=owner,
                enricher=Enricher(self.db, client, self.settings, self.rules),
                radar=Radar(self.db, self.settings, self.rules, None),
            )
            report = await service.run()
        core = report.budget.resources.get("core") if report.budget else None
        budget = {
            "limit": core.limit if core else None,
            "remaining": core.remaining if core else None,
            "reset_at": core.reset_at if core else None,
            "requests": report.budget.total_requests if report.budget else 0,
            "not_modified": report.budget.not_modified if report.budget else 0,
            "paused": report.status == "interrupted",
        }
        return SyncResult(report.status, report.outcomes, report.message, budget)
