"""My pull requests, notifications (with a live stream), and email settings."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select, update
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
from firstpr_platform import notify
from firstpr_platform.db import Notification, TrackedPull, User, utcnow
from issueradar.models import PullRequestStatus
from issueradar.prs.status import PRIORITY

router = APIRouter()

REFRESH_KEY = "firstpr:refresh-pulls:"
STREAM_SECONDS = 10 * 60
STREAM_EVERY = 3.0


class PullOut(BaseModel):
    repo: str
    number: int
    title: str
    url: str | None
    status: str
    status_label: str
    needs_you: bool
    what_to_do: str
    reasons: list[str]
    nudge: str | None
    days_quiet: int
    draft: bool
    opened_at: datetime | None
    closed_at: datetime | None
    timeline: list[dict[str, str]]
    checked_at: datetime


class Pulls(BaseModel):
    items: list[PullOut]
    checked_at: datetime | None
    next_refresh_at: datetime | None


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    link: str | None
    external_url: str | None
    created_at: datetime
    read: bool


class Notifications(BaseModel):
    items: list[NotificationOut]
    unread: int


class ReadIn(BaseModel):
    ids: list[int] = Field(default_factory=list)
    all: bool = False


class EmailOut(BaseModel):
    address: str | None
    enabled: bool
    digest: bool
    # False when the server has no email provider set up yet.
    sending: bool


class EmailIn(BaseModel):
    enabled: bool
    digest: bool


def _pull_out(row: TrackedPull) -> PullOut:
    status = PullRequestStatus(row.status)
    return PullOut(
        repo=row.repo_full_name,
        number=row.number,
        title=row.title,
        url=row.url,
        status=row.status,
        status_label=status.label,
        needs_you=status.needs_you,
        what_to_do=row.needs_you,
        reasons=list(row.reasons),
        nudge=row.nudge,
        days_quiet=row.days_quiet,
        draft=row.draft,
        opened_at=row.opened_at,
        closed_at=row.closed_at,
        timeline=list(row.timeline)[-5:],
        checked_at=row.checked_at,
    )


async def _next_refresh(redis: Redis, user: User) -> datetime | None:
    ttl = await redis.ttl(f"{REFRESH_KEY}{user.id}")
    return utcnow() + timedelta(seconds=ttl) if ttl and ttl > 0 else None


# -------------------------------------------------------------- pulls


@router.get("/me/pulls", response_model=Pulls)
async def my_pulls(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> Pulls:
    """Every tracked pull request, what needs the user first."""
    rows = list(await db.scalars(select(TrackedPull).where(TrackedPull.user_id == user.id)))
    rows.sort(
        key=lambda r: (
            PRIORITY[PullRequestStatus(r.status)],
            -(r.changed_at.timestamp() if r.changed_at else 0),
        )
    )
    checked = max((r.checked_at for r in rows), default=None)
    return Pulls(
        items=[_pull_out(r) for r in rows],
        checked_at=checked,
        next_refresh_at=await _next_refresh(redis, user),
    )


@router.post("/me/pulls/refresh", response_model=Pulls, dependencies=[Depends(require_csrf)])
async def refresh_pulls(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
    jobs: Jobs = Depends(get_jobs),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> Pulls:
    key = f"{REFRESH_KEY}{user.id}"
    if not await redis.set(key, "1", nx=True, ex=settings.refresh_every_seconds):
        wait = max(1, await redis.ttl(key))
        raise HTTPException(429, f"Checked a moment ago. Try again in {(wait + 59) // 60} min.")
    await jobs.enqueue_job("track_user", user.id, _job_id=f"track-user:{user.id}")
    return await my_pulls(user, db, redis)


# ------------------------------------------------------- notifications


def _note_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        link=n.link,
        external_url=n.external_url,
        created_at=n.created_at,
        read=n.read_at is not None,
    )


async def _unread(db: AsyncSession, user_id: int) -> int:
    count = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        )
    )
    return count or 0


@router.get("/me/notifications", response_model=Notifications)
async def notifications(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Notifications:
    rows = await db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
        .limit(50)
    )
    return Notifications(items=[_note_out(n) for n in rows], unread=await _unread(db, user.id))


@router.post(
    "/me/notifications/read", response_model=Notifications, dependencies=[Depends(require_csrf)]
)
async def mark_read(
    body: ReadIn,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Notifications:
    query = update(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)
    )
    if not body.all:
        query = query.where(Notification.id.in_(body.ids or [-1]))
    await db.execute(query.values(read_at=utcnow()))
    await db.commit()
    return await notifications(user, db)


@router.get("/me/notifications/stream")
async def stream(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008
) -> StreamingResponse:
    """Server-sent events: the unread count, and each new notification as it arrives.
    The browser reconnects by itself when the stream ends."""
    factory = request.app.state.db
    user_id = user.id

    async def events() -> Any:
        async with factory() as db:
            last = await db.scalar(
                select(func.max(Notification.id)).where(Notification.user_id == user_id)
            )
            unread = await _unread(db, user_id)
        last = last or 0
        yield f"event: unread\ndata: {unread}\n\n"
        for _ in range(int(STREAM_SECONDS / STREAM_EVERY)):
            await asyncio.sleep(STREAM_EVERY)
            if await request.is_disconnected():
                return
            async with factory() as db:
                rows = list(
                    await db.scalars(
                        select(Notification)
                        .where(Notification.user_id == user_id, Notification.id > last)
                        .order_by(Notification.id)
                    )
                )
                now_unread = await _unread(db, user_id)
            for note in rows:
                last = note.id
                yield f"event: notification\ndata: {_note_out(note).model_dump_json()}\n\n"
            if now_unread != unread:
                unread = now_unread
                yield f"event: unread\ndata: {unread}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------- email


async def _email_out(db: AsyncSession, user: User, settings: Settings) -> EmailOut:
    prefs = await notify.prefs(db, user.id)
    await db.commit()
    return EmailOut(
        address=user.email,
        enabled=prefs.enabled,
        digest=prefs.digest,
        sending=bool(settings.resend_api_key.get_secret_value()),
    )


@router.get("/me/email", response_model=EmailOut)
async def email_settings(
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> EmailOut:
    return await _email_out(db, user, settings)


@router.put("/me/email", response_model=EmailOut, dependencies=[Depends(require_csrf)])
async def save_email_settings(
    body: EmailIn,
    user: User = Depends(current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> EmailOut:
    prefs = await notify.prefs(db, user.id)
    prefs.enabled = body.enabled
    prefs.digest = body.digest
    await db.commit()
    return await _email_out(db, user, settings)


async def _unsubscribe(db: AsyncSession, settings: Settings, u: int, t: str) -> bool:
    key = notify.signing_key(settings.token_keys.get_secret_value())
    if not settings.token_keys.get_secret_value() or not notify.check_unsubscribe(key, u, t):
        return False
    if await db.get(User, u) is None:
        return False
    prefs = await notify.prefs(db, u)
    prefs.enabled = False
    await db.commit()
    return True


@router.get("/email/unsubscribe")
async def unsubscribe_link(
    u: int,
    t: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> RedirectResponse:
    """The link in every email: turns email off at once, no sign-in needed."""
    ok = await _unsubscribe(db, settings, u, t)
    return RedirectResponse("/email-off" if ok else "/email-off?bad=1", status_code=302)


@router.post("/email/unsubscribe")
async def unsubscribe_one_click(
    u: int,
    t: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> Response:
    """RFC 8058 one-click unsubscribe, sent by the mail app itself."""
    if not await _unsubscribe(db, settings, u, t):
        raise HTTPException(400, "Bad unsubscribe link")
    return Response(status_code=200)
