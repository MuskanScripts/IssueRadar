"""Tracked pull requests, notifications and email settings.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)


def _user(primary: bool = False) -> sa.Column[int]:
    return sa.Column(
        "user_id",
        sa.BigInteger(),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=primary,
    )


def upgrade() -> None:
    op.create_table(
        "tracked_pulls",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _user(),
        sa.Column("repo_full_name", sa.String(200), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("merged", sa.Boolean(), nullable=False),
        sa.Column("draft", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("needs_you", sa.Text(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("nudge", sa.Text()),
        sa.Column("days_quiet", sa.Integer(), nullable=False),
        sa.Column("opened_at", ts),
        sa.Column("closed_at", ts),
        sa.Column("timeline", sa.JSON(), nullable=False),
        sa.Column("checked_at", ts, nullable=False),
        sa.Column("changed_at", ts, nullable=False),
        sa.UniqueConstraint("user_id", "repo_full_name", "number"),
    )
    op.create_index("ix_tracked_pulls_user_id", "tracked_pulls", ["user_id"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _user(),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link", sa.String(500)),
        sa.Column("external_url", sa.String(500)),
        sa.Column("dedupe_key", sa.String(300), nullable=False),
        sa.Column("created_at", ts, nullable=False),
        sa.Column("read_at", ts),
        sa.Column("emailed_at", ts),
        sa.UniqueConstraint("user_id", "dedupe_key"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_table(
        "email_prefs",
        _user(primary=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("digest", sa.Boolean(), nullable=False),
        sa.Column("last_digest_day", sa.String(10)),
        sa.Column("updated_at", ts, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_prefs")
    op.drop_table("notifications")
    op.drop_table("tracked_pulls")
