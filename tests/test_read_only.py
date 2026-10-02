"""FirstPR never writes to GitHub (ADR 0004). These tests fail if that changes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fake_github import FakeGitHub
from issueradar.config import Settings
from issueradar.github import GitHubClient, ReadOnlyViolation
from issueradar.github.guard import ensure_read_only_graphql, ensure_read_only_rest

SRC = Path(__file__).resolve().parents[1] / "src" / "issueradar"


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "post", "OPTIONS", "HEAD"])
async def test_rest_writes_are_refused_before_anything_is_sent(
    settings: Settings, method: str
) -> None:
    fake = FakeGitHub()
    async with GitHubClient(settings.github, "t", transport=fake.transport()) as client:
        with pytest.raises(ReadOnlyViolation):
            await client.request(method, "/repos/octocat/Hello-World/issues")
    assert fake.requests == []


async def test_rest_get_is_allowed(settings: Settings) -> None:
    fake = FakeGitHub()
    fake.add("/repos/octocat/Hello-World", {"full_name": "octocat/Hello-World"})
    async with GitHubClient(settings.github, "t", transport=fake.transport()) as client:
        response = await client.request("GET", "/repos/octocat/Hello-World")
    assert response.status == 200


async def test_transport_layer_refuses_non_graphql_posts(settings: Settings) -> None:
    """Second line of defence below the public methods."""
    fake = FakeGitHub()
    async with GitHubClient(settings.github, "t", transport=fake.transport()) as client:
        with pytest.raises(ReadOnlyViolation):
            await client._send("POST", "https://api.github.com/repos/o/r/issues")
        with pytest.raises(ReadOnlyViolation):
            await client._send("DELETE", settings.github.graphql_url)
    assert fake.requests == []


@pytest.mark.parametrize(
    "document",
    [
        'mutation { addComment(input: {subjectId: "x", body: "hi"}) { clientMutationId } }',
        "subscription { viewer { login } }",
        "query A { viewer { login } } mutation B { removeStar(input: {}) { clientMutationId } }",
        '  mutation\n{ addStar(input: {starrableId: "x"}) { clientMutationId } }',
        "query {",  # does not parse
        "fragment F on User { login }",  # no operation at all
    ],
)
async def test_graphql_writes_and_odd_documents_are_refused(
    settings: Settings, document: str
) -> None:
    fake = FakeGitHub()
    async with GitHubClient(settings.github, "t", transport=fake.transport()) as client:
        with pytest.raises(ReadOnlyViolation):
            await client.graphql(document)
    assert fake.requests == []


def test_graphql_queries_pass_the_guard() -> None:
    ensure_read_only_graphql("query { viewer { login } }")
    ensure_read_only_graphql("{ rateLimit { cost } }")  # anonymous query shorthand
    ensure_read_only_graphql("query A { viewer { login } } query B { rateLimit { cost } }")


def test_rest_guard_allows_only_get() -> None:
    ensure_read_only_rest("GET")
    ensure_read_only_rest("get")
    with pytest.raises(ReadOnlyViolation):
        ensure_read_only_rest("POST")


def test_only_the_client_and_delivery_modules_import_httpx() -> None:
    """GitHub traffic goes through github/client.py; digest delivery through delivery/http.py,
    which refuses GitHub hosts (next test)."""
    importers = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if re.search(r"^\s*(import httpx|from httpx\b)", path.read_text("utf-8"), re.MULTILINE)
    )
    assert importers == ["delivery/http.py", "github/client.py"]


@pytest.mark.parametrize(
    "url",
    [
        "https://api.github.com/repos/o/r/issues/1/comments",
        "https://github.com/o/r",
        "https://uploads.github.com/x",
        "https://gist.github.com/x",
    ],
)
def test_delivery_refuses_github_hosts(url: str) -> None:
    from issueradar.delivery.http import post_json

    with pytest.raises(ReadOnlyViolation):
        post_json(url, {"body": "hello"})


def test_fixtures_contain_no_tokens() -> None:
    """GitHub returns temp_clone_token for private repos; recordings must never keep one."""
    fixtures = Path(__file__).parent / "fixtures" / "github"
    pattern = re.compile(r'"temp_clone_token":\s*"[^"]+"|"authorization"|ghp_|github_pat_', re.I)
    offenders = [p.name for p in fixtures.rglob("*.json") if pattern.search(p.read_text("utf-8"))]
    assert offenders == []
