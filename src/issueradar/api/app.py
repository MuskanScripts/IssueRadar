"""Local HTTP API for the dashboard (FastAPI, OpenAPI at /api/docs).

It reads the local database and runs the engines. The only writes are to that
database (dismiss, snooze, difficulty feedback, profile, saved views); nothing
here talks to GitHub. Bind it to 127.0.0.1 (the default of ``firstpr serve``).
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from issueradar import __version__
from issueradar.api import profile as profile_store
from issueradar.brand import BRAND
from issueradar.config.settings import Settings
from issueradar.digest import DigestBuilder, mark
from issueradar.digest import render as digest_render
from issueradar.digest.builder import issue_key
from issueradar.engine import coach
from issueradar.engine.rules import RepoRules
from issueradar.engine.stack import SkillProfile
from issueradar.models import IssueType, PullRequestStatus, Tier, TimeBucket
from issueradar.prs.tracker import tracked
from issueradar.radar import Filters, IssueReport, Radar
from issueradar.storage.db import Database
from issueradar.storage.models import (
    LOCAL_USER_ID,
    DifficultyFeedback,
    Issue,
    Repo,
    SyncRun,
    TrackedPullRequest,
    Watchlist,
    as_utc,
    utcnow,
)

# ----------------------------------------------------------------- schemas


class Meta(BaseModel):
    name: str
    version: str
    tagline: str
    demo: bool
    token_configured: bool


class IssueOut(BaseModel):
    repo: str
    number: int
    title: str
    url: str | None
    labels: list[str]
    language: str | None
    stars: int
    comments: int
    updated_at: datetime | None
    availability: str
    availability_label: str
    availability_reasons: list[str]
    tier: str
    difficulty_score: int
    time_bucket: str
    issue_type: str
    difficulty_reasons: list[str]
    discussion_first: bool
    health: int | None
    health_reasons: list[str]
    flags: dict[str, Any]
    stack_fit: float
    stack_reasons: list[str]
    rank: float | None
    rank_parts: dict[str, float]
    why: str
    frameworks: list[str]
    domains: list[str]
    checklist: list[str]


class RepoOut(BaseModel):
    full_name: str
    description: str | None
    language: str | None
    stars: int
    archived: bool
    health: int | None
    health_parts: dict[str, float | None]
    health_reasons: list[str]
    open_issues: int
    free_issues: int
    last_synced_at: datetime | None
    pushed_at: datetime | None
    sync_error: str | None


class PullOut(BaseModel):
    repo: str
    number: int
    title: str
    url: str | None
    status: str
    status_label: str
    needs_you: str
    reasons: list[str]
    nudge: str | None
    draft: bool
    days_quiet: int
    opened_at: datetime | None
    closed_at: datetime | None
    timeline: list[dict[str, Any]]


class InsightsOut(BaseModel):
    opened: int
    merged: int
    closed_unmerged: int
    open_now: int
    merge_rate: float | None
    median_hours_to_first_review: float | None
    by_month: list[dict[str, Any]]


class SettingsOut(BaseModel):
    token_configured: bool
    database: str
    last_sync: dict[str, Any] | None
    channels: dict[str, bool]
    limits: dict[str, Any]
    weights: dict[str, float]


class DigestOut(BaseModel):
    title: str
    markdown: str
    html: str
    items: int


class SnoozeIn(BaseModel):
    days: int = 7


class FeedbackIn(BaseModel):
    verdict: Literal["harder", "easier", "about_right"]


class ProfileIO(BaseModel):
    stretch: bool = False
    languages: dict[str, Literal["learning", "medium", "strong"]] = {}
    frameworks: dict[str, Literal["learning", "medium", "strong"]] = {}
    domains: dict[str, Literal["learning", "medium", "strong"]] = {}
    prefer_issue_types: list[str] = []


class SavedView(BaseModel):
    name: str
    filters: dict[str, Any]


# --------------------------------------------------------------- converters


def issue_out(report: IssueReport, settings: Settings) -> IssueOut:
    return IssueOut(
        repo=report.repo,
        number=report.number,
        title=report.title,
        url=report.url,
        labels=report.labels,
        language=report.language,
        stars=report.stars,
        comments=report.comments,
        updated_at=report.updated_at,
        availability=report.availability.state.value,
        availability_label=report.availability.state.label,
        availability_reasons=[str(r) for r in report.availability.reasons],
        tier=report.difficulty.tier.value,
        difficulty_score=report.difficulty.score,
        time_bucket=report.difficulty.time_bucket.value,
        issue_type=report.difficulty.issue_type.value,
        difficulty_reasons=[str(r) for r in report.difficulty.reasons],
        discussion_first=report.difficulty.discussion_first,
        health=report.health_score,
        health_reasons=report.health_reasons,
        flags=report.flags,
        stack_fit=report.stack.fit,
        stack_reasons=[str(r) for r in report.stack.reasons],
        rank=report.rank.score if report.rank else None,
        rank_parts=report.rank.parts if report.rank else {},
        why=report.rank.why if report.rank else "",
        frameworks=report.frameworks,
        domains=report.domains,
        checklist=coach.checklist(
            report.repo, report.flags, discussion_first=report.difficulty.discussion_first
        ),
    )


def pull_out(row: TrackedPullRequest) -> PullOut:
    return PullOut(
        repo=row.repo_full_name,
        number=row.number,
        title=row.title,
        url=row.url,
        status=row.status,
        status_label=PullRequestStatus(row.status).label,
        needs_you=row.needs_you,
        reasons=list(row.reasons),
        nudge=row.nudge,
        draft=row.draft,
        days_quiet=row.days_quiet,
        opened_at=row.opened_at,
        closed_at=row.closed_at,
        timeline=list(row.timeline),
    )


def _enum_list(values: list[str] | None, kind: type) -> list[Any]:
    out = []
    for value in values or []:
        try:
            out.append(kind(value))
        except ValueError as exc:
            raise HTTPException(422, f"Unknown value '{value}'") from exc
    return out


def insights(db: Database, now: datetime) -> InsightsOut:
    rows = tracked(db)
    merged = [r for r in rows if r.status == PullRequestStatus.MERGED.value]
    closed = [r for r in rows if r.status == PullRequestStatus.CLOSED_UNMERGED.value]
    waits = []
    for r in rows:
        reviewed, opened = as_utc(r.first_review_at), as_utc(r.opened_at)
        if reviewed is not None and opened is not None:
            waits.append((reviewed - opened).total_seconds() / 3600)
    months: dict[str, dict[str, Any]] = {}
    for row in rows:
        opened = as_utc(row.opened_at)
        if opened is None or now - opened > timedelta(days=365):
            continue
        key = opened.strftime("%Y-%m")
        bucket = months.setdefault(key, {"month": key, "opened": 0, "merged": 0})
        bucket["opened"] += 1
        bucket["merged"] += row.status == PullRequestStatus.MERGED.value
    decided = len(merged) + len(closed)
    return InsightsOut(
        opened=len(rows),
        merged=len(merged),
        closed_unmerged=len(closed),
        open_now=sum(1 for r in rows if r.state == "open"),
        merge_rate=len(merged) / decided if decided else None,
        median_hours_to_first_review=statistics.median(waits) if waits else None,
        by_month=[months[k] for k in sorted(months)],
    )


# -------------------------------------------------------------------- app


def create_app(
    db: Database,
    settings: Settings,
    rules: dict[str, RepoRules],
    *,
    file_profile: SkillProfile | None = None,
    demo: bool = False,
    token_configured: bool = False,
    web_dist: Path | None = None,
) -> FastAPI:
    app = FastAPI(
        title=f"{BRAND.name} API",
        version=__version__,
        description="Local, read-only toward GitHub. Writes go only to your own database.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    def radar() -> Radar:
        return Radar(db, settings, rules, profile_store.load(db) or file_profile)

    def find_report(repo: str, number: int) -> IssueReport:
        report = radar().report_for(repo, number)
        if report is None:
            raise HTTPException(404, f"{repo}#{number} is not in the database. Sync it first.")
        return report

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """For container health checks: the API is up and the database answers."""
        with db.sessions() as session:
            session.execute(select(func.count()).select_from(Watchlist))
        return {"status": "ok", "version": __version__}

    @app.get("/api/meta", response_model=Meta)
    def meta() -> Meta:
        return Meta(
            name=BRAND.name,
            version=__version__,
            tagline=BRAND.tagline,
            demo=demo,
            token_configured=token_configured,
        )

    @app.get("/api/issues", response_model=list[IssueOut])
    def issues(
        level: Annotated[list[str] | None, Query()] = None,
        language: Annotated[list[str] | None, Query()] = None,
        framework: Annotated[list[str] | None, Query()] = None,
        domain: Annotated[list[str] | None, Query()] = None,
        type: Annotated[list[str] | None, Query()] = None,
        time: Annotated[list[str] | None, Query()] = None,
        min_health: int | None = None,
        min_stars: int | None = None,
        max_stars: int | None = None,
        updated_within: int | None = None,
        max_comments: int | None = None,
        no_discussion: bool = False,
        repo: Annotated[list[str] | None, Query()] = None,
        all: bool = False,
        limit: int = 200,
    ) -> list[IssueOut]:
        filters = Filters(
            tiers=_enum_list(level, Tier),
            languages=language or [],
            frameworks=framework or [],
            domains=domain or [],
            issue_types=_enum_list(type, IssueType),
            times=_enum_list(time, TimeBucket),
            min_health=min_health,
            min_stars=min_stars,
            max_stars=max_stars,
            max_age_days=updated_within,
            max_comments=max_comments,
            exclude_discussion_first=no_discussion,
            repos=repo or [],
            include_unavailable=all,
        )
        return [issue_out(r, settings) for r in radar().find(filters, limit)]

    @app.get("/api/issues/{owner}/{name}/{number}", response_model=IssueOut)
    def issue(owner: str, name: str, number: int) -> IssueOut:
        return issue_out(find_report(f"{owner}/{name}", number), settings)

    @app.post("/api/issues/{owner}/{name}/{number}/dismiss", status_code=204)
    def dismiss(owner: str, name: str, number: int) -> None:
        mark(db, issue_key(f"{owner}/{name}", number), "dismissed")

    @app.post("/api/issues/{owner}/{name}/{number}/snooze", status_code=204)
    def snooze(owner: str, name: str, number: int, body: SnoozeIn) -> None:
        until = utcnow() + timedelta(days=max(1, body.days))
        mark(db, issue_key(f"{owner}/{name}", number), "snoozed", until=until)

    @app.post("/api/issues/{owner}/{name}/{number}/feedback", status_code=204)
    def feedback(owner: str, name: str, number: int, body: FeedbackIn) -> None:
        with db.sessions.begin() as session:
            repo = session.scalar(select(Repo).where(Repo.full_name.ilike(f"{owner}/{name}")))
            row = session.scalar(
                select(Issue).where(
                    Issue.repo_id == (repo.id if repo else -1), Issue.number == number
                )
            )
            if row is None:
                raise HTTPException(404, "Issue not found")
            session.add(
                DifficultyFeedback(user_id=LOCAL_USER_ID, issue_id=row.id, verdict=body.verdict)
            )

    @app.get("/api/repos", response_model=list[RepoOut])
    def repos() -> list[RepoOut]:
        found = radar().find(Filters())
        free_by_repo: dict[str, int] = {}
        for report in found:
            free_by_repo[report.repo] = free_by_repo.get(report.repo, 0) + 1
        out = []
        with db.sessions() as session:
            watched = select(Watchlist.repo_full_name).where(Watchlist.user_id == LOCAL_USER_ID)
            for repo in session.scalars(
                select(Repo).where(Repo.full_name.in_(watched)).order_by(Repo.full_name)
            ):
                open_count = (
                    session.scalar(
                        select(func.count())
                        .select_from(Issue)
                        .where(Issue.repo_id == repo.id, Issue.state == "open")
                    )
                    or 0
                )
                health = repo.health or {}
                out.append(
                    RepoOut(
                        full_name=repo.full_name,
                        description=repo.description,
                        language=repo.language,
                        stars=repo.stars,
                        archived=repo.archived,
                        health=health.get("score"),
                        health_parts=health.get("parts", {}),
                        health_reasons=health.get("reasons", []),
                        open_issues=open_count,
                        free_issues=free_by_repo.get(repo.full_name, 0),
                        last_synced_at=repo.last_synced_at,
                        pushed_at=repo.pushed_at,
                        sync_error=repo.sync_error,
                    )
                )
        return out

    @app.get("/api/prs", response_model=list[PullOut])
    def prs() -> list[PullOut]:
        return [pull_out(r) for r in tracked(db)]

    @app.get("/api/insights", response_model=InsightsOut)
    def get_insights() -> InsightsOut:
        return insights(db, utcnow())

    @app.get("/api/digest", response_model=DigestOut)
    def digest_preview() -> DigestOut:
        built = DigestBuilder(db, settings, radar()).build()
        return DigestOut(
            title=built.title,
            markdown=digest_render.markdown(built),
            html=digest_render.html(built),
            items=len(built.items),
        )

    @app.get("/api/settings", response_model=SettingsOut)
    def get_settings() -> SettingsOut:
        with db.sessions() as session:
            run = session.scalar(select(SyncRun).order_by(SyncRun.id.desc()))
            last = (
                None
                if run is None
                else {
                    "status": run.status,
                    "started_at": run.started_at,
                    "finished_at": run.finished_at,
                    "requests": run.requests,
                    "not_modified": run.not_modified,
                    "repos_done": len(run.repos_done),
                    "repos_failed": len(run.repos_failed),
                }
            )
        channels = settings.digest.channels
        return SettingsOut(
            token_configured=token_configured,
            database=db.url.split("///")[-1] if db.url.startswith("sqlite") else "database",
            last_sync=last,
            channels={
                name: getattr(channels, name).enabled
                for name in ("markdown", "rss", "email", "telegram", "discord", "slack")
            },
            limits={
                "rest_per_hour": settings.github.rest.authenticated_per_hour,
                "graphql_points_per_hour": settings.github.graphql.points_per_hour,
                "search_per_minute": settings.github.search.requests_per_minute,
                "safety_margin": settings.github.budget.safety_margin,
            },
            weights=settings.ranking.weights.model_dump(),
        )

    @app.get("/api/profile", response_model=ProfileIO)
    def get_profile() -> ProfileIO:
        current = profile_store.load(db) or file_profile or SkillProfile()
        return ProfileIO.model_validate(current.model_dump())

    @app.put("/api/profile", response_model=ProfileIO)
    def put_profile(body: ProfileIO) -> ProfileIO:
        profile_store.save(db, SkillProfile.model_validate(body.model_dump()))
        return body

    @app.get("/api/views", response_model=list[SavedView])
    def get_views() -> list[SavedView]:
        return [SavedView.model_validate(v) for v in profile_store.views(db)]

    @app.put("/api/views", response_model=list[SavedView])
    def put_views(body: list[SavedView]) -> list[SavedView]:
        profile_store.save_views(db, [v.model_dump() for v in body])
        return body

    if web_dist is not None and (web_dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = (web_dist / path).resolve()
            if path and candidate.is_file() and web_dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(web_dist / "index.html")

    return app
