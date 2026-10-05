"""Inputs shared by the engines. Built from the database or from a live fetch.

Engines are pure functions of these inputs plus settings, so every result can
be reproduced and tested without GitHub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Comment:
    author: str | None
    association: str | None
    body: str
    created_at: datetime
    is_bot: bool = False


@dataclass(frozen=True)
class PrLink:
    """A pull request connected to an issue, and how we learned about it."""

    number: int
    state: str  # open, closed, merged
    source: str  # closing_reference, mention, timeline, connected, search
    is_bot: bool = False
    repo: str | None = None


@dataclass
class IssueContext:
    repo: str
    number: int
    title: str
    body: str
    state: str
    labels: list[str]
    assignees: list[str]
    author: str | None
    author_is_bot: bool
    comments_count: int
    locked: bool
    created_at: datetime | None
    updated_at: datetime | None
    html_url: str | None = None
    comments: list[Comment] | None = None  # None: not fetched
    pr_links: list[PrLink] = field(default_factory=list)
    timeline_checked: bool = False
    linked_pr_search_checked: bool = False


@dataclass(frozen=True)
class Reason:
    """One line of "why". ``effect`` is shown next to it (for example "+10")."""

    text: str
    effect: str | None = None

    def __str__(self) -> str:
        return f"{self.text} ({self.effect})" if self.effect else self.text
