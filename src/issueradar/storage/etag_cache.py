"""ETag cache stored in the database, so savings carry over between runs."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from issueradar.github.cache import CachedResponse
from issueradar.storage.models import HttpCacheEntry, utcnow


class SqlEtagCache:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get(self, key: str) -> CachedResponse | None:
        with self._sessions() as session:
            entry = session.get(HttpCacheEntry, key)
            if entry is None:
                return None
            return CachedResponse(etag=entry.etag, body=entry.body, link=entry.link)

    def put(self, key: str, url: str, value: CachedResponse) -> None:
        with self._sessions.begin() as session:
            entry = session.get(HttpCacheEntry, key)
            if entry is None:
                session.add(
                    HttpCacheEntry(
                        key=key, url=url, etag=value.etag, link=value.link, body=value.body
                    )
                )
            else:
                entry.etag = value.etag
                entry.link = value.link
                entry.body = value.body
                entry.stored_at = utcnow()
