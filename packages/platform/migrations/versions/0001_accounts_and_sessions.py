"""Users, their GitHub accounts and sessions.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("handle", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("email", sa.String(320)),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("created_at", ts, nullable=False),
        sa.Column("updated_at", ts, nullable=False),
    )
    op.create_table(
        "github_accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("access_token", sa.LargeBinary(), nullable=False),
        sa.Column("access_expires_at", ts),
        sa.Column("refresh_token", sa.LargeBinary()),
        sa.Column("refresh_expires_at", ts),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("last_verified_at", ts),
        sa.Column("created_at", ts, nullable=False),
        sa.Column("updated_at", ts, nullable=False),
        sa.UniqueConstraint("github_id"),
    )
    op.create_index("ix_github_accounts_user_id", "github_accounts", ["user_id"], unique=True)
    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", ts, nullable=False),
        sa.Column("last_seen_at", ts, nullable=False),
        sa.Column("expires_at", ts, nullable=False),
        sa.Column("revoked_at", ts),
        sa.Column("user_agent", sa.String(200)),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("github_accounts")
    op.drop_table("users")
