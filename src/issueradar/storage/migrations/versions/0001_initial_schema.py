"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "http_cache",
        sa.Column("key", sa.String(length=600), nullable=False),
        sa.Column("url", sa.String(length=600), nullable=False),
        sa.Column("etag", sa.String(length=200), nullable=False),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "repos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("forks", sa.Integer(), nullable=False),
        sa.Column("open_issues_count", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("is_fork", sa.Boolean(), nullable=False),
        sa.Column("has_issues", sa.Boolean(), nullable=False),
        sa.Column("default_branch", sa.String(length=200), nullable=True),
        sa.Column("html_url", sa.String(length=500), nullable=True),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gh_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gh_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("full_name"),
        sa.UniqueConstraint("github_id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=100), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login"),
    )
    op.create_table(
        "digest_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("digest_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_digest_runs_user_id"), ["user_id"], unique=False)

    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("state_reason", sa.String(length=40), nullable=True),
        sa.Column("author_login", sa.String(length=100), nullable=True),
        sa.Column("author_type", sa.String(length=40), nullable=True),
        sa.Column("author_association", sa.String(length=40), nullable=True),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("assignees", sa.JSON(), nullable=False),
        sa.Column("comments_count", sa.Integer(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("html_url", sa.String(length=500), nullable=True),
        sa.Column("gh_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gh_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_open_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_id"),
        sa.UniqueConstraint("repo_id", "number"),
    )
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_issues_repo_id"), ["repo_id"], unique=False)

    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("draft", sa.Boolean(), nullable=False),
        sa.Column("author_login", sa.String(length=100), nullable=True),
        sa.Column("author_association", sa.String(length=40), nullable=True),
        sa.Column("html_url", sa.String(length=500), nullable=True),
        sa.Column("closing_issues", sa.JSON(), nullable=False),
        sa.Column("mentioned_issues", sa.JSON(), nullable=False),
        sa.Column("gh_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gh_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_open_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_id"),
        sa.UniqueConstraint("repo_id", "number"),
    )
    with op.batch_alter_table("pull_requests", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pull_requests_repo_id"), ["repo_id"], unique=False)

    op.create_table(
        "repo_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("repo_full_name", sa.String(length=200), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "repo_full_name"),
    )
    op.create_table(
        "seen_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_kind", sa.String(length=20), nullable=False),
        sa.Column("item_key", sa.String(length=300), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "item_kind", "item_key"),
    )
    with op.batch_alter_table("seen_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_seen_items_user_id"), ["user_id"], unique=False)

    op.create_table(
        "skill_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("technology", sa.String(length=100), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "technology"),
    )
    with op.batch_alter_table("skill_profiles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_skill_profiles_user_id"), ["user_id"], unique=False)

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repos_planned", sa.JSON(), nullable=False),
        sa.Column("repos_done", sa.JSON(), nullable=False),
        sa.Column("repos_failed", sa.JSON(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("not_modified", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sync_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sync_runs_user_id"), ["user_id"], unique=False)

    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("repo_full_name", sa.String(length=200), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "repo_full_name"),
    )
    with op.batch_alter_table("watchlists", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_watchlists_user_id"), ["user_id"], unique=False)

    op.create_table(
        "difficulty_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("difficulty_feedback", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_difficulty_feedback_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "issue_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("author_login", sa.String(length=100), nullable=True),
        sa.Column("author_association", sa.String(length=40), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("gh_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_id", "kind", "source_id"),
    )
    with op.batch_alter_table("issue_signals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_issue_signals_issue_id"), ["issue_id"], unique=False)

    op.create_table(
        "score_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=True),
        sa.Column("difficulty_score", sa.Integer(), nullable=True),
        sa.Column("health_score", sa.Integer(), nullable=True),
        sa.Column("rank_score", sa.Double(), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("score_snapshots", schema=None) as batch_op:
        batch_op.create_index(
            "ix_score_snapshots_user_issue", ["user_id", "issue_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("score_snapshots", schema=None) as batch_op:
        batch_op.drop_index("ix_score_snapshots_user_issue")

    op.drop_table("score_snapshots")
    with op.batch_alter_table("issue_signals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_issue_signals_issue_id"))

    op.drop_table("issue_signals")
    with op.batch_alter_table("difficulty_feedback", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_difficulty_feedback_user_id"))

    op.drop_table("difficulty_feedback")
    with op.batch_alter_table("watchlists", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_watchlists_user_id"))

    op.drop_table("watchlists")
    with op.batch_alter_table("sync_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sync_runs_user_id"))

    op.drop_table("sync_runs")
    with op.batch_alter_table("skill_profiles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_skill_profiles_user_id"))

    op.drop_table("skill_profiles")
    with op.batch_alter_table("seen_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_seen_items_user_id"))

    op.drop_table("seen_items")
    op.drop_table("repo_rules")
    with op.batch_alter_table("pull_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pull_requests_repo_id"))

    op.drop_table("pull_requests")
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_issues_repo_id"))

    op.drop_table("issues")
    with op.batch_alter_table("digest_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_digest_runs_user_id"))

    op.drop_table("digest_runs")
    op.drop_table("users")
    op.drop_table("repos")
    op.drop_table("http_cache")
