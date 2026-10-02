"""Turn GitHub REST JSON into the fields we store. Pure functions, easy to test."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# "#123", "owner/repo#123" and full issue URLs, as written in PR titles and bodies.
_REF = (
    r"(?:https://github\.com/(?P<urlrepo>[\w.-]+/[\w.-]+)/issues/(?P<urlnum>\d+)"
    r"|(?<![\w/])(?:(?P<repo>[\w.-]+/[\w.-]+))?#(?P<num>\d+)\b)"
)
_ANY_REF = re.compile(_REF)
# GitHub's closing keywords: https://docs.github.com/issues/tracking-your-work-with-issues
_CLOSING_REF = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+" + _REF, re.IGNORECASE
)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def repo_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "github_id": data["id"],
        "full_name": data["full_name"],
        "description": data.get("description"),
        "language": data.get("language"),
        "topics": list(data.get("topics") or []),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "open_issues_count": data.get("open_issues_count", 0),
        "archived": bool(data.get("archived")),
        "disabled": bool(data.get("disabled")),
        "is_fork": bool(data.get("fork")),
        "has_issues": bool(data.get("has_issues", True)),
        "default_branch": data.get("default_branch"),
        "html_url": data.get("html_url"),
        "pushed_at": parse_time(data.get("pushed_at")),
        "gh_created_at": parse_time(data.get("created_at")),
        "gh_updated_at": parse_time(data.get("updated_at")),
    }


def is_pull_request(item: dict[str, Any]) -> bool:
    """The issues endpoints also return pull requests; they carry a ``pull_request`` key."""
    return "pull_request" in item


def issue_fields(data: dict[str, Any]) -> dict[str, Any]:
    user = data.get("user") or {}
    return {
        "github_id": data["id"],
        "number": data["number"],
        "title": data.get("title") or "",
        "body": data.get("body"),
        "state": data.get("state", "open"),
        "state_reason": data.get("state_reason"),
        "author_login": user.get("login"),
        "author_type": user.get("type"),
        "author_association": data.get("author_association"),
        "labels": [
            label["name"] if isinstance(label, dict) else str(label)
            for label in data.get("labels") or []
        ],
        "assignees": [a["login"] for a in data.get("assignees") or [] if a and "login" in a],
        "comments_count": data.get("comments", 0),
        "locked": bool(data.get("locked")),
        "html_url": data.get("html_url"),
        "gh_created_at": parse_time(data.get("created_at")),
        "gh_updated_at": parse_time(data.get("updated_at")),
        "closed_at": parse_time(data.get("closed_at")),
    }


def _refs(pattern: re.Pattern[str], text: str, own: str) -> set[int]:
    found: set[int] = set()
    for match in pattern.finditer(text):
        repo = match.group("urlrepo") or match.group("repo")
        number = match.group("urlnum") or match.group("num")
        if repo is None or repo.lower() == own:
            found.add(int(number))
    return found


def referenced_issues(text: str, repo_full_name: str) -> tuple[list[int], list[int]]:
    """Issue numbers in this repo that a PR points at: (closing, mentioned).

    ``closing`` uses GitHub's closing keywords ("fixes #12") and is a strong
    signal. ``mentioned`` is every other reference and is weak: on real data,
    copied release notes produce many unrelated numbers (see RESULTS.md).
    """
    own = repo_full_name.lower()
    closing = _refs(_CLOSING_REF, text, own)
    mentioned = _refs(_ANY_REF, text, own) - closing
    return sorted(closing), sorted(mentioned)


def is_bot(user: dict[str, Any]) -> bool:
    return user.get("type") == "Bot" or str(user.get("login", "")).endswith("[bot]")


def pull_request_fields(data: dict[str, Any], repo_full_name: str) -> dict[str, Any]:
    user = data.get("user") or {}
    # Bot PRs (Dependabot, Renovate) paste upstream release notes into the body,
    # full of other projects' issue numbers. Only their title is scanned.
    body = "" if is_bot(user) else (data.get("body") or "")
    closing, mentioned = referenced_issues(f"{data.get('title') or ''}\n{body}", repo_full_name)
    return {
        "github_id": data["id"],
        "number": data["number"],
        "title": data.get("title") or "",
        "body": data.get("body"),
        "state": data.get("state", "open"),
        "draft": bool(data.get("draft")),
        "author_login": user.get("login"),
        "author_association": data.get("author_association"),
        "html_url": data.get("html_url"),
        "closing_issues": closing,
        "mentioned_issues": mentioned,
        "gh_created_at": parse_time(data.get("created_at")),
        "gh_updated_at": parse_time(data.get("updated_at")),
        "closed_at": parse_time(data.get("closed_at")),
        "merged_at": parse_time(data.get("merged_at")),
    }
