"""Watchlist sync: fetch each watched repo, its open issues and its open PRs.

How it keeps the API budget low (ADR 0012):

* Lists are fetched in a stable order (``sort=created&direction=asc``) with the
  same parameters every time, so unchanged pages come back as ``304 Not
  Modified`` from the ETag cache.
* Each repo is saved in its own transaction. A repo that fails is recorded and
  skipped; the rest of the run continues.
* If the API budget runs out, the run is marked ``interrupted``. The next
  ``sync`` continues the same run with the repos that were not done yet, so no
  work is lost or repeated.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from issueradar.config.settings import Settings
from issueradar.github.budget import BudgetSummary
from issueradar.github.client import GitHubClient
from issueradar.github.errors import GitHubError, Gone, QuotaExhausted
from issueradar.radar import Radar
from issueradar.storage.db import Database
from issueradar.storage.models import (
    LOCAL_USER_ID,
    Issue,
    PullRequest,
    Repo,
    SyncRun,
    Watchlist,
    utcnow,
)
from issueradar.sync.enrich import Enricher
from issueradar.sync.normalize import (
    is_pull_request,
    issue_fields,
    pull_request_fields,
    repo_fields,
)

NOT_OPEN = "not_open"  # dropped out of the open list: closed, transferred or deleted


@dataclass
class RepoOutcome:
    full_name: str
    status: str  # synced, archived, failed
    open_issues: int = 0
    open_pull_requests: int = 0
    note: str | None = None
    finalists: int = 0
    health: int | None = None


@dataclass
class SyncReport:
    run_id: int
    status: str  # completed, interrupted
    resumed: bool
    outcomes: list[RepoOutcome] = field(default_factory=list)
    message: str | None = None
    budget: BudgetSummary | None = None


@dataclass
class _Listing:
    items: list[dict[str, Any]]
    complete: bool


class SyncService:
    def __init__(
        self,
        db: Database,
        client: GitHubClient,
        settings: Settings,
        *,
        user_id: int = LOCAL_USER_ID,
        clock: Callable[[], datetime] = utcnow,
        enricher: Enricher | None = None,
        radar: Radar | None = None,
    ) -> None:
        self.db = db
        self.client = client
        self.settings = settings
        self.user_id = user_id
        self.clock = clock
        self.enricher = enricher
        self.radar = radar

    async def run(self) -> SyncReport:
        run_id, todo, resumed = self._start_run()
        report = SyncReport(run_id=run_id, status="completed", resumed=resumed)
        start_requests = self.client.budget.summary().total_requests
        start_not_modified = self.client.budget.not_modified

        for full_name in todo:
            try:
                outcome = await self._sync_repo(full_name)
                if outcome.status == "synced":
                    await self._enrich(outcome)
            except QuotaExhausted as exc:
                report.status = "interrupted"
                report.message = str(exc)
                break
            except GitHubError as exc:
                outcome = RepoOutcome(full_name, "failed", note=str(exc))
                self._record_repo_error(full_name, str(exc))
            report.outcomes.append(outcome)
            self._mark_done(run_id, full_name, outcome)

        summary = self.client.budget.summary()
        self._finish_run(
            run_id,
            report,
            requests=summary.total_requests - start_requests,
            not_modified=self.client.budget.not_modified - start_not_modified,
        )
        report.budget = summary
        return report

    async def _enrich(self, outcome: RepoOutcome) -> None:
        if self.enricher is not None:
            extra = await self.enricher.enrich_repo(outcome.full_name)
            outcome.finalists = extra.finalists
            outcome.health = extra.health_score
            if extra.notes:
                outcome.note = "; ".join(filter(None, [outcome.note, *extra.notes]))
        if self.radar is not None:
            self.radar.snapshot_repo(outcome.full_name, self.user_id)

    # ---------------------------------------------------------------- runs

    def _watched(self, session: Session) -> list[str]:
        rows = session.scalars(
            select(Watchlist.repo_full_name)
            .where(Watchlist.user_id == self.user_id)
            .order_by(Watchlist.added_at, Watchlist.id)
        )
        return list(rows)

    def _start_run(self) -> tuple[int, list[str], bool]:
        with self.db.sessions.begin() as session:
            watched = self._watched(session)
            previous = session.scalar(
                select(SyncRun)
                .where(SyncRun.user_id == self.user_id, SyncRun.status == "interrupted")
                .order_by(SyncRun.id.desc())
            )
            if previous is not None:
                done = set(previous.repos_done) | set(previous.repos_failed)
                planned = [r for r in previous.repos_planned if r in watched]
                planned += [r for r in watched if r not in planned]  # newly watched repos
                previous.repos_planned = planned
                previous.status = "running"
                previous.message = None
                return previous.id, [r for r in planned if r not in done], True
            run = SyncRun(user_id=self.user_id, status="running", repos_planned=list(watched))
            session.add(run)
            session.flush()
            return run.id, list(watched), False

    def _mark_done(self, run_id: int, full_name: str, outcome: RepoOutcome) -> None:
        with self.db.sessions.begin() as session:
            run = session.get_one(SyncRun, run_id)
            if outcome.status == "failed":
                run.repos_failed = {**run.repos_failed, full_name: outcome.note or "failed"}
            else:
                failed = dict(run.repos_failed)
                failed.pop(full_name, None)
                run.repos_failed = failed
                run.repos_done = [*run.repos_done, full_name]

    def _finish_run(
        self, run_id: int, report: SyncReport, *, requests: int, not_modified: int
    ) -> None:
        with self.db.sessions.begin() as session:
            run = session.get_one(SyncRun, run_id)
            run.status = report.status
            run.message = report.message
            run.requests += requests
            run.not_modified += not_modified
            if report.status == "completed":
                run.finished_at = self.clock()

    def _record_repo_error(self, full_name: str, message: str) -> None:
        with self.db.sessions.begin() as session:
            repo = session.scalar(select(Repo).where(Repo.full_name == full_name))
            if repo is None:
                session.add(Repo(full_name=full_name, sync_error=message))
            else:
                repo.sync_error = message

    # --------------------------------------------------------------- repos

    async def _list(self, path: str) -> _Listing:
        params = {
            "state": "open",
            "per_page": self.settings.github.rest.per_page,
            "sort": "created",
            "direction": "asc",
        }
        items: list[dict[str, Any]] = []
        last = None
        async for page in self.client.paginate(
            path, params=params, max_pages=self.settings.sync.max_pages_per_list
        ):
            items.extend(page.data or [])
            last = page
        complete = last is None or last.next_url is None
        return _Listing(items, complete)

    async def _sync_repo(self, full_name: str) -> RepoOutcome:
        repo_data = (await self.client.get(f"/repos/{full_name}")).data
        actual_name = repo_data["full_name"]
        archived = bool(repo_data.get("archived")) or bool(repo_data.get("disabled"))

        issues = _Listing([], True)
        pulls = _Listing([], True)
        notes: list[str] = []
        if actual_name != full_name:
            notes.append(f"moved to {actual_name}")
        if not archived:
            if repo_data.get("has_issues", True):
                try:
                    issues = await self._list(f"/repos/{actual_name}/issues")
                except Gone:
                    notes.append("issues are turned off")
            if self.settings.sync.scan_open_pull_requests:
                pulls = await self._list(f"/repos/{actual_name}/pulls")
        for listing, what in ((issues, "issues"), (pulls, "pull requests")):
            if not listing.complete:
                notes.append(f"only the first {len(listing.items)} open {what} were fetched")

        open_issues = [i for i in issues.items if not is_pull_request(i)]
        now = self.clock()
        with self.db.sessions.begin() as session:
            repo = self._upsert_repo(session, full_name, repo_data, now)
            if not archived:
                self._store_issues(session, repo, open_issues, issues.complete, now)
                self._store_pulls(session, repo, pulls.items, pulls.complete, now)
            if actual_name != full_name:
                session.execute(
                    update(Watchlist)
                    .where(Watchlist.user_id == self.user_id, Watchlist.repo_full_name == full_name)
                    .values(repo_full_name=actual_name)
                )

        return RepoOutcome(
            full_name=actual_name,
            status="archived" if archived else "synced",
            open_issues=len(open_issues),
            open_pull_requests=len(pulls.items),
            note="; ".join(notes) or None,
        )

    def _upsert_repo(
        self, session: Session, requested: str, data: dict[str, Any], now: datetime
    ) -> Repo:
        fields = repo_fields(data)
        repo = session.scalar(select(Repo).where(Repo.github_id == fields["github_id"]))
        if repo is None:
            repo = session.scalar(
                select(Repo).where(Repo.full_name.in_([requested, fields["full_name"]]))
            )
        if repo is None:
            repo = Repo(**fields)
            session.add(repo)
        else:
            for key, value in fields.items():
                setattr(repo, key, value)
        repo.last_synced_at = now
        repo.sync_error = None
        session.flush()
        return repo

    def _store_issues(
        self,
        session: Session,
        repo: Repo,
        items: list[dict[str, Any]],
        complete: bool,
        now: datetime,
    ) -> None:
        seen: set[int] = set()
        for item in items:
            fields = issue_fields(item)
            seen.add(fields["github_id"])
            issue = session.scalar(select(Issue).where(Issue.github_id == fields["github_id"]))
            if issue is None:
                issue = Issue(repo_id=repo.id, **fields)
                session.add(issue)
            else:
                issue.repo_id = repo.id
                for key, value in fields.items():
                    setattr(issue, key, value)
            issue.last_seen_open_at = now
        if complete:
            stmt = (
                update(Issue)
                .where(Issue.repo_id == repo.id, Issue.state == "open")
                .values(state=NOT_OPEN)
            )
            if seen:
                stmt = stmt.where(Issue.github_id.not_in(seen))
            session.execute(stmt)

    def _store_pulls(
        self,
        session: Session,
        repo: Repo,
        items: list[dict[str, Any]],
        complete: bool,
        now: datetime,
    ) -> None:
        seen: set[int] = set()
        for item in items:
            fields = pull_request_fields(item, repo.full_name)
            seen.add(fields["github_id"])
            pr = session.scalar(
                select(PullRequest).where(PullRequest.github_id == fields["github_id"])
            )
            if pr is None:
                pr = PullRequest(repo_id=repo.id, **fields)
                session.add(pr)
            else:
                pr.repo_id = repo.id
                for key, value in fields.items():
                    setattr(pr, key, value)
            pr.last_seen_open_at = now
        if complete:
            stmt = (
                update(PullRequest)
                .where(PullRequest.repo_id == repo.id, PullRequest.state == "open")
                .values(state=NOT_OPEN)
            )
            if seen:
                stmt = stmt.where(PullRequest.github_id.not_in(seen))
            session.execute(stmt)
