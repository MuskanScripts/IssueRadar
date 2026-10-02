"""PR tracker: recorded real PRs, and stale-day logic with frozen time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fake_github import FakeGitHub, load_fixture
from issueradar.config import Settings
from issueradar.engine.rules import RepoRules, load_rules
from issueradar.github import GitHubClient
from issueradar.models import PullRequestStatus as S
from issueradar.prs.status import Activity, PullFacts, Review, derive, latest_reviews, nudge
from issueradar.prs.tracker import PullTracker, activity_from_timeline, tracked
from issueradar.storage import Database

FROZEN = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
REPO = "MuskanScripts/IssueRadar"

# What github.com showed for each recorded PR when it was recorded (2026-10-02):
# #2, #14 and #15 merged; #12 (Dependabot) closed by the owner without merging,
# even though one of its checks had failed; #16 open, all six checks green, no
# review yet, opened that day.
EXPECTED = {
    2: S.MERGED,
    12: S.CLOSED_UNMERGED,
    14: S.MERGED,
    15: S.MERGED,
    16: S.WAITING_FOR_REVIEW,
}


def serve_pr(fake: FakeGitHub, number: int) -> datetime:
    fixture = load_fixture(f"recorded/prs/muskanscripts-issueradar-pr-{number}.json")
    body = fixture["body"]
    sha = body["pull"]["head"]["sha"]
    fake.add(f"/repos/{REPO}/pulls/{number}", body["pull"])
    fake.add(f"/repos/{REPO}/pulls/{number}/reviews?per_page=100", body["reviews"])
    fake.add(f"/repos/{REPO}/commits/{sha}/check-runs?per_page=100", body["check_runs"])
    fake.add(f"/repos/{REPO}/commits/{sha}/status", body["status"])
    fake.add(f"/repos/{REPO}/issues/{number}/timeline?per_page=100", body["timeline"])
    return datetime.fromisoformat(fixture["recorded_at"])


@pytest.mark.parametrize("number", sorted(EXPECTED))
async def test_status_matches_github_for_real_prs(
    db: Database, settings: Settings, number: int
) -> None:
    fake = FakeGitHub()
    recorded = serve_pr(fake, number)
    async with GitHubClient(settings.github, "t", transport=fake.transport()) as client:
        tracker = PullTracker(db, client, settings, load_rules(), clock=lambda: recorded)
        facts, _ = await tracker.facts(REPO, number)
    result = derive(facts, recorded, settings.pull_requests.stale_days)
    assert result.status is EXPECTED[number], result.reasons


async def test_tracker_stores_and_orders(db: Database, settings: Settings) -> None:
    fake = FakeGitHub()
    recorded = FROZEN
    listing = []
    for number in EXPECTED:
        recorded = serve_pr(fake, number)
        listing.append(
            load_fixture(f"recorded/prs/muskanscripts-issueradar-pr-{number}.json")["body"]["pull"]
        )
    fake.add(f"/repos/{REPO}/pulls?direction=desc&per_page=100&sort=updated&state=all", listing)
    async with GitHubClient(settings.github, "t", transport=fake.transport()) as client:
        tracker = PullTracker(db, client, settings, load_rules(), clock=lambda: recorded)
        report = await tracker.run(author="MuskanScripts", repos=[REPO])
    assert report.failed == {}
    numbers = [row.number for row in tracked(db)]
    assert set(numbers) == {2, 14, 15, 16}  # #12 is Dependabot's, not ours
    assert numbers[0] == 16  # the open one first
    row = tracked(db)[0]
    assert row.status == "waiting_for_review" and row.timeline


# Frozen-time logic --------------------------------------------------------


def facts(**changes: object) -> PullFacts:
    base: dict[str, object] = dict(
        repo="o/r",
        number=5,
        title="Fix it",
        author="me",
        state="open",
        merged=False,
        draft=False,
        mergeable=True,
        mergeable_state="clean",
        opened_at=FROZEN - timedelta(days=20),
    )
    base.update(changes)
    return PullFacts(**base)  # type: ignore[arg-type]


def ago(days: float) -> datetime:
    return FROZEN - timedelta(days=days)


@pytest.mark.parametrize(
    ("quiet", "expected"), [(6, S.WAITING_FOR_REVIEW), (7, S.STALE), (30, S.STALE)]
)
def test_stale_threshold_with_frozen_time(settings: Settings, quiet: int, expected: S) -> None:
    f = facts(activity=[Activity(ago(quiet), "maintainer", "commented", "")])
    assert derive(f, FROZEN, settings.pull_requests.stale_days).status is expected


def test_own_activity_does_not_reset_stale(settings: Settings) -> None:
    f = facts(
        activity=[
            Activity(ago(10), "maint", "commented", ""),
            Activity(ago(1), "me", "committed", ""),
        ]
    )
    result = derive(f, FROZEN, 7)
    assert result.status is S.STALE and result.days_quiet == 10
    assert nudge(f, result) is not None


def test_new_pr_without_activity_counts_from_opening(settings: Settings) -> None:
    assert derive(facts(opened_at=ago(3)), FROZEN, 7).status is S.WAITING_FOR_REVIEW
    assert derive(facts(opened_at=ago(8)), FROZEN, 7).status is S.STALE


def test_review_by_others_counts_as_activity() -> None:
    f = facts(reviews=[Review("lead", "COMMENTED", ago(2))])
    assert derive(f, FROZEN, 7).status is S.WAITING_FOR_REVIEW


def test_conflict_ci_and_reviews_priority() -> None:
    assert derive(facts(mergeable=False), FROZEN, 7).status is S.MERGE_CONFLICT
    assert derive(facts(mergeable_state="dirty"), FROZEN, 7).status is S.MERGE_CONFLICT
    unknown = derive(facts(mergeable=None, mergeable_state="unknown", opened_at=ago(1)), FROZEN, 7)
    assert unknown.status is S.WAITING_FOR_REVIEW
    assert "still checking" in unknown.reasons[0]
    assert derive(facts(check_conclusions=["success", "failure"]), FROZEN, 7).status is S.CI_FAILING
    assert derive(facts(combined_status="error"), FROZEN, 7).status is S.CI_FAILING
    changes = facts(reviews=[Review("lead", "CHANGES_REQUESTED", ago(1))])
    assert derive(changes, FROZEN, 7).status is S.CHANGES_REQUESTED


def test_latest_review_per_reviewer_wins() -> None:
    reviews = [
        Review("lead", "CHANGES_REQUESTED", ago(3)),
        Review("lead", "COMMENTED", ago(2)),
        Review("lead", "APPROVED", ago(1)),
        Review("other", "CHANGES_REQUESTED", ago(4)),
        Review("other", "DISMISSED", ago(2)),
        Review("me", "APPROVED", ago(1)),  # own reviews don't count
    ]
    assert latest_reviews(reviews, "me") == {"lead": "APPROVED"}
    assert derive(facts(reviews=reviews), FROZEN, 7).status is S.APPROVED


def test_closed_states_and_bot_import() -> None:
    assert derive(facts(state="closed", merged=True), FROZEN, 7).status is S.MERGED
    assert derive(facts(state="closed"), FROZEN, 7).status is S.CLOSED_UNMERGED
    imported = derive(
        facts(state="closed", labels=["ready to pull"], accepted_by_bot_label="ready to pull"),
        FROZEN,
        7,
    )
    assert imported.status is S.MERGED and imported.accepted_by_bot


def test_draft_note() -> None:
    result = derive(facts(draft=True, opened_at=ago(1)), FROZEN, 7)
    assert result.needs_you.startswith("Draft")


def test_activity_from_timeline_shapes() -> None:
    events = [
        {"event": "commented", "created_at": "2026-09-30T10:00:00Z", "actor": {"login": "lead"}},
        {"event": "reviewed", "submitted_at": "2026-09-30T11:00:00Z", "user": {"login": "lead"}},
        {
            "event": "committed",
            "committer": {"date": "2026-09-29T09:00:00Z"},
            "author": {"name": "me"},
        },
        {"event": "subscribed", "created_at": "2026-09-30T12:00:00Z", "actor": {"login": "x"}},
    ]
    items = activity_from_timeline(events)
    assert [a.kind for a in items] == ["committed", "commented", "reviewed"]
    assert items[1].text == "@lead commented"


def test_bot_import_rule_from_presets() -> None:
    rules: RepoRules = load_rules()["google/adk-python"]
    assert rules.accepted_by_bot is not None and rules.accepted_by_bot.label == "ready to pull"
