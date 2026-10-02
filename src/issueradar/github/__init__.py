"""GitHub access. ``client`` is the only module that sends requests (ADR 0004)."""

from issueradar.github.budget import ApiBudget, BudgetSummary
from issueradar.github.client import GitHubClient, GitHubResponse, token_from_env
from issueradar.github.errors import (
    GitHubError,
    Gone,
    GraphQLQueryError,
    NotFound,
    QuotaExhausted,
    ReadOnlyViolation,
    SecondaryRateLimited,
)

__all__ = [
    "ApiBudget",
    "BudgetSummary",
    "GitHubClient",
    "GitHubError",
    "GitHubResponse",
    "Gone",
    "GraphQLQueryError",
    "NotFound",
    "QuotaExhausted",
    "ReadOnlyViolation",
    "SecondaryRateLimited",
    "token_from_env",
]
