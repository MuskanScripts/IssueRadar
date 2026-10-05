"""XP, badges, active days and streaks.

Only accepted work earns XP: a merged pull request, an approval, a finished
practice task. Awards are written by the worker and keyed by what earned them,
so a webhook that arrives twice still pays once.

A day is green at GREEN_MINUTES active minutes (site time plus Codespace time)
or when a commit was pushed. A streak is green days in a row; one missed day
a week (Monday to Sunday) is bridged by a free freeze. Days are the user's own
calendar days, in their time zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_platform.db import (
    DailyActivity,
    TrackedPull,
    User,
    UserBadge,
    Workspace,
    XpTransaction,
    utcnow,
)

GREEN_MINUTES = 15
XP = {"pr_merged": 100, "pr_approved": 20, "practice_done": 30}


@dataclass(frozen=True)
class Badge:
    key: str
    name: str
    description: str


BADGES = (
    Badge("first_pr", "First pull request", "Opened your first pull request through FirstPR."),
    Badge("practice", "Warmed up", "Finished the practice task."),
    Badge("first_merge", "Merged", "Your first pull request was merged."),
    Badge("hat_trick", "Hat trick", "Three pull requests merged."),
    Badge("explorer", "Explorer", "Pull requests merged in three different repos."),
    Badge("week_streak", "Seven days", "A streak of seven green days."),
)


def _insert(db: AsyncSession) -> Any:
    """INSERT for this database, so ON CONFLICT works on Postgres and SQLite."""
    return pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert


async def award(db: AsyncSession, user_id: int, reason: str, source: str, note: str) -> bool:
    """Give XP once per source. True when it was new."""
    statement = (
        _insert(db)(XpTransaction)
        .values(
            user_id=user_id,
            amount=XP[reason],
            reason=reason,
            source=source[:300],
            note=note[:300],
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["user_id", "source"])
        .returning(XpTransaction.id)
    )
    new = await db.scalar(statement)
    if new is not None:
        total = await db.scalar(
            select(func.coalesce(func.sum(XpTransaction.amount), 0)).where(
                XpTransaction.user_id == user_id
            )
        )
        user = await db.get(User, user_id)
        if user is not None:
            user.xp = int(total or 0)
    await db.commit()
    return new is not None


# ------------------------------------------------------------------ days


@dataclass
class Day:
    day: date
    web_minutes: int = 0
    codespace_minutes: int = 0
    commits: int = 0
    frozen: bool = False

    @property
    def minutes(self) -> int:
        return self.web_minutes + self.codespace_minutes

    @property
    def green(self) -> bool:
        return self.minutes >= GREEN_MINUTES or self.commits > 0


async def add_activity(
    db: AsyncSession,
    user_id: int,
    day: str,
    *,
    web_minutes: int = 0,
    codespace_minutes: int = 0,
    commits: int = 0,
) -> None:
    """Add to a day's totals (the row is made when missing). Caller commits."""
    insert = _insert(db)
    statement = insert(DailyActivity).values(
        user_id=user_id,
        day=day,
        web_minutes=web_minutes,
        codespace_minutes=codespace_minutes,
        commits=commits,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["user_id", "day"],
        set_={
            "web_minutes": DailyActivity.web_minutes + statement.excluded.web_minutes,
            "codespace_minutes": DailyActivity.codespace_minutes
            + statement.excluded.codespace_minutes,
            "commits": DailyActivity.commits + statement.excluded.commits,
        },
    )
    await db.execute(statement)


async def days(db: AsyncSession, user_id: int, first: date, last: date) -> dict[date, Day]:
    rows = await db.scalars(
        select(DailyActivity).where(
            DailyActivity.user_id == user_id,
            DailyActivity.day >= first.isoformat(),
            DailyActivity.day <= last.isoformat(),
        )
    )
    out = {}
    for row in rows:
        d = date.fromisoformat(row.day)
        out[d] = Day(d, row.web_minutes, row.codespace_minutes, row.commits)
    return out


@dataclass
class Streak:
    current: int
    best: int
    frozen: set[date]
    freeze_left_this_week: bool


def _week(d: date) -> tuple[int, int]:
    year, week, _ = d.isocalendar()
    return year, week


def streak(known: dict[date, Day], today: date) -> Streak:
    """Green days in a row up to today. Today only counts once it is green (it is
    not over yet). One missed day per week is bridged when the days on both
    sides are green."""

    def green(d: date) -> bool:
        return d in known and known[d].green

    if not known:
        return Streak(0, 0, set(), True)
    first = min(known)
    frozen: set[date] = set()
    used: set[tuple[int, int]] = set()
    run = best = 0
    d = first
    while d <= today:
        if green(d):
            run += 1
        elif d < today and run > 0 and _week(d) not in used and green(d + timedelta(days=1)):
            frozen.add(d)  # a freeze keeps the streak alive, it does not add a day
            used.add(_week(d))
        elif d < today:
            run = 0
        best = max(best, run)
        d += timedelta(days=1)
    return Streak(run, best, frozen, _week(today) not in used)


# ---------------------------------------------------------------- badges


async def earned(db: AsyncSession, user_id: int) -> dict[str, UserBadge]:
    rows = await db.scalars(select(UserBadge).where(UserBadge.user_id == user_id))
    return {r.badge: r for r in rows}


async def check_badges(
    db: AsyncSession, user_id: int, best_streak: int | None = None
) -> list[Badge]:
    """Give every badge whose rule is met now. Returns the newly earned ones."""
    have = await earned(db, user_id)
    opened = await db.scalar(
        select(func.count(Workspace.id)).where(
            Workspace.user_id == user_id, Workspace.pr_url.is_not(None)
        )
    )
    practice = await db.scalar(
        select(func.count(XpTransaction.id)).where(
            XpTransaction.user_id == user_id, XpTransaction.reason == "practice_done"
        )
    )
    merged_rows = (
        await db.execute(
            select(TrackedPull.repo_full_name).where(
                TrackedPull.user_id == user_id, TrackedPull.merged.is_(True)
            )
        )
    ).all()
    merged = len(merged_rows)
    repos = len({r.lower() for (r,) in merged_rows})
    rules = {
        "first_pr": (opened or 0) >= 1,
        "practice": (practice or 0) >= 1,
        "first_merge": merged >= 1,
        "hat_trick": merged >= 3,
        "explorer": repos >= 3,
        "week_streak": (best_streak or 0) >= 7,
    }
    new = []
    for badge in BADGES:
        if not rules[badge.key] or badge.key in have:
            continue
        added = await db.scalar(
            _insert(db)(UserBadge)
            .values(user_id=user_id, badge=badge.key, earned_at=utcnow())
            .on_conflict_do_nothing(index_elements=["user_id", "badge"])
            .returning(UserBadge.badge)
        )
        if added is not None:  # not given a moment ago by another job
            new.append(badge)
    await db.commit()
    return new


# ------------------------------------------------------------- Codespaces

CHECK_EVERY = timedelta(minutes=5)
IDLE_TIMEOUT = timedelta(minutes=15)


def codespace_tick(ws: Workspace, state: str | None, now: datetime) -> tuple[datetime, int] | None:
    """Follow a Codespace's runs from the regular state checks.

    Returns (when the run started, active minutes) when a run has just ended.
    A Codespace stops after 15 idle minutes, so those last 15 minutes of each run
    are not counted. The run ended somewhere in the 5 minutes after it was last
    seen running, so that half-step is added back.
    """
    if state == "Available":
        ws.codespace_up_since = ws.codespace_up_since or now
        ws.codespace_up_last = now
        return None
    if ws.codespace_up_since is None or ws.codespace_up_last is None:
        return None
    ran = ws.codespace_up_last - ws.codespace_up_since + CHECK_EVERY / 2
    started = ws.codespace_up_since
    ws.codespace_up_since = ws.codespace_up_last = None
    return started, max(0, int((ran - IDLE_TIMEOUT).total_seconds() // 60))
