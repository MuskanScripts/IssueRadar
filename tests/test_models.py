from issueradar.models import Availability, Tier, level_dots


def test_level_dots() -> None:
    assert level_dots(Tier.BEGINNER) == "●○○"
    assert level_dots(Tier.INTERMEDIATE) == "●●○"
    assert level_dots(Tier.PRO) == "●●●"


def test_only_free_and_likely_free_are_rankable() -> None:
    assert {a for a in Availability if a.rankable} == {
        Availability.FREE,
        Availability.LIKELY_FREE,
    }


def test_status_labels_are_sentence_case_with_acronyms() -> None:
    from issueradar.models import PullRequestStatus

    assert PullRequestStatus.CI_FAILING.label == "CI failing"
    assert PullRequestStatus.CHANGES_REQUESTED.label == "Changes requested"
