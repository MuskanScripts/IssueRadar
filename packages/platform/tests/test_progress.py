"""Streaks with the weekly freeze, XP once per event, and badges."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from firstpr_platform import progress
from firstpr_platform.db import Base, DailyActivity, TrackedPull, User, session_factory

MONDAY = date(2026, 10, 5)


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'p.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory(engine)() as session:
        session.add(User(id=1, handle="u"))
        await session.commit()
        yield session
    await engine.dispose()


def green(*offsets: int, start: date = MONDAY) -> dict[date, progress.Day]:
    out = {}
    for o in offsets:
        d = start + timedelta(days=o)
        out[d] = progress.Day(d, web_minutes=20)
    return out


def test_a_day_is_green_at_15_minutes_or_a_commit() -> None:
    assert not progress.Day(MONDAY, web_minutes=10, codespace_minutes=4).green
    assert progress.Day(MONDAY, web_minutes=10, codespace_minutes=5).green
    assert progress.Day(MONDAY, commits=1).green


def test_streak_counts_green_days_and_today_only_once_green() -> None:
    days = green(0, 1, 2)
    assert progress.streak(days, MONDAY + timedelta(days=2)).current == 3
    # Day 3 has just started and is not green yet: the streak is still 3.
    assert progress.streak(days, MONDAY + timedelta(days=3)).current == 3
    # Day 3 ended without activity: on day 4 the streak is gone.
    assert progress.streak(days, MONDAY + timedelta(days=4)).current == 0


def test_one_missed_day_a_week_is_frozen() -> None:
    days = green(0, 1, 3, 4)  # Wednesday missed
    result = progress.streak(days, MONDAY + timedelta(days=4))
    assert result.current == 4 and result.frozen == {MONDAY + timedelta(days=2)}
    assert result.freeze_left_this_week is False
    # A second miss in the same week breaks it.
    days = green(0, 2, 4)
    assert progress.streak(days, MONDAY + timedelta(days=4)).current == 1
    # The next week has its own freeze.
    days = green(0, 1, 3, 4, 5, 6, 7, 9, 10)
    result = progress.streak(days, MONDAY + timedelta(days=10))
    assert result.current == 9 and len(result.frozen) == 2 and result.best == 9


async def test_xp_is_paid_once_per_event(db: AsyncSession) -> None:
    assert await progress.award(db, 1, "pr_merged", "pr:a/b#1:merged", "Merged a/b#1")
    assert not await progress.award(db, 1, "pr_merged", "pr:a/b#1:merged", "Merged a/b#1")
    assert await progress.award(db, 1, "pr_approved", "pr:a/b#1:approved", "Approved")
    user = await db.get(User, 1)
    assert user is not None and user.xp == 120


async def test_activity_adds_up_per_day(db: AsyncSession) -> None:
    await progress.add_activity(db, 1, "2026-10-05", web_minutes=3)
    await progress.add_activity(db, 1, "2026-10-05", web_minutes=4, commits=1)
    await db.commit()
    row = await db.scalar(select(DailyActivity))
    assert row is not None and (row.web_minutes, row.commits) == (7, 1)
    known = await progress.days(db, 1, MONDAY, MONDAY)
    assert known[MONDAY].green


async def test_badges_are_given_once(db: AsyncSession) -> None:
    for i, repo in enumerate(["a/one", "b/two", "c/three"]):
        db.add(
            TrackedPull(
                user_id=1,
                repo_full_name=repo,
                number=i,
                title="t",
                state="closed",
                merged=True,
                draft=False,
                status="merged",
                needs_you="",
                reasons=[],
                days_quiet=0,
                timeline=[],
            )
        )
    await db.commit()
    new = {b.key for b in await progress.check_badges(db, 1, best_streak=7)}
    assert new == {"first_merge", "hat_trick", "explorer", "week_streak"}
    assert await progress.check_badges(db, 1, best_streak=7) == []


def test_codespace_time_leaves_out_the_idle_minutes() -> None:
    from datetime import UTC, datetime

    from firstpr_platform.db import Workspace

    ws = Workspace()
    start = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
    for minute in range(0, 45, 5):  # seen running for 40 minutes
        assert progress.codespace_tick(ws, "Available", start + timedelta(minutes=minute)) is None
    ended = progress.codespace_tick(ws, "Shutdown", start + timedelta(minutes=45))
    assert ended == (start, 27)  # 40 + 2.5 (half a check) - 15 idle
    assert progress.codespace_tick(ws, "Shutdown", start + timedelta(minutes=50)) is None
    # A short run that was all idle time adds nothing.
    progress.codespace_tick(ws, "Available", start)
    assert progress.codespace_tick(ws, "Shutdown", start + timedelta(minutes=5)) == (start, 0)
