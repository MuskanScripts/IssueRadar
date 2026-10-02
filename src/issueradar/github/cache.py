"""ETag cache for conditional REST requests.

GitHub returns ``304 Not Modified`` when a conditional request's ETag still
matches, and (for authenticated requests) a 304 does not count against the
primary rate limit. The cache keeps the last body so a 304 can be answered
locally.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CachedResponse:
    etag: str
    body: str
    link: str | None = None


class EtagCache(Protocol):
    def get(self, key: str) -> CachedResponse | None: ...

    def put(self, key: str, url: str, value: CachedResponse) -> None: ...


class MemoryEtagCache:
    """In-process cache, used by tests and one-off commands."""

    def __init__(self) -> None:
        self._items: dict[str, CachedResponse] = {}

    def get(self, key: str) -> CachedResponse | None:
        return self._items.get(key)

    def put(self, key: str, url: str, value: CachedResponse) -> None:
        self._items[key] = value


def token_fingerprint(token: str | None) -> str:
    """A short, one-way label so cached entries never mix between tokens."""
    if not token:
        return "anon"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
