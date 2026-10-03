"""Repo health engine: "will a maintainer review my PR?" (brief 5.5).

score = sum(weight_i * part_i), each part between 0 and 1, weights add up to 100.

Parts:
* first_response: median days to a maintainer's first comment on issues opened
  by outsiders. Full points at or under ``response_days_good``, zero at or over
  ``response_days_bad``, linear in between.
* outside_merge_rate: share of recent outside-contributor PRs that were
  accepted (merged, or accepted by a bot import per repo rules) among those
  decided (merged or closed).
* recent_commit: days since the last push, scaled the same way.
* pr_backlog: number of open PRs, scaled the same way.
* contributor_docs: CONTRIBUTING (0.5), an issue template (0.25), a PR
  template (0.25).

A part with fewer than ``min_samples`` data points is unknown and scores 0.5,
and the reasons say so.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from issueradar.config.settings import HealthSettings
from issueradar.engine.rules import RepoRules
from issueradar.engine.types import Reason


@dataclass
class HealthInputs:
    pushed_at: datetime | None
    open_pull_requests: int
    first_response_days: list[float]
    outside_pr_outcomes: list[str]  # merged, accepted_by_bot, closed
    has_contributing: bool | None
    has_issue_template: bool | None
    has_pr_template: bool | None
    contributing_text: str | None = None
    archived: bool = False


@dataclass
class RepoFlags:
    cla: bool = False
    dco: bool = False
    ai_policy: bool = False
    issue_required: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class HealthResult:
    score: int
    parts: dict[str, float | None]
    reasons: list[Reason] = field(default_factory=list)
    flags: RepoFlags = field(default_factory=RepoFlags)


def outside_pr_outcome(*, merged: bool, labels: Iterable[str], rules: RepoRules) -> str:
    """How a closed outside pull request ended: merged, accepted_by_bot or closed.

    Some projects accept a change by importing it with a bot and closing the PR
    (repo rules name the label they use), so a closed PR isn't always a rejection.
    """
    if merged:
        return "merged"
    bot = rules.accepted_by_bot
    if bot and bot.label and bot.label.lower() in {label.lower() for label in labels}:
        return "accepted_by_bot"
    return "closed"


def _scale(value: float, good: float, bad: float) -> float:
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return 1.0 - (value - good) / (bad - good)


_CLA = re.compile(r"\b(CLA|contributor license agreement)\b", re.IGNORECASE)
_DCO = re.compile(r"\b(DCO|developer certificate of origin|signed-off-by)\b", re.IGNORECASE)
_AI = re.compile(
    r"\b(ai[- ]generated|generative ai|llm|chatgpt|copilot|large language model|ai tools?)\b",
    re.IGNORECASE,
)
_ISSUE_FIRST = re.compile(
    r"(open|create|file) an issue (first|before)|issue (is )?required before|"
    r"every (pr|pull request) (needs|requires|must have) an issue",
    re.IGNORECASE,
)


def detect_flags(contributing: str | None, issue_required_rule: bool) -> RepoFlags:
    flags = RepoFlags(issue_required=issue_required_rule)
    if issue_required_rule:
        flags.reasons.append("Repo rules: open an issue before a pull request")
    if not contributing:
        return flags
    if _CLA.search(contributing):
        flags.cla = True
        flags.reasons.append("CONTRIBUTING mentions a CLA: you may need to sign one")
    if _DCO.search(contributing):
        flags.dco = True
        flags.reasons.append("CONTRIBUTING mentions DCO sign-off: commits need Signed-off-by")
    if _AI.search(contributing):
        flags.ai_policy = True
        flags.reasons.append("CONTRIBUTING mentions AI tools: check their policy before using them")
    if not flags.issue_required and _ISSUE_FIRST.search(contributing):
        flags.issue_required = True
        flags.reasons.append("CONTRIBUTING asks for an issue before a pull request")
    return flags


def compute(
    inputs: HealthInputs, settings: HealthSettings, now: datetime, *, issue_required_rule: bool
) -> HealthResult:
    reasons: list[Reason] = []
    parts: dict[str, float | None] = {}

    if len(inputs.first_response_days) >= settings.min_samples:
        median = statistics.median(inputs.first_response_days)
        parts["first_response"] = _scale(
            median, settings.response_days_good, settings.response_days_bad
        )
        reasons.append(
            Reason(
                f"Maintainers first reply in a median of {median:.1f} days "
                f"({len(inputs.first_response_days)} issues)"
            )
        )
    else:
        parts["first_response"] = None
        reasons.append(
            Reason(
                f"Not enough issues to measure maintainer reply time "
                f"({len(inputs.first_response_days)} of {settings.min_samples} needed)"
            )
        )

    decided = inputs.outside_pr_outcomes
    if len(decided) >= settings.min_samples:
        accepted = sum(1 for o in decided if o in ("merged", "accepted_by_bot"))
        parts["outside_merge_rate"] = accepted / len(decided)
        by_bot = sum(1 for o in decided if o == "accepted_by_bot")
        extra = f", {by_bot} accepted by bot import" if by_bot else ""
        reasons.append(
            Reason(f"{accepted} of {len(decided)} recent outside pull requests accepted{extra}")
        )
    else:
        parts["outside_merge_rate"] = None
        reasons.append(
            Reason(f"Not enough decided outside pull requests to measure ({len(decided)})")
        )

    if inputs.pushed_at is not None:
        days = max((now - inputs.pushed_at).total_seconds() / 86400, 0.0)
        parts["recent_commit"] = _scale(days, settings.commit_days_good, settings.commit_days_bad)
        reasons.append(Reason(f"Last push {days:.0f} days ago"))
    else:
        parts["recent_commit"] = None
        reasons.append(Reason("Last push date unknown"))

    parts["pr_backlog"] = _scale(
        inputs.open_pull_requests, settings.backlog_good, settings.backlog_bad
    )
    reasons.append(Reason(f"{inputs.open_pull_requests} open pull requests"))

    if inputs.has_contributing is None:
        parts["contributor_docs"] = None
        reasons.append(Reason("Contributor docs not checked"))
    else:
        docs = (
            0.5 * bool(inputs.has_contributing)
            + 0.25 * bool(inputs.has_issue_template)
            + 0.25 * bool(inputs.has_pr_template)
        )
        parts["contributor_docs"] = docs
        found = [
            name
            for name, ok in (
                ("CONTRIBUTING", inputs.has_contributing),
                ("issue template", inputs.has_issue_template),
                ("PR template", inputs.has_pr_template),
            )
            if ok
        ]
        reasons.append(Reason("Has " + ", ".join(found) if found else "No contributor docs"))

    weights = settings.weights.model_dump()
    total = 0.0
    for name, weight in weights.items():
        value = parts.get(name)
        total += weight * (0.5 if value is None else value)
    score = round(total)
    if inputs.archived:
        score = 0
        reasons.insert(0, Reason("The repository is archived and accepts no changes"))

    return HealthResult(
        score=score,
        parts=parts,
        reasons=reasons,
        flags=detect_flags(inputs.contributing_text, issue_required_rule),
    )
