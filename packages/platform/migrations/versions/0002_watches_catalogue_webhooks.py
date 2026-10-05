"""Roles, watches, the shared catalogue, sync state and webhook deliveries.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="user"))
    op.alter_column("users", "role", server_default=None)
    op.create_table(
        "watches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("repo_full_name", sa.String(200), nullable=False),
        sa.Column("created_at", ts, nullable=False),
        sa.UniqueConstraint("user_id", "repo_full_name"),
    )
    op.create_index("ix_watches_user_id", "watches", ["user_id"])
    op.create_index("ix_watches_repo_full_name", "watches", ["repo_full_name"])
    op.create_table(
        "catalogue_repos",
        sa.Column("full_name", sa.String(200), primary_key=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("added_at", ts, nullable=False),
    )
    op.create_table(
        "repo_syncs",
        sa.Column("full_name", sa.String(200), primary_key=True),
        sa.Column("token_kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column("open_issues", sa.Integer(), nullable=False),
        sa.Column("synced_at", ts, nullable=False),
    )
    op.create_table(
        "webhook_events",
        sa.Column("delivery_id", sa.String(64), primary_key=True),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50)),
        sa.Column("repo_full_name", sa.String(200)),
        sa.Column("sender_github_id", sa.BigInteger()),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("received_at", ts, nullable=False),
        sa.Column("processed_at", ts),
        sa.Column("result", sa.String(200)),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("repo_syncs")
    op.drop_table("catalogue_repos")
    op.drop_table("watches")
    op.drop_column("users", "role")
