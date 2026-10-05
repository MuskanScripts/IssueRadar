"""Maintainers can opt their repo out with .github/firstpr.yml.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

ts = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("catalogue_repos", sa.Column("opted_out_at", ts))
    op.add_column("catalogue_repos", sa.Column("opt_out_checked_at", ts))


def downgrade() -> None:
    op.drop_column("catalogue_repos", "opt_out_checked_at")
    op.drop_column("catalogue_repos", "opted_out_at")
