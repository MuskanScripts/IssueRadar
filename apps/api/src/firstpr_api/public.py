"""Pages for people who are not signed in: live numbers, the stack picker,
Trending, issue previews, public profiles and the sitemap.

Everything is read-only, cached in Redis for a few minutes and rate-limited per
IP address. Only public data is shown: catalogue issues, and profiles whose
owner switched them to public.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from typing import Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api.deps import get_db, get_redis
from firstpr_platform import picks, progress
from firstpr_platform.analytics import FROM_BROWSER
from firstpr_platform.db import (
    ACTIVE,
    CatalogueRepo,
    IssueCard,
    Profile,
    Reservation,
    TrackedPull,
    User,
    UserSkill,
    Workspace,
    utcnow,
)
from issueradar.engine.stack import SkillProfile
from issueradar.models import Availability, Tier, TimeBucket

router = APIRouter(prefix="/public")

CACHE_PREFIX = "firstpr:public:"
CACHE_SECONDS = 300
PAGE_CACHE_SECONDS = 3600
LIMIT_PREFIX = "firstpr:ratelimit:public:"
REQUESTS_PER_MINUTE = 120

T = TypeVar("T", bound=BaseModel)


async def rate_limit(request: Request, redis: Redis = Depends(get_redis)) -> None:  # noqa: B008
    ip = request.client.host if request.client else "unknown"
    key = f"{LIMIT_PREFIX}{ip}:{int(utcnow().timestamp() // 60)}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 120)
    if count > REQUESTS_PER_MINUTE:
        raise HTTPException(429, "Too many requests. Try again in a minute.")


async def cached(
    redis: Redis, key: str, model: type[T], make: Callable[[], Awaitable[T]], seconds: int
) -> T:
    raw = await redis.get(CACHE_PREFIX + key)
    if raw:
        return model.model_validate_json(raw)
    value = await make()
    await redis.set(CACHE_PREFIX + key, value.model_dump_json(), ex=seconds)
    return value


class Stats(BaseModel):
    free_issues: int
    repos: int
    people: int
    merged_this_week: int
    merged_total: int


class PublicIssue(BaseModel):
    repo: str
    number: int
    title: str
    language: str | None
    tier: str
    time_label: str
    labels: list[str]
    health: int | None
    comments: int
    updated_at: datetime | None
    why_free: str | None


class IssueList(BaseModel):
    items: list[PublicIssue]


class IssuePreview(PublicIssue):
    repo_description: str | None
    availability: str
    availability_label: str
    url: str | None
    checklist: list[str]
    difficulty_reasons: list[str]
    health_reasons: list[str]


class MergedItem(BaseModel):
    repo: str
    number: int
    title: str
    url: str | None
    merged_at: datetime | None
    # Only for people with a public profile.
    handle: str | None


class RepoItem(BaseModel):
    repo: str
    description: str | None
    language: str | None
    free_issues: int
    health: int | None


class Trending(BaseModel):
    tab: str
    issues: list[PublicIssue]
    repos: list[RepoItem]
    merged: list[MergedItem]


class PublicDay(BaseModel):
    day: date
    minutes: int
    green: bool


class PublicProfile(BaseModel):
    handle: str
    name: str | None
    avatar_url: str | None
    xp: int
    streak: int
    best_streak: int
    merged: int
    repos: int
    badges: list[str]
    skills: list[str]
    calendar: list[PublicDay]
    merged_pulls: list[MergedItem]


class SitemapEntry(BaseModel):
    path: str
    updated_at: datetime | None


class Sitemap(BaseModel):
    entries: list[SitemapEntry]


def _issue(card: IssueCard) -> PublicIssue:
    return PublicIssue(
        repo=card.repo_full_name,
        number=card.number,
        title=card.title,
        language=card.language,
        tier=card.tier,
        time_label=TimeBucket(card.time_bucket).label,
        labels=list(card.labels)[:5],
        health=card.health,
        comments=card.comments,
        updated_at=card.updated_at,
        why_free=card.availability_reasons[0] if card.availability_reasons else None,
    )


async def _open_cards(db: AsyncSession, stack: str | None, level: Tier) -> list[IssueCard]:
    """Free issues nobody holds, best first for a newcomer in this stack."""
    skills = SkillProfile.model_validate({"languages": {stack: "medium"}}) if stack else None
    taste = picks.Taste(level=level, skills=skills)
    ranked = await picks.ranked(db, 0, taste, utcnow())
    cards = [card for card, _ in ranked]
    if stack:
        cards = [
            c
            for c in cards
            if stack in {x.lower() for x in c.languages} or (c.language or "").lower() == stack
        ]
    return cards


async def _merged(db: AsyncSession, since: datetime | None, limit: int) -> list[MergedItem]:
    """Pull requests merged through FirstPR (they come from a workspace)."""
    query = (
        select(TrackedPull, User.handle, Profile.public)
        .join(User, User.id == TrackedPull.user_id)
        .outerjoin(Profile, Profile.user_id == TrackedPull.user_id)
        .join(
            Workspace,
            (Workspace.user_id == TrackedPull.user_id)
            & (func.lower(Workspace.repo_full_name) == func.lower(TrackedPull.repo_full_name))
            & (Workspace.pr_number == TrackedPull.number),
        )
        .where(TrackedPull.merged.is_(True))
        .order_by(TrackedPull.closed_at.desc())
        .limit(limit)
    )
    if since is not None:
        query = query.where(TrackedPull.closed_at >= since)
    rows = (await db.execute(query)).all()
    return [
        MergedItem(
            repo=pull.repo_full_name,
            number=pull.number,
            title=pull.title,
            url=pull.url,
            merged_at=pull.closed_at,
            handle=handle if public else None,
        )
        for pull, handle, public in rows
    ]


# ---------------------------------------------------------------- endpoints


@router.get("/stats", response_model=Stats, dependencies=[Depends(rate_limit)])
async def stats(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> Stats:
    async def make() -> Stats:
        week = utcnow() - timedelta(days=7)
        free = await db.scalar(
            select(func.count(IssueCard.id)).where(IssueCard.availability.in_(picks.OPEN_STATES))
        )
        merged_week = len(await _merged(db, week, 10_000))
        merged_all = len(await _merged(db, None, 100_000))
        return Stats(
            free_issues=free or 0,
            repos=await db.scalar(select(func.count()).select_from(CatalogueRepo)) or 0,
            people=await db.scalar(select(func.count()).select_from(User)) or 0,
            merged_this_week=merged_week,
            merged_total=merged_all,
        )

    return await cached(redis, "stats", Stats, make, CACHE_SECONDS)


@router.get("/issues", response_model=IssueList, dependencies=[Depends(rate_limit)])
async def stack_picker(
    stack: Literal["python", "typescript", "javascript", "java", "go", "rust"] = "python",
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> IssueList:
    """The intro page's stack picker: the best four beginner issues in one stack."""

    async def make() -> IssueList:
        cards = await _open_cards(db, stack, Tier.BEGINNER)
        return IssueList(items=[_issue(c) for c in cards[:4]])

    return await cached(redis, f"issues:{stack}", IssueList, make, CACHE_SECONDS)


@router.get("/trending", response_model=Trending, dependencies=[Depends(rate_limit)])
async def trending(
    tab: Literal["fresh", "beginner", "repos", "merged"] = "fresh",
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> Trending:
    async def make() -> Trending:
        out = Trending(tab=tab, issues=[], repos=[], merged=[])
        if tab == "fresh":
            cards = await _open_cards(db, None, Tier.BEGINNER)
            cards.sort(key=lambda c: c.opened_at.timestamp() if c.opened_at else 0, reverse=True)
            out.issues = [_issue(c) for c in cards[:20]]
        elif tab == "beginner":
            cards = [c for c in await _open_cards(db, None, Tier.BEGINNER) if c.tier == "beginner"]
            out.issues = [_issue(c) for c in cards[:20]]
        elif tab == "repos":
            rows = await db.execute(
                select(
                    IssueCard.repo_full_name,
                    func.max(IssueCard.repo_description),
                    func.max(IssueCard.language),
                    func.count(IssueCard.id),
                    func.max(IssueCard.health),
                )
                .where(IssueCard.availability.in_(picks.OPEN_STATES))
                .group_by(IssueCard.repo_full_name)
                .order_by(func.max(IssueCard.health).desc(), func.count(IssueCard.id).desc())
                .limit(20)
            )
            out.repos = [
                RepoItem(repo=r, description=d, language=lang, free_issues=n, health=h)
                for r, d, lang, n, h in rows.all()
            ]
        else:
            out.merged = await _merged(db, utcnow() - timedelta(days=7), 20)
        return out

    return await cached(redis, f"trending:{tab}", Trending, make, CACHE_SECONDS)


@router.get(
    "/issues/{owner}/{name}/{number}",
    response_model=IssuePreview,
    dependencies=[Depends(rate_limit)],
)
async def issue_preview(
    owner: str,
    name: str,
    number: int,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> IssuePreview:
    card = await db.scalar(
        select(IssueCard).where(
            func.lower(IssueCard.repo_full_name) == f"{owner}/{name}".lower(),
            IssueCard.number == number,
        )
    )
    if card is None:
        raise HTTPException(404, "We do not track this issue, or it was closed.")
    held = await db.scalar(
        select(Reservation.id).where(Reservation.card_id == card.id, Reservation.status == ACTIVE)
    )
    state = Availability(card.availability)
    label = "Someone is working on it" if held else state.label
    return IssuePreview(
        **_issue(card).model_dump(),
        repo_description=card.repo_description,
        availability="held" if held else card.availability,
        availability_label=label,
        url=card.url,
        checklist=list(card.checklist),
        difficulty_reasons=list(card.difficulty_reasons),
        health_reasons=list(card.health_reasons),
    )


@router.get("/profiles/{handle}", response_model=PublicProfile, dependencies=[Depends(rate_limit)])
async def public_profile(
    handle: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PublicProfile:
    user = await db.scalar(select(User).where(func.lower(User.handle) == handle.lower()))
    profile = await db.get(Profile, user.id) if user else None
    if user is None or profile is None or not profile.public:
        # The same answer for "no such person" and "private", so nothing leaks.
        raise HTTPException(404, "No public profile here.")
    taste = await picks.load_taste(db, user.id)
    today = picks.local_day(taste, utcnow())
    known = await progress.days(db, user.id, today - timedelta(days=400), today)
    streak = progress.streak(known, today)
    first = today - timedelta(days=today.weekday()) - timedelta(weeks=52)
    calendar = []
    d = first
    while d <= today:
        item = known.get(d, progress.Day(d))
        calendar.append(PublicDay(day=d, minutes=item.minutes, green=item.green))
        d += timedelta(days=1)
    merged_rows = list(
        await db.scalars(
            select(TrackedPull)
            .where(TrackedPull.user_id == user.id, TrackedPull.merged.is_(True))
            .order_by(TrackedPull.closed_at.desc())
        )
    )
    earned = await progress.earned(db, user.id)
    skills = await db.scalars(select(UserSkill.name).where(UserSkill.user_id == user.id))
    return PublicProfile(
        handle=user.handle,
        name=user.name,
        avatar_url=user.avatar_url,
        xp=user.xp,
        streak=streak.current,
        best_streak=streak.best,
        merged=len(merged_rows),
        repos=len({p.repo_full_name.lower() for p in merged_rows}),
        badges=[b.name for b in progress.BADGES if b.key in earned],
        skills=sorted(set(skills)),
        calendar=calendar,
        merged_pulls=[
            MergedItem(
                repo=p.repo_full_name,
                number=p.number,
                title=p.title,
                url=p.url,
                merged_at=p.closed_at,
                handle=user.handle,
            )
            for p in merged_rows[:20]
        ],
    )


@router.get("/sitemap", response_model=Sitemap, dependencies=[Depends(rate_limit)])
async def sitemap(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> Sitemap:
    async def make() -> Sitemap:
        entries = [
            SitemapEntry(path="/", updated_at=None),
            SitemapEntry(path="/trending", updated_at=None),
        ]
        cards = await db.scalars(
            select(IssueCard)
            .where(IssueCard.availability.in_(picks.OPEN_STATES))
            .order_by(IssueCard.updated_at.desc())
            .limit(1000)
        )
        entries += [
            SitemapEntry(path=f"/i/{c.repo_full_name}/{c.number}", updated_at=c.updated_at)
            for c in cards
        ]
        handles = await db.scalars(
            select(User.handle)
            .join(Profile, Profile.user_id == User.id)
            .where(Profile.public.is_(True))
        )
        entries += [SitemapEntry(path=f"/u/{h}", updated_at=None) for h in handles]
        return Sitemap(entries=entries)

    return await cached(redis, "sitemap", Sitemap, make, PAGE_CACHE_SECONDS)


class EventIn(BaseModel):
    event: str
    anonymous_id: str
    properties: dict[str, str] = {}


@router.post("/events", status_code=204, dependencies=[Depends(rate_limit)])
async def browser_event(body: EventIn, request: Request) -> None:
    """Funnel events from the public pages, passed on to PostHog (if it is set up)."""
    if body.event not in FROM_BROWSER or not 8 <= len(body.anonymous_id) <= 64:
        raise HTTPException(422, "Unknown event")
    props = {k[:40]: v[:200] for k, v in list(body.properties.items())[:10]}
    await request.app.state.analytics.capture(body.event, body.anonymous_id, props)
