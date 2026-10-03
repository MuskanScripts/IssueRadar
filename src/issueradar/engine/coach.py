"""Contribution etiquette coach (brief 9).

A short checklist shown before someone starts an issue. It never counts or
rewards volume: the aim is better contributions, not more of them.
"""

from __future__ import annotations

from collections.abc import Mapping


def checklist(
    repo: str,
    flags: Mapping[str, object],
    *,
    discussion_first: bool,
    open_unreviewed_prs: int = 0,
    unreviewed_warning_at: int = 3,
) -> list[str]:
    items = [f"Read {repo}'s CONTRIBUTING guide before writing code."]
    if flags.get("issue_required"):
        items.append("This repo wants an issue first: comment on it and wait for a maintainer.")
    else:
        items.append("Say on the issue that you'd like to work on it, the way this repo expects.")
    if discussion_first:
        items.append("Agree on the approach in the issue before opening a pull request.")
    if flags.get("cla"):
        items.append("Sign the CLA before your PR can be merged.")
    if flags.get("dco"):
        items.append("Sign off every commit (git commit -s).")
    if flags.get("ai_policy"):
        items.append("Check the repo's policy on AI tools before using them.")
    items += [
        "One issue per pull request.",
        "Include a test that fails before your change and passes after.",
        "Keep the diff small and focused.",
    ]
    if open_unreviewed_prs >= unreviewed_warning_at:
        items.append(
            f"You already have {open_unreviewed_prs} open PRs waiting for a first review. "
            "Consider finishing those before starting another."
        )
    return items
