"""Bring the platform database up to date: `python -m firstpr_platform.migrate`.

Uses FIRSTPR_DATABASE_URL. The API container runs this before it starts.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_ini() -> Path:
    here = Path(__file__).resolve().parent
    packaged = here / "alembic.ini"  # inside an installed wheel
    return packaged if packaged.is_file() else here.parents[1] / "alembic.ini"


def upgrade(revision: str = "head") -> None:
    command.upgrade(Config(str(alembic_ini())), revision)


if __name__ == "__main__":
    upgrade()
