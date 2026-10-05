"""Availability engine: "is anyone already on this issue?" (brief 5.3).

Checks run in a fixed order and the first decisive one sets the state. Every
result carries the reasons that led to it, including the checks that passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from issueradar.config.settings import AvailabilitySettings
from issueradar.engine.rules import RepoRules
from issueradar.engine.text import contains_any, looks_non_english
from issueradar.engine.types import Comment, IssueContext, Reason
from issueradar.models import Availability


@dataclass
class AvailabilityResult:
    state: Availability
    reasons: list[Reason] = field(default_factory=list)
    claim_age_days: int | None = None
    claimed_by: str | None = None
    invited: bool = False
    outside_commenters: int = 0


@dataclass
class _Claim:
    author: str
    at: datetime
    phrase: str


def _labels_match(labels: list[str], wanted: list[str]) -> str | None:
    lowered = {label.lower(): label for label in labels}
    for name in wanted:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _latest_claim(
    comments: list[Comment], settings: AvailabilitySettings
) -> tuple[_Claim | None, bool]:
    """The newest claim that was not given back, and whether a maintainer invited work."""
    maintainers = {a.upper() for a in settings.maintainer_associations}
    claim: _Claim | None = None
    invited = False
    for comment in sorted(comments, key=lambda c: c.created_at):
        if comment.is_bot:
            continue
        is_maintainer = (comment.association or "").upper() in maintainers
        if is_maintainer:
            if contains_any(comment.body, settings.invitation_patterns):
                invited = True
            continue  # a maintainer saying "I'll take this" is a different situation
        if (
            claim
            and comment.author == claim.author
            and contains_any(comment.body, settings.release_patterns)
        ):
            claim = None
            continue
        phrase = contains_any(comment.body, settings.claim_patterns)
        if phrase and comment.author:
            claim = _Claim(comment.author, comment.created_at, phrase)
    return claim, invited


def assess(
    issue: IssueContext,
    rules: RepoRules,
    settings: AvailabilitySettings,
    now: datetime,
) -> AvailabilityResult:
    reasons: list[Reason] = []

    if issue.state != "open":
        return AvailabilityResult(Availability.UNCLEAR, [Reason("The issue is not open any more")])
    if issue.locked:
        return AvailabilityResult(Availability.NOT_READY, [Reason("The conversation is locked")])
    label = _labels_match(issue.labels, rules.maintainer_only_labels)
    if label:
        return AvailabilityResult(
            Availability.NOT_READY,
            [Reason(f"Label '{label}' marks it as maintainer work in this repo")],
        )
    label = _labels_match(issue.labels, [*rules.not_ready_labels, *settings.not_ready_labels])
    if label:
        return AvailabilityResult(
            Availability.NOT_READY, [Reason(f"Label '{label}' means it is not ready to work on")]
        )
    if issue.author_is_bot:
        return AvailabilityResult(
            Availability.UNCLEAR, [Reason(f"Opened by a bot ({issue.author})")]
        )
    if issue.assignees:
        names = ", ".join(f"@{a}" for a in issue.assignees)
        return AvailabilityResult(Availability.CLAIMED, [Reason(f"Assigned to {names}")])
    reasons.append(Reason("No assignee"))

    # Pull requests: strong signals first.
    human_prs = [p for p in issue.pr_links if not p.is_bot and p.state in ("open", "merged")]
    strong = [p for p in human_prs if p.source in ("closing_reference", "search", "connected")]
    from_timeline = [p for p in human_prs if p.source == "timeline"]
    weak = [p for p in human_prs if p.source == "mention"]
    if strong or from_timeline:
        pr = (strong or from_timeline)[0]
        how = {
            "closing_reference": "says it fixes this issue",
            "search": "is linked to it on GitHub",
            "connected": "was linked to it by hand on GitHub",
            "timeline": "references it",
        }[pr.source]
        when = "merged" if pr.state == "merged" else "open"
        which = f"pull request #{pr.number}" if pr.number else "pull request"
        if pr.repo:
            which = f"pull request {pr.repo}#{pr.number}"
        return AvailabilityResult(
            Availability.HAS_PR, [*reasons, Reason(f"An {when} {which} {how}")]
        )
    if weak and not issue.timeline_checked:
        numbers = ", ".join(f"#{p.number}" for p in weak)
        return AvailabilityResult(
            Availability.UNCLEAR,
            [
                *reasons,
                Reason(f"Open pull request {numbers} mentions it; check whether it fixes it"),
            ],
        )
    checked = []
    if issue.linked_pr_search_checked:
        checked.append("GitHub's linked-PR search")
    if issue.timeline_checked:
        checked.append("the issue timeline")
    checked.append("open PR descriptions")
    reasons.append(Reason("No pull request found (checked " + ", ".join(checked) + ")"))

    if looks_non_english(
        f"{issue.title}\n{issue.body}",
        ascii_ratio=settings.non_english_ascii_ratio,
        min_words=settings.non_english_min_words,
        stopword_ratio=settings.non_english_stopword_ratio,
    ):
        return AvailabilityResult(
            Availability.UNCLEAR,
            [*reasons, Reason("Not written in English, so claims can't be read reliably")],
        )

    if issue.comments is None:
        if issue.comments_count == 0:
            reasons.append(Reason("No comments, so no claims"))
            return AvailabilityResult(Availability.FREE, reasons)
        return AvailabilityResult(
            Availability.UNCLEAR,
            [*reasons, Reason(f"{issue.comments_count} comments not checked yet; run sync")],
        )

    claim, invited = _latest_claim(issue.comments, settings)
    maintainers = {a.upper() for a in settings.maintainer_associations}
    outside = {
        c.author
        for c in issue.comments
        if c.author and not c.is_bot and (c.association or "").upper() not in maintainers
    }
    if invited:
        reasons.append(Reason("A maintainer invited contributions (not a claim)"))
    if claim is None:
        reasons.append(Reason(f"No claim in {len(issue.comments)} comments"))
        return AvailabilityResult(
            Availability.FREE, reasons, invited=invited, outside_commenters=len(outside)
        )

    age = (now - claim.at).days
    claimed = f'@{claim.author} wrote "{claim.phrase}" {age} days ago'
    if age >= settings.stale_claim_days:
        return AvailabilityResult(
            Availability.LIKELY_FREE,
            [
                *reasons,
                Reason(
                    f"{claimed}, but no pull request since (stale after "
                    f"{settings.stale_claim_days} days)"
                ),
            ],
            claim_age_days=age,
            claimed_by=claim.author,
            invited=invited,
            outside_commenters=len(outside),
        )
    return AvailabilityResult(
        Availability.CLAIMED,
        [*reasons, Reason(claimed)],
        claim_age_days=age,
        claimed_by=claim.author,
        invited=invited,
        outside_commenters=len(outside),
    )
