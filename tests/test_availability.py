from __future__ import annotations

import pytest

from engine_helpers import NOW, comment, issue, pr
from issueradar.config import Settings
from issueradar.engine.availability import assess
from issueradar.engine.rules import RepoRules, load_rules, rules_for
from issueradar.models import Availability

RULES = RepoRules.empty("o/r")


def state(settings: Settings, rules: RepoRules = RULES, **changes):  # type: ignore[no-untyped-def]
    return assess(issue(**changes), rules, settings.availability, NOW)


def test_free_issue_explains_every_check(settings: Settings) -> None:
    result = state(settings)
    assert result.state is Availability.FREE
    text = " | ".join(str(r) for r in result.reasons)
    assert "No assignee" in text
    assert "No pull request found" in text and "timeline" in text
    assert "No claim in 0 comments" in text


def test_assignee_means_claimed(settings: Settings) -> None:
    result = state(settings, assignees=["alex"])
    assert result.state is Availability.CLAIMED
    assert "Assigned to @alex" in str(result.reasons[0])


@pytest.mark.parametrize(
    "body",
    [
        "Can I work on this?",
        "Hi! I'd like to work on this if nobody else is.",
        "I'll take this one",
        "/assign",
        "Working on this now, PR soon",
        "Could you ASSIGN ME please",
    ],
)
def test_outside_claims_are_detected(settings: Settings, body: str) -> None:
    result = state(settings, comments=[comment(body, age=3)], comments_count=1)
    assert result.state is Availability.CLAIMED
    assert result.claimed_by == "dev"
    assert result.claim_age_days == 3


@pytest.mark.parametrize("assoc", ["OWNER", "MEMBER", "COLLABORATOR"])
@pytest.mark.parametrize(
    "body",
    [
        "Feel free to take this!",
        "PRs welcome",
        "Happy to accept a PR for this",
        "Feel free to pick this up",
    ],
)
def test_maintainer_invitations_are_not_claims(settings: Settings, assoc: str, body: str) -> None:
    result = state(settings, comments=[comment(body, by="lead", assoc=assoc)], comments_count=1)
    assert result.state is Availability.FREE
    assert result.invited is True
    assert any("invited contributions" in str(r) for r in result.reasons)


def test_maintainer_saying_working_on_this_is_not_an_outside_claim(settings: Settings) -> None:
    result = state(
        settings, comments=[comment("I'm working on this", assoc="MEMBER")], comments_count=1
    )
    assert result.state is Availability.FREE


def test_outsider_quoting_invitation_still_claims_when_asking(settings: Settings) -> None:
    comments = [
        comment("Feel free to take this", by="lead", assoc="OWNER", age=5),
        comment("Great, can I take this?", by="newbie", age=4),
    ]
    result = state(settings, comments=comments, comments_count=2)
    assert result.state is Availability.CLAIMED
    assert result.claimed_by == "newbie"
    assert result.invited is True


def test_stale_claim_becomes_likely_free_with_age(settings: Settings) -> None:
    result = state(settings, comments=[comment("Can I work on this?", age=20)], comments_count=1)
    assert result.state is Availability.LIKELY_FREE
    assert "20 days ago" in str(result.reasons[-1])
    assert "stale after 14 days" in str(result.reasons[-1])


def test_claim_exactly_at_threshold_is_stale(settings: Settings) -> None:
    result = state(settings, comments=[comment("can i take this", age=14)], comments_count=1)
    assert result.state is Availability.LIKELY_FREE


def test_released_claim_frees_the_issue(settings: Settings) -> None:
    comments = [
        comment("I'll take this", by="dev", age=5),
        comment("Sorry, I can't work on this anymore", by="dev", age=2),
    ]
    assert state(settings, comments=comments, comments_count=2).state is Availability.FREE


def test_bot_comments_are_ignored(settings: Settings) -> None:
    result = state(
        settings, comments=[comment("/assign", by="stale[bot]", bot=True)], comments_count=1
    )
    assert result.state is Availability.FREE


def test_claim_phrase_must_be_a_phrase_not_a_substring(settings: Settings) -> None:
    body = "The networking on this branch is fine; reassign metrics later."
    assert state(settings, comments=[comment(body)], comments_count=1).state is Availability.FREE


@pytest.mark.parametrize("source", ["closing_reference", "search", "connected", "timeline"])
def test_linked_pull_requests_mean_has_pr(settings: Settings, source: str) -> None:
    result = state(settings, pr_links=[pr(42, source=source)])
    assert result.state is Availability.HAS_PR
    assert "#42" in str(result.reasons[-1])


def test_merged_pr_on_open_issue_is_has_pr(settings: Settings) -> None:
    result = state(settings, pr_links=[pr(42, state="merged")])
    assert result.state is Availability.HAS_PR
    assert "merged" in str(result.reasons[-1])


def test_closed_unmerged_pr_does_not_block(settings: Settings) -> None:
    assert state(settings, pr_links=[pr(42, state="closed")]).state is Availability.FREE


def test_bot_pr_does_not_block(settings: Settings) -> None:
    assert state(settings, pr_links=[pr(42, bot=True)]).state is Availability.FREE


def test_weak_mention_without_timeline_is_unclear(settings: Settings) -> None:
    result = state(settings, pr_links=[pr(42, source="mention")], timeline_checked=False)
    assert result.state is Availability.UNCLEAR


def test_not_ready_labels_from_defaults_and_repo_rules(settings: Settings) -> None:
    assert state(settings, labels=["needs triage"]).state is Availability.NOT_READY
    mcp = rules_for(load_rules(), "modelcontextprotocol/python-sdk")
    assert state(settings, mcp, labels=["needs maintainer action"]).state is Availability.NOT_READY
    result = state(settings, mcp, labels=["ready for work"])
    assert result.state is Availability.NOT_READY
    assert "maintainer work" in str(result.reasons[0])


def test_locked_issue_is_not_ready(settings: Settings) -> None:
    assert state(settings, locked=True).state is Availability.NOT_READY


def test_bot_authored_issue_is_unclear(settings: Settings) -> None:
    result = state(settings, author="renovate[bot]", author_is_bot=True)
    assert result.state is Availability.UNCLEAR


def test_non_english_text_is_unclear(settings: Settings) -> None:
    body = "客户端在服务器提前关闭时挂起。请帮忙看看这个问题。谢谢大家的帮助和支持。"
    assert state(settings, title="客户端挂起", body=body).state is Availability.UNCLEAR
    spanish = (
        "El cliente se queda colgado cuando el servidor cierra la conexión antes de tiempo. "
        "Pasos para reproducir: ejecutar el cliente y luego detener el servidor "
        "rápidamente sin aviso."
    )
    assert state(settings, title="Cliente colgado", body=spanish).state is Availability.UNCLEAR


def test_unchecked_comments_are_unclear(settings: Settings) -> None:
    result = state(settings, comments=None, comments_count=3)
    assert result.state is Availability.UNCLEAR
    assert "not checked" in str(result.reasons[-1])


def test_closed_issue(settings: Settings) -> None:
    assert state(settings, state="closed").state is Availability.UNCLEAR
