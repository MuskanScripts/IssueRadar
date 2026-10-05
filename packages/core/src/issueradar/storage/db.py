"""Engine, sessions and schema migrations.

SQLite is the default. Any SQLAlchemy URL works (Postgres in hosted mode).
The schema is managed by Alembic; ``open_database`` upgrades it to the latest
revision every time, so users never run migrations by hand.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from alembic import command
from alembic.config import Config
from platformdirs import user_data_dir
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from issueradar.brand import BRAND
from issueradar.config.settings import Settings
from issueradar.storage.models import LOCAL_USER_ID, User


def default_database_url() -> str:
    folder = Path(user_data_dir(BRAND.cli, appauthor=False))
    folder.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(folder / f'{BRAND.cli}.sqlite').as_posix()}"


def resolve_database_url(settings: Settings, env: dict[str, str] | None = None) -> str:
    env = dict(os.environ) if env is None else env
    return env.get(BRAND.env("DB_URL")) or settings.storage.url or default_database_url()


def _alembic_config(url: str) -> Config:
    config = Config()
    config.set_main_option(
        "script_location", str(files("issueradar.storage").joinpath("migrations"))
    )
    config.set_main_option("sqlalchemy.url", url)
    return config


def _sqlite_pragmas(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


@dataclass
class Database:
    url: str
    engine: Engine
    sessions: sessionmaker[Session]


def open_database(url: str) -> Database:
    """Create the engine, upgrade the schema, and make sure the local user exists."""
    engine = create_engine(url)
    _sqlite_pragmas(engine)
    config = _alembic_config(url)
    with engine.connect() as connection:
        sqlite = engine.dialect.name == "sqlite"
        if sqlite:
            # SQLite migrations rebuild tables. With foreign keys on, rebuilding a
            # parent table cascades deletes into its children, so switch them off
            # while migrating (as SQLite's docs recommend) and back on after.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as session:
        if session.scalar(select(User).where(User.id == LOCAL_USER_ID)) is None:
            session.add(User(id=LOCAL_USER_ID, login=None))
    return Database(url=url, engine=engine, sessions=sessions)
