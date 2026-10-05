"""Alembic environment: runs migrations with a plain (sync) connection."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

from firstpr_platform.db import Base, database_url

DEFAULT_URL = "postgresql+psycopg://firstpr:firstpr@localhost:5432/firstpr"

target_metadata = Base.metadata


def run() -> None:
    url = (
        context.config.get_main_option("sqlalchemy.url")
        or os.environ.get("FIRSTPR_DATABASE_URL")
        or DEFAULT_URL
    )
    engine = create_engine(database_url(url), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline migrations are not used; run against a database.")
run()
