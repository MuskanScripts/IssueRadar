from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from issueradar.engine.types import Comment, IssueContext, PrLink

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def days_ago(n: float) -> datetime:
    return NOW - timedelta(days=n)


def issue(**changes: Any) -> IssueContext:
    base: dict[str, Any] = {
        "repo": "o/r",
        "number": 7,
        "title": "Client hangs when the server closes early",
        "body": "Steps to reproduce: run the client and stop the server.",
        "state": "open",
        "labels": [],
        "assignees": [],
        "author": "someone",
        "author_is_bot": False,
        "comments_count": 0,
        "locked": False,
        "created_at": days_ago(10),
        "updated_at": days_ago(2),
        "comments": [],
        "pr_links": [],
        "timeline_checked": True,
        "linked_pr_search_checked": True,
    }
    base.update(changes)
    return IssueContext(**base)


def comment(
    body: str, *, by: str = "dev", assoc: str = "NONE", age: float = 1, bot: bool = False
) -> Comment:
    return Comment(author=by, association=assoc, body=body, created_at=days_ago(age), is_bot=bot)


def pr(
    number: int, *, state: str = "open", source: str = "closing_reference", bot: bool = False
) -> PrLink:
    return PrLink(number=number, state=state, source=source, is_bot=bot)
