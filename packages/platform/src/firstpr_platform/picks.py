"""How well an issue fits one user, and the daily pick held for them.

Fit reuses the engine's own pieces (packages/core): stack matching against the
user's skills, the tier fit against the level they chose, and the ranking
weights. The issue's side of it was computed by the worker and stored on the
issue card, so working out fit is cheap enough to do on every request.

A daily pick is a hold on one issue for 48 hours. At most one active hold
exists per issue (a unique index), so two people are never sent to the same
issue at the same time.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_platform.db import (
    ACTIVE,
    CatalogueRepo,
    IssueCard,
    Profile,
    RecommendationEvent,
    Reservation,
    UserSkill,
    Watch,
    utcnow,
)
from issueradar.config.settings import Settings, load_settings
from issueradar.engine import ranking, stack
from issueradar.engine.rules import load_packs
from issueradar.models import Availability, Tier, TimeBucket

HOLD = timedelta(hours=48)
SWAPS_PER_DAY = 3
SWAPPED = "swapped"
EXPIRED = "expired"
OPEN_STATES = (Availability.FREE.value, Availability.LIKELY_FREE.value)
SKILL_KINDS = ("languages", "frameworks", "domains")
SKILL_LEVELS = ("learning", "medium", "strong")
WORK = {
    TimeBucket.UNDER_AN_HOUR: "Less than an hour of work",
    TimeBucket.HALF_A_DAY: "About half a day of work",
    TimeBucket.A_WEEKEND: "About a weekend of work",
    TimeBucket.A_WEEK_OR_MORE: "A week or more of work",
}


@lru_cache(maxsize=1)
def engine_settings() -> Settings:
    return load_settings()


@dataclass
class Taste:
    """Everything about one user that fit depends on."""

    level: Tier = Tier.BEGINNER
    skills: stack.SkillProfile | None = None
    packs: list[str] = field(default_factory=list)
    timezone: str = "UTC"


@dataclass
class Fit:
    score: float  # 0 to 1
    parts: dict[str, float]
    why: list[str]

    @property
    def percent(self) -> int:
        return round(self.score * 100)


async def load_taste(db: AsyncSession, user_id: int) -> Taste:
    profile = await db.get(Profile, user_id)
    rows = list(await db.scalars(select(UserSkill).where(UserSkill.user_id == user_id)))
    skills = None
    if rows:
        data: dict[str, dict[str, str]] = {kind: {} for kind in SKILL_KINDS}
        for row in rows:
            data.setdefault(row.kind, {})[row.name] = row.level
        skills = stack.SkillProfile.model_validate(data)
    if profile is None:
        return Taste(skills=skills)
    return Taste(
        level=Tier(profile.level),
        skills=skills,
        packs=list(profile.packs or []),
        timezone=profile.timezone,
    )


def local_day(taste: Taste, now: datetime) -> date:
    try:
        zone = ZoneInfo(taste.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return now.astimezone(zone).date()


def _skill_level(skills: stack.SkillProfile, name: str) -> str | None:
    for kind in SKILL_KINDS:
        level = skills.level(kind, name)
        if level is not None:
            return level
    return None


def fit(card: IssueCard, taste: Taste, now: datetime) -> Fit | None:
    """None when the issue is not open to start (claimed, has a PR, not ready)."""
    settings = engine_settings()
    availability = Availability(card.availability)
    tier = Tier(card.tier)
    repo = stack.RepoStack(
        languages=list(card.languages), frameworks=list(card.frameworks), domains=list(card.domains)
    )
    match = stack.match(repo, list(card.paths), taste.skills, settings.stack)
    tier_fit = stack.tier_fit(tier, taste.level)
    result = ranking.score(
        ranking.RankInputs(
            availability=availability,
            tier=tier,
            tier_fit=tier_fit,
            health=card.health if card.health is not None else 50,
            stack_fit=match.fit,
            updated_at=card.updated_at,
            comments=card.comments,
        ),
        settings.ranking,
        now,
    )
    if result is None:
        return None
    return Fit(result.score, result.parts, _why(card, taste, tier, tier_fit, match, result.parts))


def _why(
    card: IssueCard,
    taste: Taste,
    tier: Tier,
    tier_fit: float,
    match: stack.StackResult,
    parts: dict[str, float],
) -> list[str]:
    why: list[str] = []
    if card.availability_reasons:
        why.append(card.availability_reasons[0])
    if tier_fit >= 1:
        why.append(f"{tier.label} level, the level you chose")
    elif tier_fit > 0:
        direction = "above" if _order(tier) > _order(taste.level) else "below"
        why.append(f"{tier.label} level, one step {direction} the level you chose")
    if taste.skills is not None and match.matched:
        known = [f"{name} ({_skill_level(taste.skills, name)})" for name in match.matched[:3]]
        why.append("Uses what you know: " + ", ".join(known))
    if card.health is not None and card.health >= 70:
        why.append(f"Healthy repo: maintainers reply and merge (health {card.health})")
    if parts["freshness"] >= 0.8:
        why.append("Active in the last week")
    if card.comments == 0:
        why.append("Nobody has commented yet")
    why.append(WORK[TimeBucket(card.time_bucket)])
    return why


def _order(tier: Tier) -> int:
    return [Tier.BEGINNER, Tier.INTERMEDIATE, Tier.PRO].index(tier)


def pack_repos(keys: list[str]) -> set[str]:
    packs = load_packs()
    return {repo.lower() for key in keys if key in packs for repo in packs[key].repos}


async def pool(db: AsyncSession, user_id: int, taste: Taste) -> set[str]:
    """Lower-case names of the repos this user's picks come from."""
    catalogue = {n.lower() for n in await db.scalars(select(CatalogueRepo.full_name))}
    chosen = pack_repos(taste.packs) & catalogue if taste.packs else catalogue
    watched = {
        n.lower()
        for n in await db.scalars(select(Watch.repo_full_name).where(Watch.user_id == user_id))
    }
    return (chosen or catalogue) | watched


def shuffle_key(seed: str, card_id: int) -> str:
    return hashlib.sha256(f"{seed}:{card_id}".encode()).hexdigest()


async def expire_old_holds(db: AsyncSession, now: datetime) -> None:
    await db.execute(
        update(Reservation)
        .where(Reservation.status == ACTIVE, Reservation.expires_at <= now)
        .values(status=EXPIRED, ended_at=now)
    )


async def active_hold(db: AsyncSession, user_id: int, day: str) -> Reservation | None:
    held: Reservation | None = await db.scalar(
        select(Reservation).where(
            Reservation.user_id == user_id, Reservation.status == ACTIVE, Reservation.day == day
        )
    )
    return held


async def swaps_today(db: AsyncSession, user_id: int, day: str) -> int:
    count = await db.scalar(
        select(func.count(Reservation.id)).where(
            Reservation.user_id == user_id, Reservation.day == day, Reservation.status == SWAPPED
        )
    )
    return count or 0


async def ranked(
    db: AsyncSession, user_id: int, taste: Taste, now: datetime, *, fresh_only: bool = False
) -> list[tuple[IssueCard, Fit]]:
    """Open issues in the user's pool that nobody else holds, best fit first.

    fresh_only also leaves out issues this user was picked before, so a swapped
    or expired pick does not come back.
    """
    names = await pool(db, user_id, taste)
    if not names:
        return []
    held_by_other = exists().where(
        Reservation.card_id == IssueCard.id,
        Reservation.status == ACTIVE,
        Reservation.expires_at > now,  # a hold past its 48 hours no longer counts
        Reservation.user_id != user_id,
    )
    query = select(IssueCard).where(
        func.lower(IssueCard.repo_full_name).in_(names),
        IssueCard.availability.in_(OPEN_STATES),
        ~held_by_other,
    )
    if fresh_only:
        query = query.where(
            ~exists().where(Reservation.card_id == IssueCard.id, Reservation.user_id == user_id)
        )
    out = []
    for card in await db.scalars(query):
        result = fit(card, taste, now)
        if result is not None:
            out.append((card, result))
    out.sort(key=lambda pair: (-pair[1].score, pair[0].id))
    return out


async def log(
    db: AsyncSession,
    user_id: int,
    card: IssueCard,
    surface: str,
    action: str,
    result: Fit | None = None,
) -> None:
    db.add(
        RecommendationEvent(
            user_id=user_id,
            repo_full_name=card.repo_full_name,
            number=card.number,
            surface=surface,
            action=action,
            fit=result.score if result else None,
            parts=result.parts if result else {},
        )
    )


async def _hold_best(
    db: AsyncSession, user_id: int, taste: Taste, day: str, now: datetime, action: str
) -> Reservation | None:
    # Plain values: a rollback below expires the loaded rows.
    candidates = [
        (card.id, card.repo_full_name, card.number, result)
        for card, result in (await ranked(db, user_id, taste, now, fresh_only=True))[:10]
    ]
    for card_id, repo, number, result in candidates:
        db.add(
            Reservation(
                user_id=user_id,
                card_id=card_id,
                status=ACTIVE,
                day=day,
                fit=result.score,
                reserved_at=now,
                expires_at=now + HOLD,
            )
        )
        db.add(
            RecommendationEvent(
                user_id=user_id,
                repo_full_name=repo,
                number=number,
                surface="daily",
                action=action,
                fit=result.score,
                parts=result.parts,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            # Someone else took this issue a moment ago; try the next one.
            await db.rollback()
            continue
        return await active_hold(db, user_id, day)
    return None


async def todays_pick(
    db: AsyncSession, user_id: int, now: datetime | None = None
) -> Reservation | None:
    """The user's pick for their local today, making one if there is none yet."""
    now = now or utcnow()
    taste = await load_taste(db, user_id)
    day = local_day(taste, now).isoformat()
    await expire_old_holds(db, now)
    held = await active_hold(db, user_id, day)
    if held is not None and held.card.availability in OPEN_STATES:
        await db.commit()
        return held
    # A new day, or today's pick was claimed or got a PR since: release it and
    # pick again. That does not count as one of the user's swaps.
    await db.execute(
        update(Reservation)
        .where(Reservation.user_id == user_id, Reservation.status == ACTIVE)
        .values(status=EXPIRED, ended_at=now)
    )
    await db.commit()
    return await _hold_best(db, user_id, taste, day, now, "shown")


class SwapLimitReached(Exception):
    pass


async def show_another(
    db: AsyncSession, user_id: int, now: datetime | None = None
) -> Reservation | None:
    """Release today's pick and hold the next best one. At most SWAPS_PER_DAY a day."""
    now = now or utcnow()
    taste = await load_taste(db, user_id)
    day = local_day(taste, now).isoformat()
    if await swaps_today(db, user_id, day) >= SWAPS_PER_DAY:
        raise SwapLimitReached
    held = await active_hold(db, user_id, day)
    if held is not None:
        held.status = SWAPPED
        held.ended_at = now
        await log(db, user_id, held.card, "daily", "swapped")
        await db.commit()
    return await _hold_best(db, user_id, taste, day, now, "shown")
