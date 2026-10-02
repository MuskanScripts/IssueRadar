"""Alembic environment. Runs against the connection ``open_database`` passes in."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from issueradar.storage.models import Base

target_metadata = Base.metadata
config = context.config


def run() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _migrate(connection)
        return
    engine = create_engine(config.get_main_option("sqlalchemy.url") or "")
    with engine.begin() as conn:
        _migrate(conn)


def _migrate(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


run()
