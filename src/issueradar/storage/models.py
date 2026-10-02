"""Database tables (brief section 5.2).

Shared tables (repos, issues, signals, pull requests, HTTP cache) hold public
GitHub data that every user can share. Personal tables carry ``user_id`` from
day one, even in single-user mode, where the only user is ``LOCAL_USER_ID``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

LOCAL_USER_ID = 1


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything we store is UTC."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012 (SQLAlchemy reads this class attribute)
        dict[str, Any]: JSON,
        list[Any]: JSON,
        datetime: DateTime(timezone=True),
    }


# --------------------------------------------------------------------- shared


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100))
    topics: Mapped[list[Any]] = mapped_column(default=list)
    stars: Mapped[int] = mapped_column(default=0)
    forks: Mapped[int] = mapped_column(default=0)
    open_issues_count: Mapped[int] = mapped_column(default=0)
    archived: Mapped[bool] = mapped_column(default=False)
    disabled: Mapped[bool] = mapped_column(default=False)
    is_fork: Mapped[bool] = mapped_column(default=False)
    has_issues: Mapped[bool] = mapped_column(default=True)
    default_branch: Mapped[str | None] = mapped_column(String(200))
    html_url: Mapped[str | None] = mapped_column(String(500))
    pushed_at: Mapped[datetime | None]
    gh_created_at: Mapped[datetime | None]
    gh_updated_at: Mapped[datetime | None]
    last_synced_at: Mapped[datetime | None]
    sync_error: Mapped[str | None] = mapped_column(Text)
    # Enrichment (M2): stack, contributor docs and the cached health result.
    languages: Mapped[dict[str, Any]] = mapped_column(default=dict)
    frameworks: Mapped[list[Any]] = mapped_column(default=list)
    community: Mapped[dict[str, Any]] = mapped_column(default=dict)
    contributing_text: Mapped[str | None] = mapped_column(Text)
    health: Mapped[dict[str, Any]] = mapped_column(default=dict)
    health_computed_at: Mapped[datetime | None]

    issues: Mapped[list[Issue]] = relationship(back_populates="repo")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (UniqueConstraint("repo_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), index=True)
    number: Mapped[int]
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20))
    state_reason: Mapped[str | None] = mapped_column(String(40))
    author_login: Mapped[str | None] = mapped_column(String(100))
    author_type: Mapped[str | None] = mapped_column(String(40))
    author_association: Mapped[str | None] = mapped_column(String(40))
    labels: Mapped[list[Any]] = mapped_column(default=list)
    assignees: Mapped[list[Any]] = mapped_column(default=list)
    comments_count: Mapped[int] = mapped_column(default=0)
    locked: Mapped[bool] = mapped_column(default=False)
    html_url: Mapped[str | None] = mapped_column(String(500))
    gh_created_at: Mapped[datetime | None]
    gh_updated_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    last_seen_open_at: Mapped[datetime | None]
    # Enrichment (M2). None means "not checked".
    linked_pr: Mapped[bool | None]
    comments_fetched_for: Mapped[datetime | None]  # gh_updated_at when comments were read
    timeline_checked_at: Mapped[datetime | None]

    repo: Mapped[Repo] = relationship(back_populates="issues")


class IssueSignal(Base):
    """Comments, label events and cross-references collected for finalists (M2)."""

    __tablename__ = "issue_signals"
    __table_args__ = (UniqueConstraint("issue_id", "kind", "source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(100))
    author_login: Mapped[str | None] = mapped_column(String(100))
    author_association: Mapped[str | None] = mapped_column(String(40))
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    gh_created_at: Mapped[datetime | None]


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repo_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), index=True)
    number: Mapped[int]
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20))
    draft: Mapped[bool] = mapped_column(default=False)
    author_login: Mapped[str | None] = mapped_column(String(100))
    author_association: Mapped[str | None] = mapped_column(String(40))
    author_is_bot: Mapped[bool] = mapped_column(default=False)
    labels: Mapped[list[Any]] = mapped_column(default=list)
    html_url: Mapped[str | None] = mapped_column(String(500))
    closing_issues: Mapped[list[Any]] = mapped_column(default=list)  # "fixes #12": strong
    mentioned_issues: Mapped[list[Any]] = mapped_column(default=list)  # any other "#12": weak
    gh_created_at: Mapped[datetime | None]
    gh_updated_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    merged_at: Mapped[datetime | None]
    last_seen_open_at: Mapped[datetime | None]


class HttpCacheEntry(Base):
    """ETag cache. ``key`` includes a one-way token fingerprint, never the token."""

    __tablename__ = "http_cache"

    key: Mapped[str] = mapped_column(String(600), primary_key=True)
    url: Mapped[str] = mapped_column(String(600))
    etag: Mapped[str] = mapped_column(String(200))
    link: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    stored_at: Mapped[datetime] = mapped_column(default=utcnow)


# ------------------------------------------------------------------- personal


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str | None] = mapped_column(String(100), unique=True)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class SkillProfile(Base):
    __tablename__ = "skill_profiles"
    __table_args__ = (UniqueConstraint("user_id", "kind", "technology"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # language, framework, domain
    technology: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(20))  # learning, medium, strong


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "repo_full_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    repo_full_name: Mapped[str] = mapped_column(String(200))
    added_at: Mapped[datetime] = mapped_column(default=utcnow)


class RepoRule(Base):
    """Per-repo rules. ``user_id`` NULL means a shared preset; set means a personal override."""

    __tablename__ = "repo_rules"
    __table_args__ = (UniqueConstraint("user_id", "repo_full_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    repo_full_name: Mapped[str] = mapped_column(String(200))
    rules: Mapped[dict[str, Any]] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)


class SyncRun(Base):
    """One ``sync``. An interrupted run is continued by the next ``sync``."""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20))  # running, interrupted, completed
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]
    repos_planned: Mapped[list[Any]] = mapped_column(default=list)
    repos_done: Mapped[list[Any]] = mapped_column(default=list)
    repos_failed: Mapped[dict[str, Any]] = mapped_column(default=dict)
    requests: Mapped[int] = mapped_column(default=0)
    not_modified: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(Text)


class DigestRun(Base):
    __tablename__ = "digest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]
    items: Mapped[list[Any]] = mapped_column(default=list)


class SeenItem(Base):
    __tablename__ = "seen_items"
    __table_args__ = (UniqueConstraint("user_id", "item_kind", "item_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_kind: Mapped[str] = mapped_column(String(20))  # issue, pull_request
    item_key: Mapped[str] = mapped_column(String(300))  # owner/repo#number
    state: Mapped[str] = mapped_column(String(20))  # shown, dismissed, snoozed
    state_hash: Mapped[str | None] = mapped_column(String(64))
    snoozed_until: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)


class DifficultyFeedback(Base):
    __tablename__ = "difficulty_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"))
    verdict: Mapped[str] = mapped_column(String(20))  # harder, easier, about_right
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"
    __table_args__ = (Index("ix_score_snapshots_user_issue", "user_id", "issue_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"))
    computed_at: Mapped[datetime] = mapped_column(default=utcnow)
    availability: Mapped[str] = mapped_column(String(20))
    tier: Mapped[str | None] = mapped_column(String(20))
    difficulty_score: Mapped[int | None]
    health_score: Mapped[int | None]
    rank_score: Mapped[float | None]
    reasons: Mapped[dict[str, Any]] = mapped_column(default=dict)
