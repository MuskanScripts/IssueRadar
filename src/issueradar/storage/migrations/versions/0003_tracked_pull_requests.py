"""tracked pull requests

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tracked_pull_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("repo_full_name", sa.String(length=200), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("merged", sa.Boolean(), nullable=False),
        sa.Column("draft", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("needs_you", sa.Text(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("nudge", sa.Text(), nullable=True),
        sa.Column("days_quiet", sa.Integer(), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timeline", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "repo_full_name", "number"),
    )
    with op.batch_alter_table("tracked_pull_requests", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_tracked_pull_requests_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("tracked_pull_requests", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tracked_pull_requests_user_id"))

    op.drop_table("tracked_pull_requests")
