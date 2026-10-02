from fake_github import load_fixture
from issueradar.sync.normalize import (
    is_pull_request,
    issue_fields,
    pull_request_fields,
    referenced_issues,
)

REPO = "o/r"


def test_closing_keywords_are_strong_references() -> None:
    closing, mentioned = referenced_issues("Fixes #12, see also #7", REPO)
    assert closing == [12]
    assert mentioned == [7]


def test_all_closing_keyword_forms() -> None:
    text = (
        "close #1 closes #2 closed #3 fix #4 fixes #5 fixed #6 resolve #7 resolves #8 Resolved: #9"
    )
    closing, mentioned = referenced_issues(text, REPO)
    assert closing == list(range(1, 10))
    assert mentioned == []


def test_other_repos_are_ignored() -> None:
    text = "Fixes other/repo#3 and https://github.com/other/repo/issues/4, related to o/r#5"
    closing, mentioned = referenced_issues(text, REPO)
    assert closing == []
    assert mentioned == [5]


def test_full_issue_url_in_same_repo_counts() -> None:
    closing, _ = referenced_issues("Closes https://github.com/o/r/issues/42", REPO)
    assert closing == [42]


def test_anchors_and_words_are_not_references() -> None:
    _, mentioned = referenced_issues("see README#install and color #fff and C#7", REPO)
    assert mentioned == []


def test_bot_pr_bodies_are_not_scanned_on_real_data() -> None:
    """Recorded Dependabot PRs: bodies are copied release notes from other projects.

    Scanning them naively found 6 to 159 unrelated numbers per PR (RESULTS.md).
    """
    pulls = load_fixture("recorded/muskanscripts-issueradar-pulls-open.json")["response"]["body"]
    assert len(pulls) == 11
    for pr in pulls:
        fields = pull_request_fields(pr, "MuskanScripts/IssueRadar")
        assert fields["closing_issues"] == [] and fields["mentioned_issues"] == [], pr["number"]


def test_recorded_issue_list_contains_pull_requests() -> None:
    """GET /issues returns PRs too; on this repo every 'open issue' is a PR."""
    items = load_fixture("recorded/muskanscripts-issueradar-issues-open.json")["response"]["body"]
    assert items and all(is_pull_request(i) for i in items)


def test_issue_fields_from_documented_example() -> None:
    body = load_fixture("examples/issue-items.json")["body"][0]
    fields = issue_fields(body)
    assert fields["number"] == 1347
    assert fields["labels"] == ["bug"]
    assert fields["author_login"] == "octocat"
    assert fields["gh_created_at"] is not None
