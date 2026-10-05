"""Workspaces, and holds that were started.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("issue_reservations", sa.Column("started_at", ts))
    op.create_table(
        "workspaces",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("repo_full_name", sa.String(200), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("issue_title", sa.Text(), nullable=False),
        sa.Column("issue_url", sa.String(500)),
        sa.Column("practice", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("help_url", sa.String(500)),
        sa.Column("fork_full_name", sa.String(200)),
        sa.Column("base_branch", sa.String(200)),
        sa.Column("base_sha", sa.String(64)),
        sa.Column("branch", sa.String(200)),
        sa.Column("codespace_name", sa.String(200)),
        sa.Column("codespace_url", sa.String(500)),
        sa.Column("codespace_state", sa.String(40)),
        sa.Column("codespace_checked_at", ts),
        sa.Column("pr_number", sa.Integer()),
        sa.Column("pr_url", sa.String(500)),
        sa.Column("pr_state", sa.String(20)),
        sa.Column("pr_opened_at", ts),
        sa.Column("created_at", ts, nullable=False),
        sa.Column("updated_at", ts, nullable=False),
        sa.UniqueConstraint("user_id", "repo_full_name", "number"),
    )
    op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"])


def downgrade() -> None:
    op.drop_table("workspaces")
    op.drop_column("issue_reservations", "started_at")
