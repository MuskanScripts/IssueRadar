"""Enrichment: the extra data the engines need, fetched only where it matters.

Per repo, after the open lists are stored (ADR 0014):

1. Layer 1: one search, ``repo:o/r is:issue is:open linked:pr``, marks issues
   GitHub links to a PR by a closing reference.
2. Finalists: open issues with no assignee, no linked PR and no closing
   reference from an open PR, most recently updated first, up to
   ``enrich.max_issues_per_repo``. For each, comments (only when the issue
   changed since they were read) and the timeline (always conditional, so an
   unchanged timeline is a free 304). Layer 3 comes from the timeline.
3. Repo health inputs, at most once per ``health.cache_hours``: community
   profile, CONTRIBUTING text, recent closed PRs, language breakdown and
   manifest files.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from issueradar.config.settings import Settings
from issueradar.engine import health as health_engine
from issueradar.engine import stack as stack_engine
from issueradar.engine.rules import RepoRules, rules_for
from issueradar.github.client import GitHubClient
from issueradar.github.errors import GitHubError, NotFound, QuotaExhausted
from issueradar.storage.db import Database
from issueradar.storage.models import Issue, IssueSignal, PullRequest, Repo, as_utc, utcnow
from issueradar.sync.normalize import is_bot, parse_time, pull_request_fields

log = logging.getLogger(__name__)
MAX_DETAIL_PAGES = 3


@dataclass
class EnrichOutcome:
    finalists: int = 0
    comments_read: int = 0
    timelines_read: int = 0
    health_score: int | None = None
    notes: list[str] = field(default_factory=list)


class Enricher:
    def __init__(
        self,
        db: Database,
        client: GitHubClient,
        settings: Settings,
        rules: dict[str, RepoRules],
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.db = db
        self.client = client
        self.settings = settings
        self.rules = rules
        self.clock = clock

    # ------------------------------------------------------------ per repo

    async def enrich_repo(self, full_name: str) -> EnrichOutcome:
        outcome = EnrichOutcome()
        cfg = self.settings.enrich
        if cfg.linked_pr_search:
            await self._linked_pr_search(full_name, outcome)
        failed = 0
        for issue_id, number, changed in self._finalists(full_name):
            outcome.finalists += 1
            try:
                if changed:
                    await self._read_comments(issue_id, full_name, number)
                    outcome.comments_read += 1
                if cfg.fetch_timeline:
                    await self._read_timeline(issue_id, full_name, number)
                    outcome.timelines_read += 1
            except QuotaExhausted:
                raise
            except GitHubError as exc:  # one deleted or hidden issue must not stop the repo
                failed += 1
                log.warning("could not read details of %s#%s: %s", full_name, number, exc)
        if failed:
            outcome.notes.append(f"details of {failed} issue(s) could not be read")
        if cfg.repo_health:
            try:
                outcome.health_score = await self.refresh_health(full_name)
            except QuotaExhausted:
                raise
            except GitHubError as exc:
                outcome.notes.append(f"health not updated: {exc}")
        return outcome

    async def _linked_pr_search(self, full_name: str, outcome: EnrichOutcome) -> None:
        query = f"repo:{full_name} is:issue is:open linked:pr"
        numbers: set[int] = set()
        complete = True
        try:
            async for page in self.client.paginate(
                "/search/issues",
                params={"q": query, "per_page": self.settings.github.search.per_page},
                max_pages=self.settings.github.search.max_results_per_query
                // self.settings.github.search.per_page,
            ):
                data = page.data or {}
                numbers.update(item["number"] for item in data.get("items", []))
                if data.get("incomplete_results"):
                    complete = False
                total = int(data.get("total_count", 0))
            complete = complete and len(numbers) >= total
        except QuotaExhausted:
            raise
        except GitHubError as exc:
            outcome.notes.append(f"linked-PR search failed: {exc}")
            return
        if not complete:
            outcome.notes.append("linked-PR search returned partial results")
        with self.db.sessions.begin() as session:
            repo = session.scalar(select(Repo).where(Repo.full_name == full_name))
            if repo is None:
                return
            for issue in session.scalars(
                select(Issue).where(Issue.repo_id == repo.id, Issue.state == "open")
            ):
                if issue.number in numbers:
                    issue.linked_pr = True
                elif complete:
                    issue.linked_pr = False

    def _finalists(self, full_name: str) -> list[tuple[int, int, bool]]:
        """(issue id, number, comments need reading) for this repo's finalists."""
        with self.db.sessions() as session:
            repo = session.scalar(select(Repo).where(Repo.full_name == full_name))
            if repo is None:
                return []
            closing: set[int] = set()
            for pr in session.scalars(
                select(PullRequest).where(
                    PullRequest.repo_id == repo.id, PullRequest.state == "open"
                )
            ):
                if not pr.author_is_bot:
                    closing.update(pr.closing_issues)
            rows = session.scalars(
                select(Issue)
                .where(Issue.repo_id == repo.id, Issue.state == "open")
                .order_by(Issue.gh_updated_at.desc())
            )
            picked = []
            for issue in rows:
                if issue.assignees or issue.linked_pr or issue.number in closing or issue.locked:
                    continue
                needs_comments = issue.comments_count > 0 and as_utc(
                    issue.comments_fetched_for
                ) != as_utc(issue.gh_updated_at)
                picked.append((issue.id, issue.number, needs_comments))
                if len(picked) >= self.settings.enrich.max_issues_per_repo:
                    break
            return picked

    async def _pages(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        async for page in self.client.paginate(
            path, params={"per_page": 100}, max_pages=MAX_DETAIL_PAGES
        ):
            items.extend(page.data or [])
        return items

    async def _read_comments(self, issue_id: int, full_name: str, number: int) -> None:
        items = await self._pages(f"/repos/{full_name}/issues/{number}/comments")
        with self.db.sessions.begin() as session:
            issue = session.get_one(Issue, issue_id)
            session.execute(
                delete(IssueSignal).where(
                    IssueSignal.issue_id == issue_id, IssueSignal.kind == "comment"
                )
            )
            for item in items:
                user = item.get("user") or {}
                session.add(
                    IssueSignal(
                        issue_id=issue_id,
                        kind="comment",
                        source_id=str(item["id"]),
                        author_login=user.get("login"),
                        author_association=item.get("author_association"),
                        body=item.get("body") or "",
                        data={"is_bot": is_bot(user)},
                        gh_created_at=parse_time(item.get("created_at")),
                    )
                )
            issue.comments_fetched_for = issue.gh_updated_at

    async def _read_timeline(self, issue_id: int, full_name: str, number: int) -> None:
        items = await self._pages(f"/repos/{full_name}/issues/{number}/timeline")
        with self.db.sessions.begin() as session:
            issue = session.get_one(Issue, issue_id)
            session.execute(
                delete(IssueSignal).where(
                    IssueSignal.issue_id == issue_id,
                    IssueSignal.kind.in_(["cross_reference", "connected", "disconnected"]),
                )
            )
            for index, event in enumerate(items):
                signal = timeline_signal(event, index)
                if signal is not None:
                    kind, source_id, data, created = signal
                    session.add(
                        IssueSignal(
                            issue_id=issue_id,
                            kind=kind,
                            source_id=source_id,
                            data=data,
                            gh_created_at=created,
                        )
                    )
            issue.timeline_checked_at = self.clock()

    # --------------------------------------------------------------- health

    async def refresh_health(self, full_name: str, *, force: bool = False) -> int | None:
        with self.db.sessions() as session:
            repo = session.scalar(select(Repo).where(Repo.full_name == full_name))
            if repo is None:
                return None
            computed = as_utc(repo.health_computed_at)
            fresh = computed and self.clock() - computed < timedelta(
                hours=self.settings.health.cache_hours
            )
            if fresh and not force:
                return int(repo.health.get("score", 0)) if repo.health else None
            archived = repo.archived

        community: dict[str, Any] = {}
        contributing_text: str | None = None
        if not archived:
            try:
                profile = (await self.client.get(f"/repos/{full_name}/community/profile")).data
                files = (profile or {}).get("files") or {}
                community = {
                    "contributing": bool(files.get("contributing")),
                    "issue_template": bool(files.get("issue_template")),
                    "pull_request_template": bool(files.get("pull_request_template")),
                }
                if not community["issue_template"]:
                    # The community profile does not count YAML issue forms (seen on
                    # real data, RESULTS.md), so look in the folder itself.
                    community["issue_template"] = await self._has_issue_forms(full_name)
                contributing = files.get("contributing") or {}
                if contributing.get("url"):
                    contributing_text = await self._file_text(contributing["url"])
            except NotFound:
                community = {}
        closed = await self._closed_pulls(full_name)
        languages = (await self.client.get(f"/repos/{full_name}/languages")).data or {}
        frameworks = await self._frameworks(full_name)

        with self.db.sessions.begin() as session:
            repo = session.scalar(select(Repo).where(Repo.full_name == full_name))
            if repo is None:
                return None
            self._store_closed(session, repo, closed)
            repo.community = community
            repo.contributing_text = contributing_text
            repo.languages = dict(languages)
            repo.frameworks = frameworks
            result = self._compute_health(session, repo)
            repo.health = {
                "score": result.score,
                "parts": result.parts,
                "reasons": [str(r) for r in result.reasons],
                "flags": {
                    "cla": result.flags.cla,
                    "dco": result.flags.dco,
                    "ai_policy": result.flags.ai_policy,
                    "issue_required": result.flags.issue_required,
                    "reasons": result.flags.reasons,
                },
            }
            repo.health_computed_at = self.clock()
            return result.score

    async def _has_issue_forms(self, full_name: str) -> bool:
        try:
            listing = (
                await self.client.get(f"/repos/{full_name}/contents/.github/ISSUE_TEMPLATE")
            ).data
        except NotFound:
            return False
        return any(
            entry.get("name", "").endswith((".yml", ".yaml", ".md"))
            and entry.get("name") != "config.yml"
            for entry in listing or []
        )

    async def _file_text(self, url: str) -> str | None:
        try:
            data = (await self.client.get(url)).data or {}
        except NotFound:
            return None
        if data.get("encoding") == "base64" and data.get("content"):
            raw = base64.b64decode(data["content"])
            return raw.decode("utf-8", errors="replace")[:50_000]
        return None

    async def _closed_pulls(self, full_name: str) -> list[dict[str, Any]]:
        page = await self.client.get(
            f"/repos/{full_name}/pulls",
            params={
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": self.settings.health.closed_prs_sample,
            },
        )
        return list(page.data or [])

    async def _frameworks(self, full_name: str) -> list[str]:
        try:
            listing = (await self.client.get(f"/repos/{full_name}/contents")).data or []
        except NotFound:
            return []
        wanted = set(self.settings.stack.manifests)
        names: set[str] = set()
        for entry in listing:
            if entry.get("type") == "file" and entry.get("name") in wanted and entry.get("url"):
                text = await self._file_text(entry["url"])
                if text:
                    names |= stack_engine.dependency_names(entry["name"], text)
        return stack_engine.frameworks_from_dependencies(names, self.settings.stack)

    def _store_closed(self, session: Session, repo: Repo, items: list[dict[str, Any]]) -> None:
        for item in items:
            fields = pull_request_fields(item, repo.full_name)
            pr = session.scalar(
                select(PullRequest).where(PullRequest.github_id == fields["github_id"])
            )
            if pr is None:
                session.add(PullRequest(repo_id=repo.id, **fields))
            else:
                for key, value in fields.items():
                    setattr(pr, key, value)

    def _compute_health(self, session: Session, repo: Repo) -> health_engine.HealthResult:
        rules = rules_for(self.rules, repo.full_name)
        maintainers = {a.upper() for a in self.settings.availability.maintainer_associations}
        session.flush()

        outcomes: list[str] = []
        for pr in session.scalars(
            select(PullRequest).where(PullRequest.repo_id == repo.id, PullRequest.state == "closed")
        ):
            if pr.author_is_bot or (pr.author_association or "").upper() in maintainers:
                continue
            outcomes.append(
                health_engine.outside_pr_outcome(
                    merged=pr.merged_at is not None, labels=pr.labels, rules=rules
                )
            )

        response_days: list[float] = []
        issues = session.scalars(
            select(Issue).where(Issue.repo_id == repo.id, Issue.comments_fetched_for.is_not(None))
        )
        for issue in issues:
            if (
                issue.author_association or ""
            ).upper() in maintainers or issue.author_type == "Bot":
                continue
            first = session.scalar(
                select(IssueSignal.gh_created_at)
                .where(
                    IssueSignal.issue_id == issue.id,
                    IssueSignal.kind == "comment",
                    IssueSignal.author_association.in_(maintainers),
                )
                .order_by(IssueSignal.gh_created_at)
            )
            created = as_utc(issue.gh_created_at)
            replied = as_utc(first)
            if replied is not None and created is not None:
                response_days.append((replied - created).total_seconds() / 86400)

        open_count = (
            session.scalar(
                select(func.count())
                .select_from(PullRequest)
                .where(PullRequest.repo_id == repo.id, PullRequest.state == "open")
            )
            or 0
        )
        inputs = health_engine.HealthInputs(
            pushed_at=as_utc(repo.pushed_at),
            open_pull_requests=open_count,
            first_response_days=response_days,
            outside_pr_outcomes=outcomes,
            has_contributing=repo.community.get("contributing") if repo.community else None,
            has_issue_template=repo.community.get("issue_template") if repo.community else None,
            has_pr_template=repo.community.get("pull_request_template") if repo.community else None,
            contributing_text=repo.contributing_text,
            archived=repo.archived or repo.disabled,
        )
        return health_engine.compute(
            inputs,
            self.settings.health,
            self.clock(),
            issue_required_rule=rules.issue_required_before_pr,
        )


def timeline_signal(
    event: dict[str, Any], index: int
) -> tuple[str, str, dict[str, Any], datetime | None] | None:
    """Turn one REST timeline event into a stored signal, or None to skip it."""
    kind = event.get("event")
    created = parse_time(event.get("created_at"))
    if kind == "cross-referenced":
        source = (event.get("source") or {}).get("issue") or {}
        if not source:
            return None
        pr = source.get("pull_request") or {}
        repo = ((source.get("repository") or {}).get("full_name")) or ""
        state = source.get("state", "open")
        if pr.get("merged_at"):
            state = "merged"
        data = {
            "is_pr": bool(pr),
            "number": source.get("number"),
            "repo": repo,
            "state": state,
            "is_bot": is_bot(source.get("user") or {}),
        }
        return "cross_reference", f"{repo}#{source.get('number')}", data, created
    if kind in ("connected", "disconnected"):
        return kind, str(event.get("id") or f"{kind}-{index}"), {}, created
    return None
