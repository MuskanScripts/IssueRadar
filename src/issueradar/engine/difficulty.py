"""Difficulty engine: Beginner, Intermediate or Pro, with a 0-100 score (brief 5.4).

score = starting point + adjustments, clamped to 0..100

* Starting point: the tier anchor of a mapped label (repo rules first, then
  the default label map). Several mapped labels: their average. No mapped
  label: ``base_score``.
* Adjustments: fixed points for signals found in the title, body, labels and
  comment count. All points are in config and shown in the reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from issueradar.config.settings import DifficultySettings
from issueradar.engine.rules import RepoRules
from issueradar.engine.text import contains_any, file_paths, has_code_block, issue_refs
from issueradar.engine.types import IssueContext, Reason
from issueradar.models import IssueType, Tier, TimeBucket


@dataclass
class DifficultyResult:
    score: int
    tier: Tier
    time_bucket: TimeBucket
    issue_type: IssueType
    reasons: list[Reason] = field(default_factory=list)
    discussion_first: bool = False
    files: list[str] = field(default_factory=list)


def tier_for(score: int, settings: DifficultySettings) -> Tier:
    if score <= settings.beginner_max:
        return Tier.BEGINNER
    if score <= settings.intermediate_max:
        return Tier.INTERMEDIATE
    return Tier.PRO


def time_for(score: int, settings: DifficultySettings) -> TimeBucket:
    buckets = settings.time_buckets
    if score <= buckets.under_an_hour:
        return TimeBucket.UNDER_AN_HOUR
    if score <= buckets.half_a_day:
        return TimeBucket.HALF_A_DAY
    if score <= buckets.a_weekend:
        return TimeBucket.A_WEEKEND
    return TimeBucket.A_WEEK_OR_MORE


def issue_type(issue: IssueContext, settings: DifficultySettings) -> IssueType:
    labels = " ".join(issue.labels).lower()
    text = f"{issue.title}\n{labels}"
    checks = [
        (IssueType.DOCS, ["documentation", "docs", "typo", "readme"]),
        (IssueType.TESTS, ["test", "tests", "testing", "coverage"]),
        (IssueType.CI, ["ci", "github actions", "workflow", "build"]),
        (IssueType.REFACTOR, ["refactor", "cleanup", "clean up", "tech debt"]),
        (IssueType.BUG, ["bug", "crash", "error", "fails", "broken", "regression", "exception"]),
        (IssueType.FEATURE, ["feature", "enhancement", "add support", "support for", "proposal"]),
    ]
    for kind, words in checks:
        if contains_any(text, words):
            return kind
    return IssueType.BUG if "bug" in labels else IssueType.FEATURE


def _fmt(points: int) -> str:
    return f"{points:+d}"


def assess(issue: IssueContext, rules: RepoRules, settings: DifficultySettings) -> DifficultyResult:
    reasons: list[Reason] = []
    label_map = {k.lower(): v for k, v in settings.label_tiers.items()}
    label_map.update({k.lower(): v for k, v in rules.label_tiers.items()})

    anchors = []
    for label in issue.labels:
        mapped = label_map.get(label.lower())
        if mapped is not None:
            anchors.append(settings.tier_anchor[mapped])
            source = (
                "this repo's rules"
                if label.lower() in {k.lower() for k in rules.label_tiers}
                else "the default label map"
            )
            reasons.append(
                Reason(
                    f"Label '{label}' means {mapped} in {source}",
                    f"starts at {settings.tier_anchor[mapped]}",
                )
            )
    if anchors:
        score = round(sum(anchors) / len(anchors))
    else:
        score = settings.base_score
        reasons.append(Reason("No level label", f"starts at {score}"))

    adj = settings.adjustments
    kw = settings.keywords
    text = f"{issue.title}\n{issue.body}"
    body_len = len(issue.body or "")

    def add(points: int, why: str) -> None:
        nonlocal score
        if points:
            score += points
            reasons.append(Reason(why, _fmt(points)))

    match = contains_any(text, kw.docs_or_typo) or contains_any(
        " ".join(issue.labels), kw.docs_or_typo
    )
    if match:
        add(adj.docs_or_typo, f"Docs or typo work ('{match}')")
    match = contains_any(text, kw.tests_only)
    if match:
        add(adj.tests_only, f"Test work ('{match}')")
    if has_code_block(issue.body or "") or contains_any(text, kw.repro):
        add(adj.code_or_repro, "Has code or a reproduction")
    files = file_paths(issue.body or "")
    if files:
        add(adj.names_a_file, f"Names a file to start from ({files[0]})")
    if body_len < settings.short_body_chars:
        add(adj.short_body, f"Short description ({body_len} characters)")
    elif body_len > settings.long_body_chars:
        add(adj.long_body, f"Long description ({body_len} characters)")
    if issue.comments_count >= settings.many_comments:
        add(adj.many_comments, f"Long discussion ({issue.comments_count} comments)")
    linked = min(issue_refs(issue.body or ""), adj.max_linked_issues)
    if linked:
        add(adj.per_linked_issue * linked, f"Links {linked} other issue(s)")
    discussion = contains_any(
        f"{text}\n{' '.join(issue.labels)}",
        [*kw.discussion_first, *rules.discussion_first_keywords],
    )
    if discussion:
        add(adj.discussion_first, f"Needs discussion first ('{discussion}')")
    match = contains_any(text, kw.performance_or_concurrency)
    if match:
        add(adj.performance_or_concurrency, f"Performance or concurrency work ('{match}')")
    match = contains_any(text, kw.security)
    if match:
        add(adj.security, f"Security-sensitive ('{match}')")

    score = max(0, min(100, score))
    tier = tier_for(score, settings)
    reasons.append(
        Reason(
            f"Score {score} is in the {tier.label} band "
            f"(0-{settings.beginner_max}, {settings.beginner_max + 1}-"
            f"{settings.intermediate_max}, {settings.intermediate_max + 1}-100)"
        )
    )
    return DifficultyResult(
        score=score,
        tier=tier,
        time_bucket=time_for(score, settings),
        issue_type=issue_type(issue, settings),
        reasons=reasons,
        discussion_first=bool(discussion),
        files=files,
    )
