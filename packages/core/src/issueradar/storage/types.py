"""Column types for text that comes from GitHub."""

from __future__ import annotations

from typing import Any

from sqlalchemy import String, Text, TypeDecorator


def _without_nul(value: Any) -> Any:
    # GitHub accepts NUL characters in issue and comment text; PostgreSQL text
    # columns refuse them, and one such issue would fail a whole sync.
    return value.replace("\x00", "") if isinstance(value, str) else value


class SafeText(TypeDecorator[str]):
    """Text with NUL characters dropped on the way in."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return _without_nul(value)


class SafeString(TypeDecorator[str]):
    """A length-limited string with NUL characters dropped on the way in."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return _without_nul(value)
