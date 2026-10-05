"""Fit and the daily pick: levels and skills, a new day, holds running out."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from firstpr_platform import picks
from firstpr_platform.db import (
    Base,
    CatalogueRepo,
    IssueCard,
    Profile,
    Reservation,
    User,
    UserSkill,
    session_factory,
)
from issueradar.engine.stack import SkillProfile
from issueradar.models import Tier

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'p.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory(engine)() as session:
        yield session
    await engine.dispose()


def card(number: int, **values: object) -> IssueCard:
    defaults: dict[str, object] = {
        "repo_full_name": "pallets/flask",
        "number": number,
        "title": f"Issue {number}",
        "url": None,
        "labels": [],
        "language": "Python",
        "languages": ["python"],
        "frameworks": [],
        "domains": [],
        "paths": [],
        "stars": 10,
        "comments": 0,
        "updated_at": NOW - timedelta(days=2),
        "availability": "free",
        "availability_reasons": ["Free"],
        "tier": "beginner",
        "difficulty_score": 10,
        "time_bucket": "under_an_hour",
        "issue_type": "docs",
        "difficulty_reasons": [],
        "discussion_first": False,
        "health": 75,
        "health_reasons": [],
        "checklist": [],
        "changed_at": NOW,
        "refreshed_at": NOW,
    }
    return IssueCard(**{**defaults, **values})


async def setup(db: AsyncSession, users: int = 1, cards: int = 3, tz: str = "UTC") -> None:
    db.add(CatalogueRepo(full_name="pallets/flask", source="pack"))
    for user_id in range(1, users + 1):
        db.add(User(id=user_id, handle=f"u{user_id}"))
        db.add(Profile(user_id=user_id, level="beginner", packs=[], timezone=tz, onboarded_at=NOW))
    db.add_all(card(n) for n in range(1, cards + 1))
    await db.commit()


def test_level_and_skills_change_the_fit() -> None:
    issue = card(1, tier="intermediate")
    beginner = picks.fit(issue, picks.Taste(level=Tier.BEGINNER), NOW)
    intermediate = picks.fit(issue, picks.Taste(level=Tier.INTERMEDIATE), NOW)
    assert beginner and intermediate and intermediate.score > beginner.score
    assert "one step above" in " ".join(beginner.why)

    strong = picks.Taste(skills=SkillProfile(languages={"python": "strong"}))
    other = picks.Taste(skills=SkillProfile(languages={"go": "strong"}))
    knows = picks.fit(card(2), strong, NOW)
    does_not = picks.fit(card(2), other, NOW)
    assert knows and does_not and knows.score > does_not.score
    assert "Uses what you know: python (strong)" in knows.why
    assert picks.fit(card(3, availability="has_pr"), strong, NOW) is None


async def test_one_pick_a_day_and_a_new_one_tomorrow(db: AsyncSession) -> None:
    await setup(db)
    first = await picks.todays_pick(db, 1, NOW)
    assert first is not None and first.day == "2026-10-05"
    same = await picks.todays_pick(db, 1, NOW + timedelta(hours=3))
    assert same is not None and same.id == first.id

    tomorrow = await picks.todays_pick(db, 1, NOW + timedelta(days=1))
    assert tomorrow is not None and tomorrow.card_id != first.card_id
    old = await db.get(Reservation, first.id)
    assert old is not None and old.status == picks.EXPIRED


async def test_the_day_follows_the_users_time_zone(db: AsyncSession) -> None:
    await setup(db, tz="Asia/Kolkata")
    late = datetime(2026, 10, 5, 19, 0, tzinfo=UTC)  # 00:30 on the 6th in India
    pick = await picks.todays_pick(db, 1, late)
    assert pick is not None and pick.day == "2026-10-06"


async def test_holds_run_out_after_48_hours(db: AsyncSession) -> None:
    await setup(db, users=2, cards=1)
    mine = await picks.todays_pick(db, 1, NOW)
    assert mine is not None
    # The only issue is held, so the second person gets nothing for now.
    assert await picks.todays_pick(db, 2, NOW + timedelta(hours=1)) is None
    theirs = await picks.todays_pick(db, 2, NOW + timedelta(hours=49))
    assert theirs is not None and theirs.card_id == mine.card_id
    active = await db.scalars(select(Reservation).where(Reservation.status == "active"))
    assert [r.user_id for r in active] == [2]


async def test_swaps_are_limited(db: AsyncSession) -> None:
    await setup(db, cards=6)
    await picks.todays_pick(db, 1, NOW)
    for _ in range(picks.SWAPS_PER_DAY):
        assert await picks.show_another(db, 1, NOW) is not None
    with pytest.raises(picks.SwapLimitReached):
        await picks.show_another(db, 1, NOW)
    # The limit is per day.
    assert await picks.show_another(db, 1, NOW + timedelta(days=1)) is not None


async def test_skills_are_read_from_the_database(db: AsyncSession) -> None:
    await setup(db)
    db.add(UserSkill(user_id=1, kind="languages", name="python", level="medium"))
    await db.commit()
    taste = await picks.load_taste(db, 1)
    assert taste.skills is not None and taste.skills.level("languages", "python") == "medium"


async def test_a_pick_that_got_claimed_is_replaced_for_free(db: AsyncSession) -> None:
    await setup(db, cards=3)
    first = await picks.todays_pick(db, 1, NOW)
    assert first is not None
    first.card.availability = "claimed"  # the next sync saw a claim
    await db.commit()
    second = await picks.todays_pick(db, 1, NOW + timedelta(hours=1))
    assert second is not None and second.card_id != first.card_id
    assert await picks.swaps_today(db, 1, second.day) == 0


async def test_a_hold_past_48_hours_no_longer_hides_the_issue(db: AsyncSession) -> None:
    await setup(db, users=2, cards=1)
    assert await picks.todays_pick(db, 1, NOW) is not None
    taste = await picks.load_taste(db, 2)
    assert await picks.ranked(db, 2, taste, NOW + timedelta(hours=47)) == []
    later = await picks.ranked(db, 2, taste, NOW + timedelta(hours=49))
    assert [card.number for card, _ in later] == [1]
