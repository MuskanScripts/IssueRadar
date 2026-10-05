"""Database tables for the platform: accounts, sessions, watches, sync state,
profiles, issue cards, daily picks and recommendation logs.

Types stay portable (no Postgres-only columns) so tests can run on SQLite.
Production runs on Postgres; migrations live in packages/platform/migrations.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    text,
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


class Profile(Base):
    """What a user told us in onboarding. One row per user, made on first save."""

    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # The engine's tiers: beginner, intermediate or pro.
    level: Mapped[str] = mapped_column(String(20), default="beginner")
    # Starter pack keys. Empty means every repo in the catalogue.
    packs: Mapped[list[str]] = mapped_column(JSON, default=list)
    # IANA name from the browser, so "today" means the user's own day.
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    onboarded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class UserSkill(Base):
    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "kind", "name"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # languages, frameworks, domains
    name: Mapped[str] = mapped_column(String(50))
    level: Mapped[str] = mapped_column(String(20))  # learning, medium, strong


class IssueCard(Base):
    """One open issue with the engine's verdicts, written by the worker after each sync.

    The API reads only this table, so a page never runs the engine over the
    whole catalogue. Fit is per user and is worked out on top of it.
    """

    __tablename__ = "issue_cards"
    __table_args__ = (UniqueConstraint("repo_full_name", "number"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    repo_full_name: Mapped[str] = mapped_column(String(200), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(500))
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    repo_description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100))
    languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    frameworks: Mapped[list[str]] = mapped_column(JSON, default=list)
    domains: Mapped[list[str]] = mapped_column(JSON, default=list)
    # File paths named in the issue body; they decide the language when present.
    paths: Mapped[list[str]] = mapped_column(JSON, default=list)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    availability: Mapped[str] = mapped_column(String(20), index=True)
    availability_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    tier: Mapped[str] = mapped_column(String(20))
    difficulty_score: Mapped[int] = mapped_column(Integer, default=0)
    time_bucket: Mapped[str] = mapped_column(String(30))
    issue_type: Mapped[str] = mapped_column(String(20))
    difficulty_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    discussion_first: Mapped[bool] = mapped_column(Boolean, default=False)
    health: Mapped[int | None] = mapped_column(Integer)
    health_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    checklist: Mapped[list[str]] = mapped_column(JSON, default=list)
    repo_notes: Mapped[str | None] = mapped_column(Text)
    # When the issue last changed in a way people care about (new activity, claimed).
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    refreshed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


ACTIVE = "active"


class Reservation(Base):
    """An issue held for one user. At most one active hold per issue, for 48 hours."""

    __tablename__ = "issue_reservations"
    __table_args__ = (
        Index(
            "uq_issue_reservations_active",
            "card_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("issue_cards.id", ondelete="CASCADE"))
    # active, swapped (the user asked for another), expired (time ran out or a new day).
    status: Mapped[str] = mapped_column(String(20), default=ACTIVE)
    # The user's local date the pick belongs to, YYYY-MM-DD.
    day: Mapped[str] = mapped_column(String(10))
    fit: Mapped[float] = mapped_column(Float)
    reserved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    card: Mapped[IssueCard] = relationship(lazy="joined")


class RecommendationEvent(Base):
    """Every recommendation shown and what the user did with it, for a learned ranking later."""

    __tablename__ = "recommendation_events"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    repo_full_name: Mapped[str] = mapped_column(String(200))
    number: Mapped[int] = mapped_column(Integer)
    surface: Mapped[str] = mapped_column(String(20))  # daily, explore, issue
    action: Mapped[str] = mapped_column(String(20))  # shown, swapped, opened, github, expired
    fit: Mapped[float | None] = mapped_column(Float)
    parts: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class FeatureInterest(Base):
    """An "I want this" click on a coming-soon feature. One per user and feature."""

    __tablename__ = "feature_interest"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    feature: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def open_session(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
