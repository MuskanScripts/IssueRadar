"""Pull request status (brief 5.9), derived from REST data. Pure functions.

Order for an open PR, first match wins:
1. merge conflict   mergeable is false, or mergeable_state is "dirty"
2. CI failing       a check run failed, or the combined status is failure/error
3. changes requested  a reviewer's latest review is CHANGES_REQUESTED
4. approved         a reviewer's latest review is APPROVED (and nobody requests changes)
5. stale            nobody else has done anything for ``stale_days``
6. waiting for review

Closed PRs are merged, accepted by a bot import (per repo rules), or closed unmerged.
GitHub reports ``mergeable: null`` while it is still computing; that is never
treated as a conflict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from issueradar.models import PullRequestStatus

FAILED_CHECKS = {"failure", "timed_out", "action_required", "startup_failure"}
FAILED_STATUS = {"failure", "error"}
PRIORITY = {
    PullRequestStatus.CHANGES_REQUESTED: 0,
    PullRequestStatus.CI_FAILING: 1,
    PullRequestStatus.MERGE_CONFLICT: 2,
    PullRequestStatus.STALE: 3,
    PullRequestStatus.APPROVED: 4,
    PullRequestStatus.WAITING_FOR_REVIEW: 5,
    PullRequestStatus.MERGED: 6,
    PullRequestStatus.CLOSED_UNMERGED: 7,
}


@dataclass(frozen=True)
class Review:
    reviewer: str
    state: str  # APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED, PENDING
    submitted_at: datetime | None


@dataclass(frozen=True)
class Activity:
    at: datetime
    actor: str | None
    kind: str  # commented, reviewed, committed, labeled, ...
    text: str


@dataclass
class PullFacts:
    repo: str
    number: int
    title: str
    author: str
    state: str  # open, closed
    merged: bool
    draft: bool
    mergeable: bool | None
    mergeable_state: str | None
    opened_at: datetime
    check_conclusions: list[str] = field(default_factory=list)
    combined_status: str | None = None
    reviews: list[Review] = field(default_factory=list)
    activity: list[Activity] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    accepted_by_bot_label: str | None = None
    url: str | None = None
    closed_at: datetime | None = None


@dataclass
class PullStatus:
    status: PullRequestStatus
    needs_you: str
    reasons: list[str]
    days_quiet: int
    accepted_by_bot: bool = False

    @property
    def priority(self) -> int:
        return PRIORITY[self.status]


def latest_reviews(reviews: list[Review], author: str) -> dict[str, str]:
    """Each reviewer's most recent decisive review (comments don't change a decision)."""
    latest: dict[str, str] = {}
    for review in sorted(
        reviews, key=lambda r: r.submitted_at.timestamp() if r.submitted_at else 0
    ):
        if review.reviewer == author or review.state in ("COMMENTED", "PENDING"):
            continue
        if review.state == "DISMISSED":
            latest.pop(review.reviewer, None)
        else:
            latest[review.reviewer] = review.state
    return latest


def _others(facts: PullFacts) -> list[datetime]:
    """Times when someone other than the author did something on the PR."""
    others = [a.at for a in facts.activity if a.actor and a.actor != facts.author]
    others += [
        r.submitted_at for r in facts.reviews if r.reviewer != facts.author and r.submitted_at
    ]
    return others


def last_activity_by_others(facts: PullFacts) -> datetime:
    return max([facts.opened_at, *_others(facts)])


def derive(facts: PullFacts, now: datetime, stale_days: int) -> PullStatus:
    quiet = max((now - last_activity_by_others(facts)).days, 0)
    if facts.merged:
        return PullStatus(PullRequestStatus.MERGED, "Merged. Nothing to do.", ["Merged"], quiet)
    if facts.state == "closed":
        label = facts.accepted_by_bot_label
        if label and label.lower() in {lbl.lower() for lbl in facts.labels}:
            return PullStatus(
                PullRequestStatus.MERGED,
                "Accepted: this repo imports changes with a bot and closes the PR.",
                [f"Closed with the '{label}' label, which this repo uses for accepted changes"],
                quiet,
                accepted_by_bot=True,
            )
        return PullStatus(
            PullRequestStatus.CLOSED_UNMERGED,
            "Closed without merging.",
            ["Closed without merging"],
            quiet,
        )

    reasons: list[str] = []
    if facts.mergeable is None:
        reasons.append("GitHub is still checking for conflicts")
    if facts.mergeable is False or facts.mergeable_state == "dirty":
        return PullStatus(
            PullRequestStatus.MERGE_CONFLICT,
            "It has merge conflicts: merge the base branch and push.",
            [*reasons, "GitHub reports merge conflicts"],
            quiet,
        )
    failed = [c for c in facts.check_conclusions if c in FAILED_CHECKS]
    if failed or facts.combined_status in FAILED_STATUS:
        what = f"{len(failed)} check(s) failed" if failed else f"status is {facts.combined_status}"
        return PullStatus(
            PullRequestStatus.CI_FAILING,
            f"CI is failing ({what}): open the checks and fix them.",
            [*reasons, f"CI: {what}"],
            quiet,
        )
    decisions = latest_reviews(facts.reviews, facts.author)
    requested = sorted(r for r, s in decisions.items() if s == "CHANGES_REQUESTED")
    if requested:
        who = ", ".join(f"@{r}" for r in requested)
        return PullStatus(
            PullRequestStatus.CHANGES_REQUESTED,
            f"{who} asked for changes: reply or push an update.",
            [*reasons, f"Changes requested by {who}"],
            quiet,
        )
    approved = sorted(r for r, s in decisions.items() if s == "APPROVED")
    if approved:
        who = ", ".join(f"@{r}" for r in approved)
        return PullStatus(
            PullRequestStatus.APPROVED,
            "Approved. Nothing to do unless a maintainer asks; they will merge it.",
            [*reasons, f"Approved by {who}"],
            quiet,
        )
    if quiet >= stale_days:
        return PullStatus(
            PullRequestStatus.STALE,
            f"Quiet for {quiet} days. A polite nudge is drafted for you to copy.",
            [*reasons, f"No activity from anyone else for {quiet} days (stale after {stale_days})"],
            quiet,
        )
    note = (
        "Draft: mark it ready for review when it is."
        if facts.draft
        else ("Waiting for a first review. Nothing to do yet.")
    )
    days = f"{quiet} day{'s' if quiet != 1 else ''}"
    if _others(facts):
        when = f"Last activity from someone else {days} ago"
    else:
        when = f"Nobody else has replied yet (opened {days} ago)"
    return PullStatus(PullRequestStatus.WAITING_FOR_REVIEW, note, [*reasons, when], quiet)


def nudge(facts: PullFacts, status: PullStatus) -> str | None:
    """A polite note for a stale PR, for the user to copy. Never posted automatically."""
    if status.status is not PullRequestStatus.STALE:
        return None
    return (
        "Hi! Just checking in on this when you have a moment. "
        "I'm happy to change anything, and thanks for maintaining the project."
    )
