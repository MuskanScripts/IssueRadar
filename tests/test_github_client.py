"""Contract tests for the GitHub client, using recorded and documented responses."""

from __future__ import annotations

import pytest

from conftest import FakeSleep
from fake_github import FakeGitHub, load_fixture
from issueradar.config import Settings
from issueradar.github import (
    GitHubClient,
    GraphQLQueryError,
    NotFound,
    QuotaExhausted,
    SecondaryRateLimited,
)
from issueradar.github.budget import ApiBudget
from issueradar.github.errors import GraphQLTimeout

REPO = load_fixture("recorded/muskanscripts-issueradar-repo.json")
REPO_304 = load_fixture("recorded/muskanscripts-issueradar-repo-304.json")


def client_for(
    settings: Settings, fake: FakeGitHub, sleep: FakeSleep | None = None
) -> GitHubClient:
    return GitHubClient(
        settings.github, "token", transport=fake.transport(), sleep=sleep or FakeSleep()
    )


def test_recorded_fixtures_show_a_free_304() -> None:
    """The recording itself: x-ratelimit-used did not move on the 304."""
    assert REPO["response"]["status"] == 200
    assert REPO_304["response"]["status"] == 304
    assert (
        REPO["response"]["headers"]["x-ratelimit-used"]
        == REPO_304["response"]["headers"]["x-ratelimit-used"]
    )


async def test_second_get_is_conditional_and_served_from_cache(settings: Settings) -> None:
    fake = FakeGitHub()
    fake.add("/repos/MuskanScripts/IssueRadar", REPO["response"]["body"])
    async with client_for(settings, fake) as client:
        first = await client.get("/repos/MuskanScripts/IssueRadar")
        second = await client.get("/repos/MuskanScripts/IssueRadar")
    assert (first.status, first.from_cache) == (200, False)
    assert (second.status, second.from_cache) == (304, True)
    assert second.data == first.data
    route = next(iter(fake.routes.values()))
    assert "if-none-match" not in fake.requests[0].headers
    assert fake.requests[1].headers["if-none-match"] == route.etag
    assert client.budget.not_modified == 1
    assert client.budget.states["core"].remaining == 4999  # the 304 cost nothing


async def test_token_is_sent_as_bearer_and_api_version_pinned(settings: Settings) -> None:
    fake = FakeGitHub()
    fake.add("/rate_limit", {"resources": {}})
    async with client_for(settings, fake) as client:
        await client.get("/rate_limit", conditional=False)
    sent = fake.requests[0].headers
    assert sent["authorization"] == "Bearer token"
    assert sent["x-github-api-version"] == "2022-11-28"
    assert sent["accept"] == "application/vnd.github+json"


async def test_pagination_follows_link_and_stops_at_max_pages(settings: Settings) -> None:
    fake = FakeGitHub()
    items = [{"id": i} for i in range(25)]
    fake.add_list("/repos/o/r/issues", items, {"state": "open"}, page_size=10)
    async with client_for(settings, fake) as client:
        pages = [
            p
            async for p in client.paginate(
                "/repos/o/r/issues", params={"state": "open", "per_page": 10}, max_pages=2
            )
        ]
    assert [len(p.data) for p in pages] == [10, 10]
    assert pages[-1].next_url is not None  # a third page exists but was not fetched


async def test_primary_limit_used_up_stops_with_reset_time(settings: Settings) -> None:
    fake = FakeGitHub(remaining=0)
    async with client_for(settings, fake) as client:
        with pytest.raises(QuotaExhausted) as info:
            await client.get("/repos/o/r")
    assert info.value.resource == "core"
    assert info.value.reset_at == fake.reset_at
    assert len(fake.requests) == 1  # no retry while the primary limit is used up


async def test_budget_margin_stops_before_sending(settings: Settings) -> None:
    fake = FakeGitHub(limit=100, remaining=11)
    fake.add("/repos/o/r", {"id": 1})
    budget = ApiBudget(safety_margin=0.10)
    async with GitHubClient(
        settings.github, "t", transport=fake.transport(), budget=budget
    ) as client:
        await client.get("/repos/o/r", conditional=False)  # remaining becomes 10 = margin
        with pytest.raises(QuotaExhausted):
            await client.get("/repos/o/r", conditional=False)
    assert len(fake.requests) == 1


async def test_secondary_limit_honours_retry_after(
    settings: Settings, fake_sleep: FakeSleep
) -> None:
    fake = FakeGitHub()
    fake.add("/repos/o/r", {"id": 1})
    fake.secondary_limited.append({"retry-after": "7"})
    async with client_for(settings, fake, fake_sleep) as client:
        response = await client.get("/repos/o/r")
    assert response.status == 200
    assert fake_sleep.waits == [7.0]


async def test_secondary_limit_without_retry_after_waits_a_minute_then_backs_off(
    settings: Settings, fake_sleep: FakeSleep
) -> None:
    fake = FakeGitHub()
    fake.add("/repos/o/r", {"id": 1})
    fake.secondary_limited.extend([{}, {}, {}])
    async with client_for(settings, fake, fake_sleep) as client:
        await client.get("/repos/o/r")
    assert fake_sleep.waits == [60.0, 120.0, 240.0]


async def test_secondary_limit_gives_up_after_max_retries(
    settings: Settings, fake_sleep: FakeSleep
) -> None:
    fake = FakeGitHub()
    fake.add("/repos/o/r", {"id": 1})
    fake.secondary_limited.extend([{}] * 10)
    async with client_for(settings, fake, fake_sleep) as client:
        with pytest.raises(SecondaryRateLimited):
            await client.get("/repos/o/r")
    retries = settings.github.retry.max_retries
    assert len(fake.requests) == retries + 1
    assert len(fake_sleep.waits) == retries


async def test_not_found(settings: Settings) -> None:
    async with client_for(settings, FakeGitHub()) as client:
        with pytest.raises(NotFound):
            await client.get("/repos/o/missing")


async def test_server_errors_are_retried_with_backoff(
    settings: Settings, fake_sleep: FakeSleep
) -> None:
    fake = FakeGitHub()
    fake.add("/repos/o/r", {"message": "boom"}, status=502)
    async with client_for(settings, fake, fake_sleep) as client:
        with pytest.raises(Exception, match="502"):
            await client.get("/repos/o/r")
    assert fake_sleep.waits == [2.0, 4.0, 8.0, 16.0]


# GraphQL --------------------------------------------------------------------
# Shapes follow GitHub's GraphQL docs; recorded GraphQL fixtures need a token
# (GraphQL was not reachable from the environment where these were written).

QUERY = "query { rateLimit { cost remaining } viewer { login } }"


async def test_graphql_returns_data_and_records_cost(settings: Settings) -> None:
    fake = FakeGitHub()
    fake.graphql_responses.append(
        (
            200,
            {"data": {"rateLimit": {"cost": 1, "remaining": 4999}, "viewer": {"login": "me"}}},
            {},
        )
    )
    async with client_for(settings, fake) as client:
        data = await client.graphql(QUERY)
    assert data["viewer"]["login"] == "me"
    assert client.budget.graphql_cost == 1
    assert fake.requests[0].method == "POST"


async def test_graphql_errors_inside_http_200_are_raised(settings: Settings) -> None:
    fake = FakeGitHub()
    body = {
        "data": {"repository": None},
        "errors": [
            {
                "type": "NOT_FOUND",
                "path": ["repository"],
                "message": "Could not resolve to a Repository with the name 'o/missing'.",
            }
        ],
    }
    fake.graphql_responses.append((200, body, {}))
    async with client_for(settings, fake) as client:
        with pytest.raises(GraphQLQueryError, match="Could not resolve") as info:
            await client.graphql(QUERY)
    assert info.value.data == {"repository": None}


async def test_graphql_primary_limit_in_http_200(settings: Settings) -> None:
    fake = FakeGitHub()
    body = {"errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}
    fake.graphql_responses.append((200, body, {"x-ratelimit-remaining": "0"}))
    async with client_for(settings, fake) as client:
        with pytest.raises(QuotaExhausted) as info:
            await client.graphql(QUERY)
    assert info.value.resource == "graphql"


async def test_graphql_secondary_limit_in_http_200_is_retried(
    settings: Settings, fake_sleep: FakeSleep
) -> None:
    fake = FakeGitHub()
    limited = {"errors": [{"message": "You have exceeded a secondary rate limit."}]}
    fake.graphql_responses.append((200, limited, {}))
    fake.graphql_responses.append((200, {"data": {"viewer": {"login": "me"}}}, {}))
    async with client_for(settings, fake, fake_sleep) as client:
        data = await client.graphql(QUERY)
    assert data == {"viewer": {"login": "me"}}
    assert fake_sleep.waits == [60.0]


async def test_graphql_timeout(settings: Settings) -> None:
    fake = FakeGitHub()
    body = {"errors": [{"message": "We couldn't respond to your request in time."}]}
    fake.graphql_responses.append((200, body, {}))
    async with client_for(settings, fake) as client:
        with pytest.raises(GraphQLTimeout):
            await client.graphql(QUERY)
