"""PR tracker (brief 5.9): find the user's pull requests and work out what needs them.

Discovery: ``is:pr author:<login> updated:>=<date>`` search, or, with
``repos``, each repo's PR list filtered by author (no search budget needed).
Details per PR over REST: the PR, its reviews, check runs and combined status
for the head commit, and the issue timeline for activity by others.
Only reads; never comments.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from issueradar.config.settings import Settings
from issueradar.engine.rules import RepoRules, rules_for
from issueradar.github.client import GitHubClient
from issueradar.github.errors import GitHubError, QuotaExhausted
from issueradar.prs.status import Activity, PullFacts, PullStatus, Review, derive, nudge
from issueradar.storage.db import Database
from issueradar.storage.models import LOCAL_USER_ID, TrackedPullRequest, User, utcnow
from issueradar.sync.normalize import parse_time

TIMELINE_KINDS = {
    "commented": "commented",
    "reviewed": "reviewed",
    "committed": "pushed a commit",
    "labeled": "added a label",
    "review_requested": "requested a review",
    "ready_for_review": "marked it ready for review",
    "convert_to_draft": "marked it as a draft",
    "merged": "merged it",
    "closed": "closed it",
    "reopened": "reopened it",
    "head_ref_force_pushed": "force-pushed",
}


@dataclass
class TrackReport:
    login: str
    tracked: list[TrackedPullRequest] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def _actor(event: dict[str, Any]) -> str | None:
    for key in ("actor", "user", "author"):
        value = event.get(key)
        if isinstance(value, dict) and value.get("login"):
            return str(value["login"])
    return None


def activity_from_timeline(events: list[dict[str, Any]]) -> list[Activity]:
    items = []
    for event in events:
        kind = event.get("event")
        if kind not in TIMELINE_KINDS:
            continue
        when = parse_time(
            event.get("created_at")
            or event.get("submitted_at")
            or (event.get("committer") or {}).get("date")
        )
        if when is None:
            continue
        actor = _actor(event) if kind != "committed" else None
        who = f"@{actor}" if actor else ((event.get("author") or {}).get("name") or "Someone")
        items.append(Activity(when, actor, kind, f"{who} {TIMELINE_KINDS[kind]}"))
    return sorted(items, key=lambda a: a.at)


class PullTracker:
    def __init__(
        self,
        db: Database,
        client: GitHubClient,
        settings: Settings,
        rules: dict[str, RepoRules],
        *,
        user_id: int = LOCAL_USER_ID,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.db = db
        self.client = client
        self.settings = settings
        self.rules = rules
        self.user_id = user_id
        self.clock = clock

    async def login(self, override: str | None = None) -> str:
        if override:
            return override
        data = (await self.client.get("/user", conditional=False)).data or {}
        login = str(data.get("login") or "")
        if not login:
            raise GitHubError("GitHub did not say who the token belongs to; pass --author.")
        with self.db.sessions.begin() as session:
            user = session.get(User, self.user_id)
            if user is not None and user.login != login:
                user.login = login
        return login

    async def discover(self, login: str, repos: list[str] | None = None) -> list[tuple[str, int]]:
        since = (self.clock() - timedelta(days=self.settings.pull_requests.track_days)).date()
        found: list[tuple[str, int]] = []
        if repos:
            for repo in repos:
                async for page in self.client.paginate(
                    f"/repos/{repo}/pulls",
                    params={
                        "state": "all",
                        "per_page": 100,
                        "sort": "updated",
                        "direction": "desc",
                    },
                    max_pages=3,
                ):
                    for pr in page.data or []:
                        updated = parse_time(pr.get("updated_at"))
                        if (pr.get("user") or {}).get("login", "").lower() == login.lower() and (
                            updated is None or updated.date() >= since
                        ):
                            found.append((repo, int(pr["number"])))
            return found
        query = f"is:pr author:{login} updated:>={since.isoformat()}"
        async for page in self.client.paginate(
            "/search/issues", params={"q": query, "per_page": 100}, max_pages=3
        ):
            for item in (page.data or {}).get("items", []):
                repo_url = str(item.get("repository_url", ""))
                repo = "/".join(repo_url.rstrip("/").split("/")[-2:])
                found.append((repo, int(item["number"])))
        return found

    async def facts(self, repo: str, number: int) -> tuple[PullFacts, list[Activity]]:
        pr = (await self.client.get(f"/repos/{repo}/pulls/{number}")).data
        reviews_raw = await self._all(f"/repos/{repo}/pulls/{number}/reviews")
        sha = pr["head"]["sha"]
        conclusions: list[str] = []
        combined: str | None = None
        if pr.get("state") == "open":
            runs = (
                await self.client.get(
                    f"/repos/{repo}/commits/{sha}/check-runs", params={"per_page": 100}
                )
            ).data or {}
            conclusions = [
                str(r.get("conclusion")) for r in runs.get("check_runs", []) if r.get("conclusion")
            ]
            status = (await self.client.get(f"/repos/{repo}/commits/{sha}/status")).data or {}
            if status.get("total_count"):
                combined = status.get("state")
        timeline = await self._all(f"/repos/{repo}/issues/{number}/timeline")
        activity = activity_from_timeline(timeline)
        rules = rules_for(self.rules, repo)
        facts = PullFacts(
            repo=repo,
            number=number,
            title=pr.get("title") or "",
            author=(pr.get("user") or {}).get("login", ""),
            state=pr.get("state", "open"),
            merged=bool(pr.get("merged") or pr.get("merged_at")),
            draft=bool(pr.get("draft")),
            mergeable=pr.get("mergeable"),
            mergeable_state=pr.get("mergeable_state"),
            opened_at=parse_time(pr.get("created_at")) or self.clock(),
            check_conclusions=conclusions,
            combined_status=combined,
            reviews=[
                Review(
                    (r.get("user") or {}).get("login", ""),
                    str(r.get("state")),
                    parse_time(r.get("submitted_at")),
                )
                for r in reviews_raw
            ],
            activity=activity,
            labels=[lbl["name"] for lbl in pr.get("labels") or [] if isinstance(lbl, dict)],
            accepted_by_bot_label=rules.accepted_by_bot.label if rules.accepted_by_bot else None,
            url=pr.get("html_url"),
            closed_at=parse_time(pr.get("merged_at") or pr.get("closed_at")),
        )
        return facts, activity

    async def _all(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        async for page in self.client.paginate(path, params={"per_page": 100}, max_pages=3):
            items.extend(page.data or [])
        return items

    async def run(
        self, *, author: str | None = None, repos: list[str] | None = None
    ) -> TrackReport:
        login = await self.login(author)
        report = TrackReport(login=login)
        for repo, number in await self.discover(login, repos):
            try:
                facts, activity = await self.facts(repo, number)
            except QuotaExhausted:
                raise
            except GitHubError as exc:
                report.failed[f"{repo}#{number}"] = str(exc)
                continue
            status = derive(facts, self.clock(), self.settings.pull_requests.stale_days)
            report.tracked.append(self._store(facts, status, activity))
        return report

    def _store(
        self, facts: PullFacts, status: PullStatus, activity: list[Activity]
    ) -> TrackedPullRequest:
        others = [
            r.submitted_at
            for r in facts.reviews
            if r.reviewer != facts.author and r.submitted_at is not None
        ]
        with self.db.sessions.begin() as session:
            row = session.scalar(
                select(TrackedPullRequest).where(
                    TrackedPullRequest.user_id == self.user_id,
                    TrackedPullRequest.repo_full_name == facts.repo,
                    TrackedPullRequest.number == facts.number,
                )
            )
            if row is None:
                row = TrackedPullRequest(
                    user_id=self.user_id, repo_full_name=facts.repo, number=facts.number
                )
                session.add(row)
            row.title = facts.title
            row.url = facts.url
            row.state = facts.state
            row.merged = facts.merged
            row.draft = facts.draft
            row.status = status.status.value
            row.needs_you = status.needs_you
            row.reasons = status.reasons
            row.nudge = nudge(facts, status)
            row.days_quiet = status.days_quiet
            row.reviewed = bool(others)
            row.opened_at = facts.opened_at
            row.closed_at = facts.closed_at
            row.first_review_at = min(others) if others else None
            row.timeline = [
                {"at": a.at.isoformat(), "actor": a.actor, "kind": a.kind, "text": a.text}
                for a in activity
            ]
            row.checked_at = self.clock()
            session.flush()
            session.expunge(row)
            return row


def tracked(db: Database, user_id: int = LOCAL_USER_ID) -> list[TrackedPullRequest]:
    """Stored PRs, most urgent first."""
    from issueradar.models import PullRequestStatus
    from issueradar.prs.status import PRIORITY

    with db.sessions() as session:
        rows = list(
            session.scalars(select(TrackedPullRequest).where(TrackedPullRequest.user_id == user_id))
        )
    return sorted(rows, key=lambda r: (PRIORITY[PullRequestStatus(r.status)], -r.number))
