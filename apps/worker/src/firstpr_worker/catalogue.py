"""Running the engine's sync for one token and a set of repos.

The engine (packages/core) already knows how to sync repos cheaply: stable
ordering so pages come back as 304s, one transaction per repo, and resuming an
interrupted run. Here it is pointed at a Postgres database and told which repos
each token is responsible for, through the engine's own per-user watchlists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import create_engine, delete, func, make_url, select, text
from sqlalchemy.exc import OperationalError

from issueradar.config.settings import Settings, load_settings
from issueradar.engine import coach
from issueradar.engine.rules import RepoRules, load_packs, load_rules
from issueradar.engine.text import file_paths
from issueradar.github import GitHubClient
from issueradar.github.errors import GitHubError, QuotaExhausted
from issueradar.prs.status import Activity, PullFacts, PullStatus, derive, nudge
from issueradar.prs.tracker import PullTracker
from issueradar.radar import Preloaded, Radar, repo_stack
from issueradar.storage.db import Database, open_database
from issueradar.storage.etag_cache import SqlEtagCache
from issueradar.storage.models import LOCAL_USER_ID, Issue, Repo, User, Watchlist, as_utc
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


@dataclass
class Card:
    """One open issue as the platform's issue_cards table stores it."""

    repo_full_name: str
    number: int
    title: str
    url: str | None
    labels: list[str]
    repo_description: str | None
    language: str | None
    languages: list[str]
    frameworks: list[str]
    domains: list[str]
    paths: list[str]
    stars: int
    comments: int
    opened_at: datetime | None
    updated_at: datetime | None
    availability: str
    availability_reasons: list[str]
    tier: str
    difficulty_score: int
    time_bucket: str
    issue_type: str
    difficulty_reasons: list[str]
    discussion_first: bool
    health: int | None
    health_reasons: list[str]
    checklist: list[str] = field(default_factory=list)
    repo_notes: str | None = None


@dataclass
class Tracked:
    facts: PullFacts
    status: PullStatus
    nudge: str | None
    activity: list[Activity]


@dataclass
class TrackResult:
    pulls: list[Tracked] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def pack_repos() -> list[str]:
    """Every repo in the starter packs: the first catalogue."""
    seen: dict[str, str] = {}
    for pack in load_packs().values():
        for repo in pack.repos:
            seen.setdefault(repo.lower(), repo)
    return sorted(seen.values(), key=str.lower)


def ensure_database(url: str) -> bool:
    """Create the engine's Postgres database when it does not exist yet (managed
    Postgres services start with one database). True when it was created."""
    target = make_url(url)
    if not target.drivername.startswith("postgresql") or not target.database:
        return False
    engine = create_engine(target)
    try:
        with engine.connect():
            return False
    except OperationalError as error:
        if "does not exist" not in str(error):
            raise
    finally:
        engine.dispose()
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin.dispose()
    return True


class Catalogue:
    def __init__(
        self,
        url: str,
        pause_share: float,
        transport: httpx.AsyncBaseTransport | None = None,
        api_url: str | None = None,
    ) -> None:
        self.db: Database = open_database(url)
        self.transport = transport  # tests point the engine at a fake GitHub
        base = load_settings()
        budget = base.github.budget.model_copy(update={"safety_margin": pause_share})
        github: dict[str, Any] = {"budget": budget}
        if api_url:  # only changed to point at a fake GitHub in local end-to-end tests
            github |= {
                "api_url": api_url.rstrip("/"),
                "graphql_url": f"{api_url.rstrip('/')}/graphql",
            }
        self.settings: Settings = base.model_copy(
            update={"github": base.github.model_copy(update=github)}
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

    def cards(self, repos: set[str]) -> dict[str, list[Card]]:
        """Every open issue of these repos with the engine's verdicts, by repo.

        Repos the engine has no data for are left out, so the caller can tell
        "no open issues" (an empty list) from "not synced yet" (missing).
        """
        radar = Radar(self.db, self.settings, self.rules, None)
        out: dict[str, list[Card]] = {}
        wanted = {r.lower() for r in repos}
        if not wanted:
            return out
        with self.db.sessions() as session:
            found = list(
                session.scalars(select(Repo).where(func.lower(Repo.full_name).in_(wanted)))
            )
            preloaded = Preloaded.load(session, {r.id for r in found})
            for repo in found:
                tech = repo_stack(repo, self.settings)
                issues = session.scalars(
                    select(Issue).where(Issue.repo_id == repo.id, Issue.state == "open")
                )
                cards = out.setdefault(repo.full_name, [])
                if repo.archived or repo.disabled:
                    continue
                for issue in issues:
                    report = radar.evaluate(session, issue, repo, preloaded)
                    cards.append(
                        Card(
                            repo_full_name=repo.full_name,
                            number=issue.number,
                            title=issue.title,
                            url=issue.html_url,
                            labels=list(issue.labels),
                            repo_description=repo.description,
                            language=repo.language,
                            languages=tech.languages,
                            frameworks=tech.frameworks,
                            domains=tech.domains,
                            paths=file_paths(issue.body or "")[:20],
                            stars=repo.stars,
                            comments=issue.comments_count,
                            opened_at=as_utc(issue.gh_created_at),
                            updated_at=report.updated_at,
                            availability=report.availability.state.value,
                            availability_reasons=[str(r) for r in report.availability.reasons],
                            tier=report.difficulty.tier.value,
                            difficulty_score=report.difficulty.score,
                            time_bucket=report.difficulty.time_bucket.value,
                            issue_type=report.difficulty.issue_type.value,
                            difficulty_reasons=[str(r) for r in report.difficulty.reasons],
                            discussion_first=report.difficulty.discussion_first,
                            health=report.health_score,
                            health_reasons=report.health_reasons,
                            checklist=coach.checklist(
                                repo.full_name,
                                report.flags,
                                discussion_first=report.difficulty.discussion_first,
                            ),
                            repo_notes=report.repo_notes,
                        )
                    )
        return out

    async def track(
        self,
        token: str,
        cache_identity: str,
        login: str,
        known: list[tuple[str, int]],
        *,
        discover: bool,
        now: datetime,
    ) -> TrackResult:
        """The status of a user's pull requests, with their own token (reads only).

        `known` are pull requests FirstPR already tracks; `discover` also searches
        GitHub for the user's other public pull requests of the last 90 days.
        """
        result = TrackResult()
        async with GitHubClient(
            self.settings.github,
            token,
            cache=SqlEtagCache(self.db.sessions),
            cache_identity=cache_identity,
            transport=self.transport,
        ) as client:
            tracker = PullTracker(self.db, client, self.settings, self.rules, clock=lambda: now)
            pairs = {(r.lower(), n): (r, n) for r, n in known}
            if discover:
                try:
                    for repo, number in await tracker.discover(login, public_only=True):
                        pairs.setdefault((repo.lower(), number), (repo, number))
                except GitHubError as exc:
                    result.failed["search"] = str(exc)
            for repo, number in pairs.values():
                try:
                    facts, activity = await tracker.facts(repo, number)
                except QuotaExhausted:
                    raise
                except GitHubError as exc:
                    result.failed[f"{repo}#{number}"] = str(exc)
                    continue
                if facts.author.lower() != login.lower():
                    continue
                status = derive(facts, now, self.settings.pull_requests.stale_days)
                result.pulls.append(Tracked(facts, status, nudge(facts, status), activity))
        return result
