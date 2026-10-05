"""Shared vocabulary for the engine, CLI, API and web app.

These enums are the values users see (through their labels) and the values
stored in the database, so changing a member's value is a breaking change.
"""

from __future__ import annotations

from enum import StrEnum


class Tier(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    PRO = "pro"

    @property
    def dots(self) -> int:
        """Level is always shown as three dots; this many are filled."""
        return {Tier.BEGINNER: 1, Tier.INTERMEDIATE: 2, Tier.PRO: 3}[self]

    @property
    def label(self) -> str:
        return self.value.capitalize()


class Availability(StrEnum):
    FREE = "free"
    LIKELY_FREE = "likely_free"
    CLAIMED = "claimed"
    HAS_PR = "has_pr"
    NOT_READY = "not_ready"
    UNCLEAR = "unclear"

    @property
    def rankable(self) -> bool:
        """Only free and likely-free issues are ranked (brief 5.7)."""
        return self in (Availability.FREE, Availability.LIKELY_FREE)

    @property
    def label(self) -> str:
        return {
            Availability.FREE: "Free",
            Availability.LIKELY_FREE: "Likely free",
            Availability.CLAIMED: "Claimed",
            Availability.HAS_PR: "Has a PR",
            Availability.NOT_READY: "Not ready",
            Availability.UNCLEAR: "Unclear",
        }[self]


class TimeBucket(StrEnum):
    UNDER_AN_HOUR = "under_an_hour"
    HALF_A_DAY = "half_a_day"
    A_WEEKEND = "a_weekend"
    A_WEEK_OR_MORE = "a_week_or_more"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").capitalize()


class IssueType(StrEnum):
    DOCS = "docs"
    TESTS = "tests"
    BUG = "bug"
    FEATURE = "feature"
    REFACTOR = "refactor"
    CI = "ci"


class PullRequestStatus(StrEnum):
    WAITING_FOR_REVIEW = "waiting_for_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    CI_FAILING = "ci_failing"
    MERGE_CONFLICT = "merge_conflict"
    STALE = "stale"
    MERGED = "merged"
    CLOSED_UNMERGED = "closed_unmerged"

    @property
    def label(self) -> str:
        if self is PullRequestStatus.CI_FAILING:
            return "CI failing"
        return self.value.replace("_", " ").capitalize()

    @property
    def needs_you(self) -> bool:
        """The author has something to do: fix, rebase, or send a nudge when it went quiet.
        Same grouping as the dashboard's "Needs you" and "Gone quiet" columns."""
        return self in {
            PullRequestStatus.CHANGES_REQUESTED,
            PullRequestStatus.CI_FAILING,
            PullRequestStatus.MERGE_CONFLICT,
            PullRequestStatus.STALE,
        }


def level_dots(tier: Tier) -> str:
    """Text form of the three-dot level marker, for terminals and plain text."""
    return "●" * tier.dots + "○" * (3 - tier.dots)
