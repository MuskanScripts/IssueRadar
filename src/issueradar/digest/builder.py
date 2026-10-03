"""Build the daily digest (brief 5.10).

Sections: free for you (top N), your pull requests, new since yesterday,
watchlist alerts, and a quiet-day message when there is nothing new.

Idempotent: an item that was already sent is left out until its state changes.
Its state is a short hash of what the reader sees (availability, tier and
title for issues; status for PRs). Dismissed items never come back; snoozed
items come back after their date.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta

from sqlalchemy import func, select

from issueradar.config.settings import Settings
from issueradar.digest.model import Alert, Digest, IssueItem, PullItem
from issueradar.models import level_dots
from issueradar.radar import Filters, IssueReport, Radar
from issueradar.storage.db import Database
from issueradar.storage.models import (
    LOCAL_USER_ID,
    DigestRun,
    Issue,
    Repo,
    ScoreSnapshot,
    SeenItem,
    Watchlist,
    as_utc,
    utcnow,
)

PullProvider = Callable[[], Sequence[PullItem]]
QUIET_MESSAGES = (
    "Nothing new today. Your watched repos are quiet, which is a good day to finish "
    "something you already started."
)


def state_hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def issue_key(repo: str, number: int) -> str:
    return f"issue:{repo}#{number}"


def _item(report: IssueReport) -> IssueItem:
    return IssueItem(
        key=issue_key(report.repo, report.number),
        repo=report.repo,
        number=report.number,
        title=report.title,
        url=report.url,
        tier=report.difficulty.tier.value,
        dots=level_dots(report.difficulty.tier),
        state=report.availability.state.label,
        why=report.rank.why if report.rank else "",
        state_hash=state_hash(
            report.availability.state.value, report.difficulty.tier.value, report.title
        ),
    )


class DigestBuilder:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        radar: Radar,
        *,
        user_id: int = LOCAL_USER_ID,
        clock: Callable[[], datetime] = utcnow,
        pulls: PullProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.radar = radar
        self.user_id = user_id
        self.clock = clock
        self.pulls = pulls

    def _blocked(self) -> dict[str, tuple[str, str | None]]:
        """key -> (state, hash) for items the reader should not see again now."""
        now = self.clock()
        blocked: dict[str, tuple[str, str | None]] = {}
        with self.db.sessions() as session:
            for seen in session.scalars(select(SeenItem).where(SeenItem.user_id == self.user_id)):
                if seen.state == "snoozed":
                    until = as_utc(seen.snoozed_until)
                    if until is not None and until <= now:
                        continue
                blocked[seen.item_key] = (seen.state, seen.state_hash)
        return blocked

    @staticmethod
    def _is_new(key: str, digest_hash: str, blocked: dict[str, tuple[str, str | None]]) -> bool:
        if key not in blocked:
            return True
        state, old_hash = blocked[key]
        if state in ("dismissed", "snoozed"):
            return False
        return old_hash != digest_hash  # shown before: only if something changed

    def build(self) -> Digest:
        now = self.clock()
        cfg = self.settings.digest
        digest = Digest(created_at=now)
        blocked = self._blocked()

        ranked = [_item(r) for r in self.radar.find(Filters())]
        fresh = {key for key in self._first_seen_since(now - timedelta(hours=cfg.new_since_hours))}
        for item in ranked:
            if not self._is_new(item.key, item.state_hash, blocked):
                continue
            if len(digest.free) < cfg.top_n:
                digest.free.append(item)
            elif item.key in fresh:
                digest.new_since.append(item)

        if self.pulls is not None:
            # The first digest with pull requests shows the ones still open. PRs that
            # closed before then are history, not news; a first run would otherwise
            # list everything merged in the last day.
            first = not any(key.startswith("pr:") for key in blocked)
            for pull in self.pulls():
                if first and pull.closed:
                    continue
                if self._is_new(pull.key, pull.state_hash, blocked):
                    digest.pulls.append(pull)

        for alert in self._alerts(now):
            if self._is_new(alert.key, alert.state_hash, blocked):
                digest.alerts.append(alert)

        if digest.is_empty and not self._sent_today(now):
            digest.quiet_message = QUIET_MESSAGES
        return digest

    def _first_seen_since(self, since: datetime) -> list[str]:
        with self.db.sessions() as session:
            rows = session.execute(
                select(Repo.full_name, Issue.number, func.min(ScoreSnapshot.computed_at))
                .join(Issue, Issue.id == ScoreSnapshot.issue_id)
                .join(Repo, Repo.id == Issue.repo_id)
                .where(ScoreSnapshot.user_id == self.user_id)
                .group_by(Repo.full_name, Issue.number)
            )
            return [
                issue_key(repo, number)
                for repo, number, first in rows
                if first is not None and (as_utc(first) or since) >= since
            ]

    def _alerts(self, now: datetime) -> list[Alert]:
        quiet_days = self.settings.digest.quiet_repo_days
        alerts = []
        with self.db.sessions() as session:
            watched = select(Watchlist.repo_full_name).where(Watchlist.user_id == self.user_id)
            for repo in session.scalars(select(Repo).where(Repo.full_name.in_(watched))):
                pushed = as_utc(repo.pushed_at)
                if repo.archived:
                    text = (
                        f"{repo.full_name} was archived. Consider removing it from your watchlist."
                    )
                    alerts.append(
                        Alert(
                            f"repo:{repo.full_name}:archived",
                            repo.full_name,
                            text,
                            state_hash("archived"),
                        )
                    )
                elif pushed is not None and (now - pushed).days >= quiet_days:
                    days = (now - pushed).days
                    text = f"{repo.full_name} has had no push for {days} days."
                    alerts.append(
                        Alert(
                            f"repo:{repo.full_name}:quiet",
                            repo.full_name,
                            text,
                            state_hash("quiet", days // 30),
                        )
                    )
                elif repo.sync_error:
                    text = f"{repo.full_name} could not be synced: {repo.sync_error}"
                    alerts.append(
                        Alert(
                            f"repo:{repo.full_name}:error",
                            repo.full_name,
                            text,
                            state_hash("error", repo.sync_error),
                        )
                    )
        return alerts

    def _sent_today(self, now: datetime) -> bool:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        with self.db.sessions() as session:
            count = session.scalar(
                select(func.count())
                .select_from(DigestRun)
                .where(
                    DigestRun.user_id == self.user_id,
                    DigestRun.status == "sent",
                    DigestRun.started_at >= start,
                )
            )
        return bool(count)


def record_sent(
    db: Database, digest: Digest, channels: list[str], user_id: int = LOCAL_USER_ID
) -> None:
    """Remember what was sent so the next digest only has news."""
    with db.sessions.begin() as session:
        for item in digest.items:
            seen = session.scalar(
                select(SeenItem).where(SeenItem.user_id == user_id, SeenItem.item_key == item.key)
            )
            kind = item.key.split(":", 1)[0]
            if seen is None:
                session.add(
                    SeenItem(
                        user_id=user_id,
                        item_kind=kind,
                        item_key=item.key,
                        state="shown",
                        state_hash=item.state_hash,
                        updated_at=digest.created_at,
                    )
                )
            elif seen.state in ("shown", "snoozed"):
                seen.state = "shown"
                seen.state_hash = item.state_hash
                seen.snoozed_until = None
                seen.updated_at = digest.created_at
        session.add(
            DigestRun(
                user_id=user_id,
                channel=",".join(channels),
                status="sent",
                started_at=digest.created_at,
                finished_at=utcnow(),
                items=[item.key for item in digest.items],
            )
        )


def mark(
    db: Database,
    key: str,
    state: str,
    *,
    until: datetime | None = None,
    user_id: int = LOCAL_USER_ID,
) -> None:
    """Dismiss or snooze an item by key."""
    with db.sessions.begin() as session:
        seen = session.scalar(
            select(SeenItem).where(SeenItem.user_id == user_id, SeenItem.item_key == key)
        )
        if seen is None:
            seen = SeenItem(
                user_id=user_id, item_kind=key.split(":", 1)[0], item_key=key, state=state
            )
            session.add(seen)
        seen.state = state
        seen.snoozed_until = until
        seen.updated_at = utcnow()
