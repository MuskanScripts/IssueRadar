"""Today's pick, Explore, the issue page, Refresh, and logging what people do.

Everything here reads the issue cards the worker writes after each sync, and
works out fit for the signed-in user on top of them (firstpr_platform.picks).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api.deps import (
    Jobs,
    current_user,
    get_db,
    get_jobs,
    get_redis,
    get_settings,
    require_csrf,
)
from firstpr_api.settings import Settings
from firstpr_platform import accounts, picks, plan
from firstpr_platform.db import ACTIVE, IssueCard, Reservation, User, utcnow
from firstpr_platform.github_oauth import GitHubAuthError
from issueradar.models import Availability, TimeBucket

router = APIRouter()

REFRESH_PREFIX = "firstpr:refresh:"
LIVE_PREFIX = "firstpr:live:"
PAGE_SIZE = 20


class IssueOut(BaseModel):
    repo: str
    number: int
    title: str
    url: str | None
    labels: list[str]
    language: str | None
    tier: str
    time_bucket: str
    time_label: str
    issue_type: str
    availability: str
    availability_label: str
    comments: int
    stars: int
    health: int | None
    updated_at: datetime | None
    changed_at: datetime
    fit: int | None
    why: list[str]
    held_by_you: bool


class Live(BaseModel):
    checked_at: datetime
    open: bool
    assignees: list[str]
    comments: int
    note: str | None


class IssueDetail(IssueOut):
    repo_description: str | None
    availability_reasons: list[str]
    difficulty_reasons: list[str]
    discussion_first: bool
    health_reasons: list[str]
    checklist: list[str]
    repo_notes: str | None
    refreshed_at: datetime
    held_until: datetime | None
    live: Live | None


class Today(BaseModel):
    day: str
    pick: IssueOut | None
    held_until: datetime | None
    swaps_left: int
    # Why there is no pick, in words people understand.
    empty_reason: str | None


class Page(BaseModel):
    items: list[IssueOut]
    next_cursor: str | None
    total: int
    seed: str


class RefreshState(BaseModel):
    requested_at: datetime | None
    next_allowed_at: datetime | None
    data_updated_at: datetime | None


class Changes(BaseModel):
    since: datetime
    new_activity: int
    now_taken: int
    data_updated_at: datetime | None


class EventIn(BaseModel):
    repo: str
    number: int
    surface: Literal["daily", "explore", "issue"]
    action: Literal["opened", "github"]


def _out(card: IssueCard, result: picks.Fit | None, held: bool) -> dict[str, Any]:
    return {
        "repo": card.repo_full_name,
        "number": card.number,
        "title": card.title,
        "url": card.url,
        "labels": list(card.labels),
        "language": card.language,
        "tier": card.tier,
        "time_bucket": card.time_bucket,
        "time_label": TimeBucket(card.time_bucket).label,
        "issue_type": card.issue_type,
        "availability": card.availability,
        "availability_label": Availability(card.availability).label,
        "comments": card.comments,
        "stars": card.stars,
        "health": card.health,
        "updated_at": card.updated_at,
        "changed_at": card.changed_at,
        "fit": result.percent if result else None,
        "why": result.why if result else list(card.availability_reasons[:1]),
        "held_by_you": held,
    }


def issue_out(card: IssueCard, result: picks.Fit | None, held: bool = False) -> IssueOut:
    return IssueOut(**_out(card, result, held))


# ------------------------------------------------------------------ today


async def _today(db: AsyncSession, user: User, hold: Reservation | None) -> Today:
    now = utcnow()
    taste = await picks.load_taste(db, user.id)
    day = picks.local_day(taste, now).isoformat()
    swaps_left = max(0, picks.SWAPS_PER_DAY - await picks.swaps_today(db, user.id, day))
    if hold is None:
        any_cards = await db.scalar(select(func.count()).select_from(IssueCard))
        reason = (
            "Nothing is left that fits you today. Try Explore, or come back tomorrow."
            if any_cards
            else "The first sync has not finished yet. Your pick appears once issues are in."
        )
        return Today(
            day=day, pick=None, held_until=None, swaps_left=swaps_left, empty_reason=reason
        )
    return Today(
        day=day,
        pick=issue_out(hold.card, picks.fit(hold.card, taste, now), held=True),
        held_until=hold.expires_at,
        swaps_left=swaps_left,
        empty_reason=None,
    )


@router.get("/me/today", response_model=Today)
async def today(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Today:
    return await _today(db, user, await picks.todays_pick(db, user.id))


@router.post("/me/today/another", response_model=Today, dependencies=[Depends(require_csrf)])
async def another(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Today:
    try:
        hold = await picks.show_another(db, user.id)
    except picks.SwapLimitReached:
        raise HTTPException(
            429, f"You can ask for another pick {picks.SWAPS_PER_DAY} times a day."
        ) from None
    return await _today(db, user, hold)


# ---------------------------------------------------------------- explore


def _encode(key: list[Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode(cursor: str) -> list[Any]:
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except ValueError:
        raise HTTPException(422, "Bad cursor") from None
    if not isinstance(value, list) or len(value) != 2:
        raise HTTPException(422, "Bad cursor")
    return value


def _skill_match(card: IssueCard, skill: str) -> bool:
    skill = skill.lower()
    names = {*card.languages, *card.frameworks, *card.domains}
    return skill in {n.lower() for n in names} or (card.language or "").lower() == skill


@router.get("/issues", response_model=Page)
async def explore(
    level: Literal["beginner", "intermediate", "pro"] | None = None,
    skill: str | None = None,
    language: str | None = None,
    fresh: int | None = Query(default=None, ge=1, le=365),
    sort: Literal["fit", "newest", "shuffle"] = "fit",
    seed: str | None = Query(default=None, max_length=40),
    cursor: str | None = None,
    limit: int = Query(default=PAGE_SIZE, ge=1, le=50),
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Page:
    now = utcnow()
    taste = await picks.load_taste(db, user.id)
    # Explore covers the whole catalogue and the user's own repos, not only their packs.
    everything = picks.Taste(level=taste.level, skills=taste.skills, timezone=taste.timezone)
    rows = await picks.ranked(db, user.id, everything, now)
    mine = set(
        await db.scalars(
            select(Reservation.card_id).where(
                Reservation.user_id == user.id, Reservation.status == ACTIVE
            )
        )
    )
    oldest = now - timedelta(days=fresh) if fresh else None
    kept = [
        (card, result)
        for card, result in rows
        if (level is None or card.tier == level)
        and (skill is None or _skill_match(card, skill))
        and (language is None or (card.language or "").lower() == language.lower())
        and (oldest is None or (card.updated_at is not None and card.updated_at >= oldest))
    ]
    seed = seed or "default"

    def key(pair: tuple[IssueCard, picks.Fit]) -> list[Any]:
        card, result = pair
        if sort == "newest":
            stamp = card.updated_at.timestamp() if card.updated_at else 0.0
            return [-stamp, card.id]
        if sort == "shuffle":
            return [picks.shuffle_key(seed, card.id), card.id]
        return [-result.score, card.id]

    kept.sort(key=key)
    start = 0
    if cursor:
        after = _decode(cursor)
        start = next((i for i, pair in enumerate(kept) if key(pair) > after), len(kept))
    page = kept[start : start + limit]
    more = start + limit < len(kept)
    return Page(
        items=[issue_out(card, result, card.id in mine) for card, result in page],
        next_cursor=_encode(key(page[-1])) if page and more else None,
        total=len(kept),
        seed=seed,
    )


async def _pool_cards(db: AsyncSession, user: User) -> Any:
    taste = await picks.load_taste(db, user.id)
    names = await picks.pool(db, user.id, picks.Taste(level=taste.level))
    return func.lower(IssueCard.repo_full_name).in_(names)


@router.get("/issues/changes", response_model=Changes)
async def changes(
    since: datetime,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Changes:
    in_pool = await _pool_cards(db, user)
    rows = await db.execute(
        select(IssueCard.availability, func.count())
        .where(in_pool, IssueCard.changed_at > since)
        .group_by(IssueCard.availability)
    )
    counts: dict[str, int] = {state: n for state, n in rows.all()}
    open_now = sum(n for state, n in counts.items() if state in picks.OPEN_STATES)
    return Changes(
        since=since,
        new_activity=open_now,
        now_taken=sum(counts.values()) - open_now,
        data_updated_at=await db.scalar(select(func.max(IssueCard.refreshed_at)).where(in_pool)),
    )


# ---------------------------------------------------------------- refresh


async def _refresh_state(db: AsyncSession, redis: Redis, user: User) -> RefreshState:
    key = f"{REFRESH_PREFIX}user:{user.id}"
    raw = await redis.get(key)
    ttl = await redis.ttl(key)
    requested = (
        datetime.fromisoformat(raw.decode() if isinstance(raw, bytes) else raw) if raw else None
    )
    in_pool = await _pool_cards(db, user)
    return RefreshState(
        requested_at=requested,
        next_allowed_at=utcnow() + timedelta(seconds=ttl) if raw and ttl > 0 else None,
        data_updated_at=await db.scalar(select(func.max(IssueCard.refreshed_at)).where(in_pool)),
    )


@router.get("/me/refresh", response_model=RefreshState)
async def refresh_state(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> RefreshState:
    return await _refresh_state(db, redis, user)


@router.post("/me/refresh", response_model=RefreshState, dependencies=[Depends(require_csrf)])
async def refresh(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
    jobs: Jobs = Depends(get_jobs),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> RefreshState:
    every = settings.refresh_every_seconds
    now = utcnow()
    if not await redis.set(f"{REFRESH_PREFIX}user:{user.id}", now.isoformat(), nx=True, ex=every):
        wait = max(1, await redis.ttl(f"{REFRESH_PREFIX}user:{user.id}"))
        minutes = (wait + 59) // 60
        raise HTTPException(429, f"You refreshed a moment ago. Try again in {minutes} min.")
    sync_plan = await plan.build(db)
    if sync_plan.by_user.get(user.id):
        # Repos only this user watches, with their own token.
        await jobs.enqueue_job("sync_user", user.id, _job_id=f"sync-user:{user.id}")
    # The shared catalogue at most once per interval, whoever asks.
    if await redis.set(f"{REFRESH_PREFIX}catalogue", now.isoformat(), nx=True, ex=every):
        await jobs.enqueue_job("sync_catalogue", _job_id="sync-catalogue")
    return await _refresh_state(db, redis, user)


# -------------------------------------------------------------- issue page


async def _live(
    request: Request,
    db: AsyncSession,
    redis: Redis,
    user: User,
    card: IssueCard,
    settings: Settings,
) -> Live | None:
    """The issue as GitHub has it now, when our copy is older than a few minutes."""
    if utcnow() - card.refreshed_at < timedelta(seconds=settings.live_after_seconds):
        return None
    key = f"{LIVE_PREFIX}{card.repo_full_name.lower()}#{card.number}"
    cached = await redis.get(key)
    if cached:
        return Live.model_validate_json(cached)
    oauth, box = request.app.state.oauth, request.app.state.token_box
    if oauth is None or box is None:
        return None
    token = await accounts.usable_token(db, user.github, box, oauth)
    if token is None:
        return None
    try:
        data = await oauth.get_issue(token, card.repo_full_name, card.number)
    except GitHubAuthError:
        await accounts.mark_reconnect(db, user.github)
        return None
    except httpx.HTTPError:
        return None
    if data is None:
        live = Live(
            checked_at=utcnow(),
            open=False,
            assignees=[],
            comments=card.comments,
            note="This issue is gone from GitHub.",
        )
    else:
        is_open = data.get("state") == "open"
        assignees = [a["login"] for a in data.get("assignees") or [] if a.get("login")]
        comments = int(data.get("comments") or 0)
        note = None
        if not is_open:
            note = "Closed on GitHub since our last sync."
        elif assignees:
            note = "Assigned to " + ", ".join(f"@{a}" for a in assignees) + " since our last sync."
        elif comments > card.comments:
            new = comments - card.comments
            note = (
                f"{new} new comment{'s' if new != 1 else ''} since our last sync. Read them first."
            )
        live = Live(
            checked_at=utcnow(), open=is_open, assignees=assignees, comments=comments, note=note
        )
    await redis.set(key, live.model_dump_json(), ex=settings.live_after_seconds)
    return live


@router.get("/issues/{owner}/{name}/{number}", response_model=IssueDetail)
async def issue_page(
    owner: str,
    name: str,
    number: int,
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> IssueDetail:
    card = await db.scalar(
        select(IssueCard).where(
            func.lower(IssueCard.repo_full_name) == f"{owner}/{name}".lower(),
            IssueCard.number == number,
        )
    )
    if card is None:
        raise HTTPException(404, "We do not track this issue, or it was closed.")
    taste = await picks.load_taste(db, user.id)
    hold = await db.scalar(
        select(Reservation).where(Reservation.card_id == card.id, Reservation.status == ACTIVE)
    )
    held_by_you = hold is not None and hold.user_id == user.id
    result = picks.fit(card, taste, utcnow())
    live = await _live(request, db, redis, user, card, settings)
    base = _out(card, result, held_by_you)
    if hold is not None and not held_by_you:
        base["why"] = ["Someone else is trying this issue for the next two days."]
    if live is not None and (not live.open or live.assignees):
        # GitHub is newer than our copy: do not offer an issue that is taken or closed.
        base.update(
            availability="closed" if not live.open else Availability.CLAIMED.value,
            availability_label="Closed" if not live.open else Availability.CLAIMED.label,
            fit=None,
            why=[live.note] if live.note else [],
        )
    return IssueDetail(
        **base,
        repo_description=card.repo_description,
        availability_reasons=list(card.availability_reasons),
        difficulty_reasons=list(card.difficulty_reasons),
        discussion_first=card.discussion_first,
        health_reasons=list(card.health_reasons),
        checklist=list(card.checklist),
        repo_notes=card.repo_notes,
        refreshed_at=card.refreshed_at,
        held_until=hold.expires_at if held_by_you and hold else None,
        live=live,
    )


@router.post("/me/events", status_code=204, dependencies=[Depends(require_csrf)])
async def record_event(
    body: EventIn,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> None:
    card = await db.scalar(
        select(IssueCard).where(
            func.lower(IssueCard.repo_full_name) == body.repo.lower(),
            IssueCard.number == body.number,
        )
    )
    if card is None:
        return
    taste = await picks.load_taste(db, user.id)
    await picks.log(db, user.id, card, body.surface, body.action, picks.fit(card, taste, utcnow()))
    await db.commit()
