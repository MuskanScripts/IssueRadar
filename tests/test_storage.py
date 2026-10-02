from __future__ import annotations

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from issueradar.storage import Database, open_database
from issueradar.storage.models import LOCAL_USER_ID, Base, User

PERSONAL_TABLES = {
    "skill_profiles",
    "watchlists",
    "digest_runs",
    "seen_items",
    "difficulty_feedback",
    "score_snapshots",
    "sync_runs",
    "repo_rules",
}


def test_every_table_in_the_brief_exists(db: Database) -> None:
    tables = set(inspect(db.engine).get_table_names())
    brief = {
        "repos",
        "issues",
        "issue_signals",
        "pull_requests",
        "users",
        "skill_profiles",
        "watchlists",
        "repo_rules",
        "digest_runs",
        "seen_items",
        "difficulty_feedback",
        "score_snapshots",
    }
    assert brief <= tables


def test_personal_tables_have_user_id(db: Database) -> None:
    inspector = inspect(db.engine)
    for table in PERSONAL_TABLES:
        columns = {c["name"] for c in inspector.get_columns(table)}
        assert "user_id" in columns, table


def test_migrations_match_the_models(db: Database) -> None:
    with db.engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == [], "models changed without a migration; generate one with alembic"


def test_local_user_exists_and_reopening_is_safe(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'again.sqlite').as_posix()}"
    open_database(url)
    db = open_database(url)
    with db.sessions() as session:
        assert session.get(User, LOCAL_USER_ID) is not None
