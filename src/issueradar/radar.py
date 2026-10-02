"""Radar: runs every engine on stored data. Used by explain, find, eval and sync.

Nothing here talks to GitHub; it reads what sync stored.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from issueradar.config.settings import Settings
from issueradar.engine import availability, difficulty, ranking, stack
from issueradar.engine.rules import RepoRules, rules_for
from issueradar.engine.text import file_paths
from issueradar.engine.types import Comment, IssueContext, PrLink
from issueradar.models import IssueType, Tier, TimeBucket
from issueradar.storage.db import Database
from issueradar.storage.models import (
    LOCAL_USER_ID,
    Issue,
    IssueSignal,
    PullRequest,
    Repo,
    ScoreSnapshot,
    as_utc,
    utcnow,
)


@dataclass
class IssueReport:
    repo: str
    number: int
    title: str
    url: str | None
    labels: list[str]
    comments: int
    updated_at: datetime | None
    stars: int
    language: str | None
    availability: availability.AvailabilityResult
    difficulty: difficulty.DifficultyResult
    health_score: int | None
    health_reasons: list[str]
    flags: dict[str, object]
    stack: stack.StackResult
    rank: ranking.RankResult | None
    frameworks: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    repo_notes: str | None = None


@dataclass
class Filters:
    tiers: list[Tier] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    issue_types: list[IssueType] = field(default_factory=list)
    times: list[TimeBucket] = field(default_factory=list)
    min_health: int | None = None
    min_stars: int | None = None
    max_stars: int | None = None
    max_age_days: int | None = None
    max_comments: int | None = None
    exclude_discussion_first: bool = False
    repos: list[str] = field(default_factory=list)
    include_unavailable: bool = False


def repo_stack(repo: Repo, settings: Settings) -> stack.RepoStack:
    languages = stack.languages_from_breakdown(repo.languages) if repo.languages else []
    if not languages and repo.language:
        languages = [repo.language.lower()]
    return stack.RepoStack(
        languages=languages,
        frameworks=list(repo.frameworks or []),
        domains=stack.domains_from_topics(list(repo.topics or []), settings.stack),
    )


def build_context(session: Session, issue: Issue, repo: Repo) -> IssueContext:
    comments: list[Comment] | None
    if issue.comments_fetched_for is None and issue.comments_count > 0:
        comments = None
    else:
        comments = [
            Comment(
                author=s.author_login,
                association=s.author_association,
                body=s.body or "",
                created_at=as_utc(s.gh_created_at) or utcnow(),
                is_bot=bool(s.data.get("is_bot")),
            )
            for s in session.scalars(
                select(IssueSignal).where(
                    IssueSignal.issue_id == issue.id, IssueSignal.kind == "comment"
                )
            )
        ]

    links: list[PrLink] = []
    for pr in session.scalars(select(PullRequest).where(PullRequest.repo_id == repo.id)):
        state = "merged" if pr.merged_at else pr.state
        if state not in ("open", "merged"):
            continue
        if issue.number in pr.closing_issues:
            links.append(PrLink(pr.number, state, "closing_reference", pr.author_is_bot))
        elif issue.number in pr.mentioned_issues and state == "open":
            links.append(PrLink(pr.number, state, "mention", pr.author_is_bot))
    connected = 0
    for signal in session.scalars(select(IssueSignal).where(IssueSignal.issue_id == issue.id)):
        if signal.kind == "cross_reference" and signal.data.get("is_pr"):
            other = signal.data.get("repo") or None
            links.append(
                PrLink(
                    int(signal.data.get("number") or 0),
                    str(signal.data.get("state")),
                    "timeline",
                    bool(signal.data.get("is_bot")),
                    repo=None if other == repo.full_name else other,
                )
            )
        elif signal.kind == "connected":
            connected += 1
        elif signal.kind == "disconnected":
            connected -= 1
    if connected > 0:
        links.append(PrLink(0, "open", "connected"))
    if issue.linked_pr:
        links.append(PrLink(0, "open", "search"))

    return IssueContext(
        repo=repo.full_name,
        number=issue.number,
        title=issue.title,
        body=issue.body or "",
        state=issue.state,
        labels=list(issue.labels),
        assignees=list(issue.assignees),
        author=issue.author_login,
        author_is_bot=issue.author_type == "Bot" or (issue.author_login or "").endswith("[bot]"),
        comments_count=issue.comments_count,
        locked=issue.locked,
        created_at=as_utc(issue.gh_created_at),
        updated_at=as_utc(issue.gh_updated_at),
        html_url=issue.html_url,
        comments=comments,
        pr_links=links,
        timeline_checked=issue.timeline_checked_at is not None,
        linked_pr_search_checked=issue.linked_pr is not None,
    )


class Radar:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        rules: dict[str, RepoRules],
        profile: stack.SkillProfile | None,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.db = db
        self.settings = settings
        self.rules = rules
        self.profile = profile
        self.clock = clock

    def evaluate(self, session: Session, issue: Issue, repo: Repo) -> IssueReport:
        now = self.clock()
        rules = rules_for(self.rules, repo.full_name)
        context = build_context(session, issue, repo)
        avail = availability.assess(context, rules, self.settings.availability, now)
        diff = difficulty.assess(context, rules, self.settings.difficulty)
        repo_tech = repo_stack(repo, self.settings)
        match = stack.match(
            repo_tech,
            file_paths(context.body),
            self.profile,
            self.settings.stack,
        )
        health = repo.health or {}
        health_score = health.get("score")
        rank = ranking.score(
            ranking.RankInputs(
                availability=avail.state,
                tier=diff.tier,
                tier_fit=stack.tier_fit(diff.tier, match.target_tier),
                health=int(health_score) if health_score is not None else 50,
                stack_fit=match.fit,
                updated_at=context.updated_at,
                comments=issue.comments_count,
            ),
            self.settings.ranking,
            now,
        )
        return IssueReport(
            repo=repo.full_name,
            number=issue.number,
            title=issue.title,
            url=issue.html_url,
            labels=list(issue.labels),
            comments=issue.comments_count,
            updated_at=context.updated_at,
            stars=repo.stars,
            language=repo.language,
            availability=avail,
            difficulty=diff,
            health_score=int(health_score) if health_score is not None else None,
            health_reasons=list(health.get("reasons", [])),
            flags=dict(health.get("flags", {})),
            stack=match,
            rank=rank,
            frameworks=repo_tech.frameworks,
            domains=repo_tech.domains,
            repo_notes=rules.notes,
        )

    def report_for(self, full_name: str, number: int) -> IssueReport | None:
        with self.db.sessions() as session:
            repo = session.scalar(select(Repo).where(Repo.full_name.ilike(full_name)))
            if repo is None:
                return None
            issue = session.scalar(
                select(Issue).where(Issue.repo_id == repo.id, Issue.number == number)
            )
            if issue is None:
                return None
            return self.evaluate(session, issue, repo)

    def find(self, filters: Filters, limit: int | None = None) -> list[IssueReport]:
        reports: list[IssueReport] = []
        now = self.clock()
        with self.db.sessions() as session:
            query = select(Issue, Repo).join(Repo).where(Issue.state == "open")
            if filters.repos:
                query = query.where(Repo.full_name.in_(filters.repos))
            for issue, repo in session.execute(query):
                report = self.evaluate(session, issue, repo)
                if not filters.include_unavailable and report.rank is None:
                    continue
                if not _matches(report, filters, now):
                    continue
                reports.append(report)
        reports.sort(key=lambda r: r.rank.score if r.rank else -1.0, reverse=True)
        return reports[:limit] if limit else reports

    def snapshot_repo(self, full_name: str, user_id: int = LOCAL_USER_ID) -> int:
        """Store the profile-independent results for every open issue of a repo."""
        count = 0
        with self.db.sessions.begin() as session:
            repo = session.scalar(select(Repo).where(Repo.full_name == full_name))
            if repo is None:
                return 0
            for issue in session.scalars(
                select(Issue).where(Issue.repo_id == repo.id, Issue.state == "open")
            ):
                report = self.evaluate(session, issue, repo)
                session.add(
                    ScoreSnapshot(
                        user_id=user_id,
                        issue_id=issue.id,
                        computed_at=self.clock(),
                        availability=report.availability.state.value,
                        tier=report.difficulty.tier.value,
                        difficulty_score=report.difficulty.score,
                        health_score=report.health_score,
                        rank_score=report.rank.score if report.rank else None,
                        reasons={
                            "availability": [str(r) for r in report.availability.reasons],
                            "difficulty": [str(r) for r in report.difficulty.reasons],
                        },
                    )
                )
                count += 1
        return count


def _matches(report: IssueReport, f: Filters, now: datetime) -> bool:
    lang = (report.language or "").lower()
    if f.tiers and report.difficulty.tier not in f.tiers:
        return False
    if f.languages and lang not in {x.lower() for x in f.languages}:
        return False
    if f.issue_types and report.difficulty.issue_type not in f.issue_types:
        return False
    if f.times and report.difficulty.time_bucket not in f.times:
        return False
    if f.min_health is not None and (report.health_score or 0) < f.min_health:
        return False
    if f.min_stars is not None and report.stars < f.min_stars:
        return False
    if f.max_stars is not None and report.stars > f.max_stars:
        return False
    if f.max_comments is not None and report.comments > f.max_comments:
        return False
    if f.exclude_discussion_first and report.difficulty.discussion_first:
        return False
    if (
        f.max_age_days is not None
        and report.updated_at is not None
        and (now - report.updated_at).days > f.max_age_days
    ):
        return False
    if f.frameworks and not {x.lower() for x in f.frameworks} & set(report.frameworks):
        return False
    return not (f.domains and not {x.lower() for x in f.domains} & set(report.domains))
