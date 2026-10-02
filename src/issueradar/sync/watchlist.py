"""Add, remove and list watched repositories for a user."""

from __future__ import annotations

import re

from sqlalchemy import delete, select

from issueradar.storage.db import Database
from issueradar.storage.models import LOCAL_USER_ID, Watchlist

_REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_URL = re.compile(r"^https?://github\.com/([^/\s]+/[^/\s#?]+?)(?:\.git)?/?$")


class WatchlistError(ValueError):
    pass


def normalise_repo(value: str) -> str:
    """Accept ``owner/name`` or a github.com URL; return ``owner/name``."""
    text = value.strip()
    match = _URL.match(text)
    if match:
        text = match.group(1)
    if not _REPO.match(text):
        raise WatchlistError(
            f"'{value}' is not a repository. Use owner/name, for example "
            "modelcontextprotocol/python-sdk."
        )
    return text


def add(db: Database, repo: str, user_id: int = LOCAL_USER_ID) -> tuple[str, bool]:
    name = normalise_repo(repo)
    with db.sessions.begin() as session:
        existing = session.scalar(
            select(Watchlist).where(
                Watchlist.user_id == user_id, Watchlist.repo_full_name.ilike(name)
            )
        )
        if existing is not None:
            return existing.repo_full_name, False
        session.add(Watchlist(user_id=user_id, repo_full_name=name))
    return name, True


def remove(db: Database, repo: str, user_id: int = LOCAL_USER_ID) -> bool:
    name = normalise_repo(repo)
    with db.sessions.begin() as session:
        result = session.execute(
            delete(Watchlist).where(
                Watchlist.user_id == user_id, Watchlist.repo_full_name.ilike(name)
            )
        )
        return bool(getattr(result, "rowcount", 0))


def list_watched(db: Database, user_id: int = LOCAL_USER_ID) -> list[str]:
    with db.sessions() as session:
        return list(
            session.scalars(
                select(Watchlist.repo_full_name)
                .where(Watchlist.user_id == user_id)
                .order_by(Watchlist.added_at, Watchlist.id)
            )
        )
