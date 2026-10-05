"""XP, badges, daily activity, Codespace run times, public profiles.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
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
    op.add_column("users", sa.Column("xp", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("users", "xp", server_default=None)
    op.add_column(
        "profiles", sa.Column("public", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.alter_column("profiles", "public", server_default=None)
    op.add_column("workspaces", sa.Column("codespace_up_since", ts))
    op.add_column("workspaces", sa.Column("codespace_up_last", ts))
    op.add_column(
        "workspaces", sa.Column("counted_commits", sa.JSON(), nullable=False, server_default="[]")
    )
    op.alter_column("workspaces", "counted_commits", server_default=None)
    op.create_table(
        "xp_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _user(),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("note", sa.String(300), nullable=False),
        sa.Column("created_at", ts, nullable=False),
        sa.UniqueConstraint("user_id", "source"),
    )
    op.create_index("ix_xp_transactions_user_id", "xp_transactions", ["user_id"])
    op.create_table(
        "user_badges",
        _user(primary=True),
        sa.Column("badge", sa.String(40), primary_key=True),
        sa.Column("earned_at", ts, nullable=False),
    )
    op.create_table(
        "daily_activity",
        _user(primary=True),
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("web_minutes", sa.Integer(), nullable=False),
        sa.Column("codespace_minutes", sa.Integer(), nullable=False),
        sa.Column("commits", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("daily_activity")
    op.drop_table("user_badges")
    op.drop_table("xp_transactions")
    op.drop_column("workspaces", "counted_commits")
    op.drop_column("workspaces", "codespace_up_last")
    op.drop_column("workspaces", "codespace_up_since")
    op.drop_column("profiles", "public")
    op.drop_column("users", "xp")
