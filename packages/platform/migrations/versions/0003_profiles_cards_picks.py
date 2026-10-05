"""Profiles and skills, issue cards, daily picks, recommendation logs, feature interest.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)


def _user_fk() -> sa.Column[int]:
    return sa.Column(
        "user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("packs", sa.JSON(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("onboarded_at", ts),
        sa.Column("updated_at", ts, nullable=False),
    )
    op.create_table(
        "user_skills",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _user_fk(),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.UniqueConstraint("user_id", "kind", "name"),
    )
    op.create_index("ix_user_skills_user_id", "user_skills", ["user_id"])
    op.create_table(
        "issue_cards",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("repo_full_name", sa.String(200), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("repo_description", sa.Text()),
        sa.Column("language", sa.String(100)),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("frameworks", sa.JSON(), nullable=False),
        sa.Column("domains", sa.JSON(), nullable=False),
        sa.Column("paths", sa.JSON(), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Integer(), nullable=False),
        sa.Column("opened_at", ts),
        sa.Column("updated_at", ts),
        sa.Column("availability", sa.String(20), nullable=False),
        sa.Column("availability_reasons", sa.JSON(), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("difficulty_score", sa.Integer(), nullable=False),
        sa.Column("time_bucket", sa.String(30), nullable=False),
        sa.Column("issue_type", sa.String(20), nullable=False),
        sa.Column("difficulty_reasons", sa.JSON(), nullable=False),
        sa.Column("discussion_first", sa.Boolean(), nullable=False),
        sa.Column("health", sa.Integer()),
        sa.Column("health_reasons", sa.JSON(), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("repo_notes", sa.Text()),
        sa.Column("changed_at", ts, nullable=False),
        sa.Column("refreshed_at", ts, nullable=False),
        sa.UniqueConstraint("repo_full_name", "number"),
    )
    op.create_index("ix_issue_cards_repo_full_name", "issue_cards", ["repo_full_name"])
    op.create_index("ix_issue_cards_availability", "issue_cards", ["availability"])
    op.create_table(
        "issue_reservations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _user_fk(),
        sa.Column(
            "card_id",
            sa.BigInteger(),
            sa.ForeignKey("issue_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("fit", sa.Float(), nullable=False),
        sa.Column("reserved_at", ts, nullable=False),
        sa.Column("expires_at", ts, nullable=False),
        sa.Column("ended_at", ts),
    )
    op.create_index("ix_issue_reservations_user_id", "issue_reservations", ["user_id"])
    # One active hold per issue: two people never get the same pick.
    op.create_index(
        "uq_issue_reservations_active",
        "issue_reservations",
        ["card_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "recommendation_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _user_fk(),
        sa.Column("repo_full_name", sa.String(200), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("surface", sa.String(20), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("fit", sa.Float()),
        sa.Column("parts", sa.JSON(), nullable=False),
        sa.Column("created_at", ts, nullable=False),
    )
    op.create_index("ix_recommendation_events_user_id", "recommendation_events", ["user_id"])
    op.create_table(
        "feature_interest",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("feature", sa.String(40), primary_key=True),
        sa.Column("created_at", ts, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feature_interest")
    op.drop_table("recommendation_events")
    op.drop_table("issue_reservations")
    op.drop_table("issue_cards")
    op.drop_table("user_skills")
    op.drop_table("profiles")
