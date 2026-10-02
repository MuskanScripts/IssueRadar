"""Upgrading a database that already has M1 data must keep the data."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, text

from issueradar.storage import open_database
from issueradar.storage.db import _alembic_config


def test_upgrade_from_0001_keeps_rows(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'old.sqlite').as_posix()}"
    command.upgrade(_alembic_config(url), "0001")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO repos (full_name, topics, stars, forks, open_issues_count, "
                "archived, disabled, is_fork, has_issues) "
                "VALUES ('o/r', '[]', 0, 0, 0, 0, 0, 0, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO pull_requests (github_id, repo_id, number, title, state, "
                "draft, closing_issues, mentioned_issues) "
                "VALUES (1, 1, 1, 't', 'open', 0, '[]', '[]')"
            )
        )
    db = open_database(url)  # upgrades to head
    with db.engine.connect() as conn:
        row = conn.execute(text("SELECT health, frameworks FROM repos")).one()
        assert (row.health, row.frameworks) == ("{}", "[]")
        assert conn.execute(text("SELECT author_is_bot FROM pull_requests")).scalar() == 0


def test_upgrade_keeps_child_rows_with_foreign_keys(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'fk.sqlite').as_posix()}"
    command.upgrade(_alembic_config(url), "0001")
    with create_engine(url).begin() as conn:
        conn.execute(
            text(
                "INSERT INTO repos (full_name, topics, stars, forks, open_issues_count, "
                "archived, disabled, is_fork, has_issues) "
                "VALUES ('o/r', '[]', 0, 0, 0, 0, 0, 0, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO issues (github_id, repo_id, number, title, state, labels, "
                "assignees, comments_count, locked) "
                "VALUES (5, 1, 1, 't', 'open', '[]', '[]', 0, 0)"
            )
        )
    db = open_database(url)
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM issues")).scalar() == 1
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
