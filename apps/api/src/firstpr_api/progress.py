"""Activity heartbeats, and the numbers behind Progress, Home and Profile.

The web page sends a heartbeat once a minute, but only while its tab is visible
and the user did something in the last 2 minutes; the API checks both again and
counts at most one minute per 55 seconds. Minutes are counted in Redis under the
user's own calendar day and moved to the database by the worker every 10 minutes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api.deps import current_user, get_db, get_redis, require_csrf
from firstpr_platform import picks, progress, workspaces
from firstpr_platform.db import Profile, TrackedPull, User, Workspace, XpTransaction, utcnow

router = APIRouter()

# Must match ACTIVITY_PREFIX and ACTIVITY_DIRTY in apps/worker.
ACTIVITY_PREFIX = "firstpr:activity:"
ACTIVITY_DIRTY = "firstpr:activity:dirty"
BEAT_PREFIX = "firstpr:beat:"
BEAT_EVERY_SECONDS = 55
IDLE_LIMIT_SECONDS = 120


class BeatIn(BaseModel):
    visible: bool
    # Seconds since the last key press, click, scroll or touch on the page.
    idle_seconds: int = Field(ge=0)


class BeatOut(BaseModel):
    counted: bool
    today_minutes: int


class DayOut(BaseModel):
    day: date
    minutes: int
    web_minutes: int
    codespace_minutes: int
    commits: int
    green: bool
    frozen: bool


class StreakOut(BaseModel):
    current: int
    best: int
    freeze_left_this_week: bool


class BadgeOut(BaseModel):
    key: str
    name: str
    description: str
    earned_at: datetime | None


class XpOut(BaseModel):
    amount: int
    note: str
    created_at: datetime


class Stats(BaseModel):
    xp: int
    merged: int
    open_prs: int
    repos: int
    started: int


class ProgressOut(BaseModel):
    today: date
    today_minutes: int
    goal_minutes: int
    streak: StreakOut
    calendar: list[DayOut]
    badges: list[BadgeOut]
    recent_xp: list[XpOut]
    stats: Stats


class VisibilityIn(BaseModel):
    public: bool


async def _today(db: AsyncSession, user: User) -> date:
    return picks.local_day(await picks.load_taste(db, user.id), utcnow())


async def _pending(redis: Redis, user_id: int, day: date) -> int:
    raw = await redis.get(f"{ACTIVITY_PREFIX}{user_id}:{day.isoformat()}")
    return int(raw or 0)


@router.post("/me/heartbeat", response_model=BeatOut, dependencies=[Depends(require_csrf)])
async def heartbeat(
    body: BeatIn,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> BeatOut:
    today = await _today(db, user)
    counted = False
    # A tab in the background, or nobody at the keyboard, earns nothing.
    active = body.visible and body.idle_seconds <= IDLE_LIMIT_SECONDS
    if active and await redis.set(f"{BEAT_PREFIX}{user.id}", "1", nx=True, ex=BEAT_EVERY_SECONDS):
        key = f"{ACTIVITY_PREFIX}{user.id}:{today.isoformat()}"
        await redis.incr(key)
        await redis.expire(key, 3 * 24 * 3600)
        await redis.sadd(ACTIVITY_DIRTY, str(user.id))  # type: ignore[misc]
        counted = True
    stored = await progress.days(db, user.id, today, today)
    minutes = (stored[today].web_minutes if today in stored else 0) + await _pending(
        redis, user.id, today
    )
    return BeatOut(counted=counted, today_minutes=minutes)


@router.get("/me/progress", response_model=ProgressOut)
async def my_progress(
    weeks: int = Query(default=17, ge=1, le=53),
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> ProgressOut:
    today = await _today(db, user)
    # Whole weeks, Monday to Sunday, ending with this week.
    first = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    # The streak looks further back than the calendar shows.
    known = await progress.days(db, user.id, today - timedelta(days=400), today)
    pending = await _pending(redis, user.id, today)
    if pending:
        day = known.setdefault(today, progress.Day(today))
        day.web_minutes += pending
    streak = progress.streak(known, today)
    calendar = []
    d = first
    while d <= today:
        item = known.get(d, progress.Day(d))
        calendar.append(
            DayOut(
                day=d,
                minutes=item.minutes,
                web_minutes=item.web_minutes,
                codespace_minutes=item.codespace_minutes,
                commits=item.commits,
                green=item.green,
                frozen=d in streak.frozen,
            )
        )
        d += timedelta(days=1)

    earned = await progress.earned(db, user.id)
    recent = await db.scalars(
        select(XpTransaction)
        .where(XpTransaction.user_id == user.id)
        .order_by(XpTransaction.id.desc())
        .limit(10)
    )
    merged = (
        await db.execute(
            select(TrackedPull.repo_full_name).where(
                TrackedPull.user_id == user.id, TrackedPull.merged.is_(True)
            )
        )
    ).all()
    started = await db.scalar(select(func.count(Workspace.id)).where(Workspace.user_id == user.id))
    return ProgressOut(
        today=today,
        today_minutes=known[today].minutes if today in known else 0,
        goal_minutes=progress.GREEN_MINUTES,
        streak=StreakOut(
            current=streak.current,
            best=streak.best,
            freeze_left_this_week=streak.freeze_left_this_week,
        ),
        calendar=calendar,
        badges=[
            BadgeOut(
                key=b.key,
                name=b.name,
                description=b.description,
                earned_at=earned[b.key].earned_at if b.key in earned else None,
            )
            for b in progress.BADGES
        ],
        recent_xp=[XpOut(amount=x.amount, note=x.note, created_at=x.created_at) for x in recent],
        stats=Stats(
            xp=user.xp,
            merged=len(merged),
            open_prs=await workspaces.open_prs(db, user.id),
            repos=len({r.lower() for (r,) in merged}),
            started=started or 0,
        ),
    )


@router.put("/me/profile/visibility", dependencies=[Depends(require_csrf)])
async def set_visibility(
    body: VisibilityIn,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, bool]:
    profile = await db.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id, level="beginner", packs=[], timezone="UTC")
        db.add(profile)
    profile.public = body.public
    await db.commit()
    return {"public": profile.public}
