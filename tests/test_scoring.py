from __future__ import annotations

from datetime import timedelta

from engine_helpers import NOW, days_ago, issue
from issueradar.config import Settings
from issueradar.engine import difficulty, health, ranking, stack
from issueradar.engine.rules import RepoRules, load_rules, rules_for
from issueradar.models import Availability, IssueType, Tier, TimeBucket

RULES = RepoRules.empty("o/r")


# Difficulty -----------------------------------------------------------------


def test_good_first_docs_issue_is_beginner_and_quick(settings: Settings) -> None:
    result = difficulty.assess(
        issue(
            title="Fix broken link in the quickstart",
            body="The link in docs/quickstart.md is dead.",
            labels=["good first issue", "documentation"],
        ),
        RULES,
        settings.difficulty,
    )
    assert result.tier is Tier.BEGINNER
    assert result.time_bucket is TimeBucket.UNDER_AN_HOUR
    assert result.issue_type is IssueType.DOCS
    assert result.files == ["docs/quickstart.md"]
    text = " | ".join(str(r) for r in result.reasons)
    assert "Label 'good first issue' means beginner" in text
    assert "Docs or typo work" in text


def test_concurrency_proposal_is_pro(settings: Settings) -> None:
    body = "We need a design doc first. There is a race condition in the scheduler. " + "x" * 3200
    result = difficulty.assess(
        issue(title="Race condition in the job scheduler", body=body, comments_count=14),
        RULES,
        settings.difficulty,
    )
    assert result.tier is Tier.PRO
    assert result.discussion_first is True
    assert result.time_bucket is TimeBucket.A_WEEK_OR_MORE


def test_unlabelled_plain_bug_is_intermediate(settings: Settings) -> None:
    result = difficulty.assess(
        issue(
            title="Crash when config has no profile",
            body="Traceback below.\n```\nNullPointerException at Loader.java:42\n```\n" + "y" * 500,
        ),
        RULES,
        settings.difficulty,
    )
    assert result.tier is Tier.INTERMEDIATE
    assert result.issue_type is IssueType.BUG


def test_repo_label_map_overrides_default(settings: Settings) -> None:
    custom = RepoRules(repo="o/r", label_tiers={"good first issue": "intermediate"})
    result = difficulty.assess(
        issue(labels=["good first issue"], body="z" * 600), custom, settings.difficulty
    )
    assert "this repo's rules" in str(result.reasons[0])
    assert result.score == settings.difficulty.tier_anchor["intermediate"]  # no adjustments apply


def test_mcp_preset_help_wanted_is_intermediate(settings: Settings) -> None:
    rules = rules_for(load_rules(), "modelcontextprotocol/python-sdk")
    result = difficulty.assess(
        issue(labels=["help wanted"], body="w" * 600), rules, settings.difficulty
    )
    assert result.tier is Tier.INTERMEDIATE


def test_score_is_clamped(settings: Settings) -> None:
    result = difficulty.assess(
        issue(
            title="typo in readme docs",
            body="typo",
            labels=["good first issue", "first-timers-only"],
        ),
        RULES,
        settings.difficulty,
    )
    assert 0 <= result.score <= 100


# Health ---------------------------------------------------------------------


def inputs(**changes):  # type: ignore[no-untyped-def]
    base = dict(
        pushed_at=days_ago(1),
        open_pull_requests=5,
        first_response_days=[0.5, 1.0, 1.5, 2.0],
        outside_pr_outcomes=["merged", "merged", "merged", "closed"],
        has_contributing=True,
        has_issue_template=True,
        has_pr_template=True,
    )
    base.update(changes)
    return health.HealthInputs(**base)


def test_healthy_repo_scores_high(settings: Settings) -> None:
    result = health.compute(inputs(), settings.health, NOW, issue_required_rule=False)
    # 30*1 + 30*0.75 + 20*1 + 10*1 + 10*1 = 92.5 -> 92 (banker's rounding)
    assert result.score == 92
    assert result.parts["outside_merge_rate"] == 0.75


def test_unknown_parts_score_half_and_say_so(settings: Settings) -> None:
    result = health.compute(
        inputs(first_response_days=[1.0], outside_pr_outcomes=[]),
        settings.health,
        NOW,
        issue_required_rule=False,
    )
    assert result.parts["first_response"] is None
    assert result.score == round(30 * 0.5 + 30 * 0.5 + 20 + 10 + 10)
    assert any("Not enough issues" in str(r) for r in result.reasons)


def test_bot_imports_count_as_accepted(settings: Settings) -> None:
    result = health.compute(
        inputs(outside_pr_outcomes=["accepted_by_bot", "accepted_by_bot", "closed"]),
        settings.health,
        NOW,
        issue_required_rule=False,
    )
    assert round(result.parts["outside_merge_rate"] or 0, 3) == 0.667
    assert any("accepted by bot import" in str(r) for r in result.reasons)


def test_linear_scaling_between_good_and_bad(settings: Settings) -> None:
    result = health.compute(
        inputs(pushed_at=NOW - timedelta(days=93.5)),
        settings.health,
        NOW,
        issue_required_rule=False,
    )
    assert round(result.parts["recent_commit"] or 0, 2) == 0.5  # halfway between 7 and 180


def test_archived_repo_scores_zero(settings: Settings) -> None:
    assert (
        health.compute(inputs(archived=True), settings.health, NOW, issue_required_rule=False).score
        == 0
    )


def test_flags_from_contributing_text() -> None:
    text = (
        "You must sign our Contributor License Agreement. All commits need a Signed-off-by line. "
        "Please do not submit AI-generated code. Open an issue first before sending a PR."
    )
    flags = health.detect_flags(text, issue_required_rule=False)
    assert (flags.cla, flags.dco, flags.ai_policy, flags.issue_required) == (True, True, True, True)
    assert not health.detect_flags("Thanks for contributing!", issue_required_rule=False).cla


# Stack ----------------------------------------------------------------------


PROFILE = stack.SkillProfile(
    languages={"python": "strong", "typescript": "learning"},
    frameworks={"react": "learning"},
    domains={"agents-and-mcp": "medium"},
)


def test_dependencies_from_manifests() -> None:
    assert {"react", "vite"} <= stack.dependency_names(
        "package.json", '{"dependencies": {"react": "18"}, "devDependencies": {"vite": "8"}}'
    )
    assert {"fastapi", "httpx"} <= stack.dependency_names(
        "pyproject.toml", '[project]\ndependencies = ["fastapi>=0.1", "httpx[http2]"]\n'
    )
    assert "pytest" in stack.dependency_names("requirements.txt", "# dev\npytest==8\n-r base.txt\n")
    pom = (
        "<dependency><groupId>org.springframework.boot</groupId>"
        "<artifactId>spring-boot-starter</artifactId></dependency>"
    )
    assert "spring-boot-starter" in stack.dependency_names("pom.xml", pom)
    assert stack.dependency_names("package.json", "not json") == set()


def test_frameworks_and_domains(settings: Settings) -> None:
    deps = {"react", "react-dom", "org.springframework.boot"}
    assert stack.frameworks_from_dependencies(deps, settings.stack) == ["react", "spring"]
    assert stack.domains_from_topics(["MCP", "python"], settings.stack) == ["agents-and-mcp"]


def test_strong_language_targets_intermediate(settings: Settings) -> None:
    repo = stack.RepoStack(languages=["python"], domains=["agents-and-mcp"])
    result = stack.match(repo, [], PROFILE, settings.stack)
    assert result.target_tier is Tier.INTERMEDIATE
    assert result.fit > 0.8


def test_learning_language_targets_beginner_and_stretch_moves_up(settings: Settings) -> None:
    repo = stack.RepoStack(languages=["typescript"], frameworks=["react"])
    assert stack.match(repo, [], PROFILE, settings.stack).target_tier is Tier.BEGINNER
    stretchy = PROFILE.model_copy(update={"stretch": True})
    assert stack.match(repo, [], stretchy, settings.stack).target_tier is Tier.INTERMEDIATE


def test_file_paths_in_issue_override_repo_language(settings: Settings) -> None:
    repo = stack.RepoStack(languages=["python"])
    result = stack.match(repo, ["web/src/App.tsx"], PROFILE, settings.stack)
    assert result.target_tier is Tier.BEGINNER  # typescript: learning
    assert "named files" in str(result.reasons[-1])


def test_no_profile_is_neutral_and_unknown_stack_is_zero(settings: Settings) -> None:
    assert stack.match(stack.RepoStack(["go"]), [], None, settings.stack).fit == 0.5
    assert stack.match(stack.RepoStack(["go"]), [], PROFILE, settings.stack).fit == 0.0


def test_tier_fit() -> None:
    assert stack.tier_fit(Tier.BEGINNER, Tier.BEGINNER) == 1.0
    assert stack.tier_fit(Tier.INTERMEDIATE, Tier.BEGINNER) == 0.5
    assert stack.tier_fit(Tier.PRO, Tier.BEGINNER) == 0.0
    assert stack.tier_fit(Tier.PRO, None) == 0.5


# Ranking --------------------------------------------------------------------


def rank_inputs(**changes):  # type: ignore[no-untyped-def]
    base = dict(
        availability=Availability.FREE,
        tier=Tier.BEGINNER,
        tier_fit=1.0,
        health=80,
        stack_fit=1.0,
        updated_at=NOW,
        comments=0,
    )
    base.update(changes)
    return ranking.RankInputs(**base)


def test_perfect_issue_scores_one(settings: Settings) -> None:
    result = ranking.score(rank_inputs(health=100), settings.ranking, NOW)
    assert result is not None and result.score == 1.0


def test_only_free_and_likely_free_are_ranked(settings: Settings) -> None:
    for state in (
        Availability.CLAIMED,
        Availability.HAS_PR,
        Availability.NOT_READY,
        Availability.UNCLEAR,
    ):
        assert ranking.score(rank_inputs(availability=state), settings.ranking, NOW) is None


def test_formula_matches_weights(settings: Settings) -> None:
    result = ranking.score(
        rank_inputs(tier_fit=0.5, health=50, stack_fit=0.0, updated_at=days_ago(30), comments=5),
        settings.ranking,
        NOW,
    )
    assert result is not None
    expected = 0.35 * 0.5 + 0.25 * 0.5 + 0.20 * 0.0 + 0.10 * 0.5 + 0.10 * 0.5
    assert abs(result.score - expected) < 1e-4


def test_likely_free_loses_half_competition(settings: Settings) -> None:
    free = ranking.score(rank_inputs(), settings.ranking, NOW)
    likely = ranking.score(
        rank_inputs(availability=Availability.LIKELY_FREE), settings.ranking, NOW
    )
    assert free is not None and likely is not None
    assert likely.parts["low_competition"] == 0.5
    assert "old claim went quiet" in likely.why.lower()


def test_why_line_is_human(settings: Settings) -> None:
    result = ranking.score(rank_inputs(), settings.ranking, NOW)
    assert result is not None
    assert result.why.startswith("Beginner matches your level")
