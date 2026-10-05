"""Database tables for the platform: accounts, sessions, watches and sync state.

Types stay portable (no Postgres-only columns) so tests can run on SQLite.
Production runs on Postgres; migrations live in apps/api/migrations.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Always hands back timezone-aware UTC datetimes, also on SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("naive datetime; use timezone-aware UTC")
        return value

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


# BIGINT on Postgres, but SQLite only auto-increments INTEGER primary keys.
BigId = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    handle: Mapped[str] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    # "user" or "admin". Admins are the GitHub logins in FIRSTPR_ADMIN_LOGINS.
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    github: Mapped[GitHubAccount] = relationship(back_populates="user", lazy="joined")


class GitHubAccount(Base):
    __tablename__ = "github_accounts"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    login: Mapped[str] = mapped_column(String(100))
    # Encrypted with Fernet (see crypto.py). Never logged, never sent to the browser.
    access_token: Mapped[bytes] = mapped_column(LargeBinary)
    access_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    refresh_token: Mapped[bytes | None] = mapped_column(LargeBinary)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # "connected" or "reconnect_needed".
    status: Mapped[str] = mapped_column(String(20), default="connected")
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="github", lazy="joined")


class Session(Base):
    __tablename__ = "sessions"

    # SHA-256 of the cookie value. The cookie value itself is never stored.
    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    user_agent: Mapped[str | None] = mapped_column(String(200))


class Watch(Base):
    """A repo one user follows. Who watches what decides which token syncs it."""

    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("user_id", "repo_full_name"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    repo_full_name: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CatalogueRepo(Base):
    """A repo in the shared catalogue, synced with the app's own token."""

    __tablename__ = "catalogue_repos"

    full_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    # "pack" (from a starter pack) or "admin" (added by hand).
    source: Mapped[str] = mapped_column(String(20))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RepoSync(Base):
    """The last sync of each repo, for the admin page."""

    __tablename__ = "repo_syncs"

    full_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    # "app" (installation token) or "user" (the one watcher's own token).
    token_kind: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))  # synced, archived, failed, paused
    note: Mapped[str | None] = mapped_column(String(500))
    open_issues: Mapped[int] = mapped_column(Integer, default=0)
    synced_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WebhookEvent(Base):
    """A delivery from GitHub, kept until the worker has handled it."""

    __tablename__ = "webhook_events"

    delivery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event: Mapped[str] = mapped_column(String(50))
    action: Mapped[str | None] = mapped_column(String(50))
    repo_full_name: Mapped[str | None] = mapped_column(String(200))
    sender_github_id: Mapped[int | None] = mapped_column(BigInteger)
    payload: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    result: Mapped[str | None] = mapped_column(String(200))


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def open_session(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
