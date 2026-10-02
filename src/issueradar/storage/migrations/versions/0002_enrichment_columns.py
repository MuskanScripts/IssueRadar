"""Enrichment columns (existing rows get empty defaults)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("linked_pr", sa.Boolean(), nullable=True))
        batch_op.add_column(
            sa.Column("comments_fetched_for", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("timeline_checked_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("pull_requests", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "author_is_bot", sa.Boolean(), nullable=False, server_default=sa.text("false")
            )
        )
        batch_op.add_column(
            sa.Column("labels", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )

    with op.batch_alter_table("repos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("languages", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.add_column(
            sa.Column("frameworks", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch_op.add_column(
            sa.Column("community", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.add_column(sa.Column("contributing_text", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("health", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch_op.add_column(
            sa.Column("health_computed_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("repos", schema=None) as batch_op:
        batch_op.drop_column("health_computed_at")
        batch_op.drop_column("health")
        batch_op.drop_column("contributing_text")
        batch_op.drop_column("community")
        batch_op.drop_column("frameworks")
        batch_op.drop_column("languages")

    with op.batch_alter_table("pull_requests", schema=None) as batch_op:
        batch_op.drop_column("labels")
        batch_op.drop_column("author_is_bot")

    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_column("timeline_checked_at")
        batch_op.drop_column("comments_fetched_for")
        batch_op.drop_column("linked_pr")
