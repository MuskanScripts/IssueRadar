from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from issueradar.storage.db import open_database
from issueradar.storage.models import Repo


def test_text_columns_drop_nul_characters(tmp_path: Path) -> None:
    db = open_database(f"sqlite:///{tmp_path / 'nul.db'}")
    with db.sessions.begin() as session:
        session.add(Repo(full_name="a/b", description="fast\x00 tool"))
    with db.sessions() as session:
        assert session.scalar(select(Repo.description)) == "fast tool"
