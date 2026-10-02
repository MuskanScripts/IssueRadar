"""Errors raised by the GitHub client. Each one says what happened in plain words."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class GitHubError(Exception):
    """Base class for every GitHub client error."""


class ReadOnlyViolation(GitHubError):
    """Something tried to write to GitHub, which this project never does (ADR 0004)."""


class QuotaExhausted(GitHubError):
    """The primary rate limit for a resource is used up (or inside the safety margin)."""

    def __init__(self, resource: str, reset_at: float | None) -> None:
        self.resource = resource
        self.reset_at = reset_at
        when = (
            datetime.fromtimestamp(reset_at, tz=UTC).strftime("%H:%M UTC")
            if reset_at
            else "the next reset"
        )
        super().__init__(
            f"GitHub API budget for '{resource}' is used up. It resets at {when}; "
            "run the command again after that and it will pick up where it stopped."
        )


class SecondaryRateLimited(GitHubError):
    """GitHub kept answering with a secondary rate limit after every retry."""


class NotFound(GitHubError):
    """404: the repository or issue does not exist, or the token cannot see it."""


class Gone(GitHubError):
    """410: the resource was deleted, or issues are disabled for the repository."""


class GitHubHTTPError(GitHubError):
    """Any other unexpected HTTP status."""

    def __init__(self, status: int, message: str, url: str) -> None:
        self.status = status
        self.url = url
        super().__init__(f"GitHub returned {status} for {url}: {message}")


class GraphQLQueryError(GitHubError):
    """A GraphQL response came back with an ``errors`` array (often with HTTP 200)."""

    def __init__(self, errors: list[dict[str, Any]], data: Any = None) -> None:
        self.errors = errors
        self.data = data
        first = errors[0].get("message", "unknown error") if errors else "unknown error"
        super().__init__(f"GraphQL query failed: {first}")


class GraphQLTimeout(GitHubError):
    """GitHub stopped a GraphQL query after its server-side time limit."""
