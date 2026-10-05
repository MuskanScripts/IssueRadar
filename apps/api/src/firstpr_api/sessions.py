"""Server-side sessions behind an HTTP-only cookie, plus the CSRF cookie.

The cookie holds a random value; only its SHA-256 is stored. Sessions live in
Postgres and are cached in Redis, so they can be revoked at once (sign out,
abuse, a leaked token) and every request costs one Redis lookup.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import Response
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api.db import Session, User, utcnow
from firstpr_api.settings import Settings

SESSION_COOKIE = "firstpr_session"
CSRF_COOKIE = "firstpr_csrf"
CSRF_HEADER = "X-CSRF-Token"
CACHE_PREFIX = "firstpr:session:"
CACHE_SECONDS = 24 * 3600
# Sliding expiry: extend a session at most once an hour, not on every request.
EXTEND_AFTER = timedelta(hours=1)


def hash_id(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create(
    db: AsyncSession, redis: Redis, user_id: int, settings: Settings, user_agent: str | None
) -> str:
    raw = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        Session(
            id_hash=hash_id(raw),
            user_id=user_id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=settings.session_days),
            user_agent=(user_agent or "")[:200] or None,
        )
    )
    await db.commit()
    await redis.set(CACHE_PREFIX + hash_id(raw), str(user_id), ex=CACHE_SECONDS)
    return raw


async def load(
    db: AsyncSession, redis: Redis, raw: str | None, settings: Settings
) -> tuple[User | None, bool]:
    """The signed-in user, and whether the session was just extended."""
    if not raw:
        return None, False
    key = hash_id(raw)
    cached = await redis.get(CACHE_PREFIX + key)
    if cached is not None:
        # Revoking deletes this key, so a hit means the session is still good.
        return await db.scalar(select(User).where(User.id == int(cached))), False

    row = await db.get(Session, key)
    now = utcnow()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None, False
    extended = False
    if now - row.last_seen_at >= EXTEND_AFTER:
        row.last_seen_at = now
        row.expires_at = now + timedelta(days=settings.session_days)
        await db.commit()
        extended = True
    left = int((row.expires_at - now).total_seconds())
    await redis.set(CACHE_PREFIX + key, str(row.user_id), ex=max(1, min(CACHE_SECONDS, left)))
    user = await db.scalar(select(User).where(User.id == row.user_id))
    return user, extended


async def revoke(db: AsyncSession, redis: Redis, raw: str | None) -> None:
    if not raw:
        return
    key = hash_id(raw)
    await redis.delete(CACHE_PREFIX + key)
    row = await db.get(Session, key)
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()
        await db.commit()


def set_cookies(response: Response, raw: str, settings: Settings) -> None:
    max_age = settings.session_days * 24 * 3600
    response.set_cookie(
        SESSION_COOKIE,
        raw,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    # Readable by the page's own script, which echoes it in the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(24),
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_cookies(response: Response, settings: Settings) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=settings.cookie_secure, samesite="lax")
