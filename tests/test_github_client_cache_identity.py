"""A stable cache identity keeps ETags working when the token rotates."""

from __future__ import annotations

from fake_github import FakeGitHub, example_repo
from issueradar.config import Settings
from issueradar.github import GitHubClient
from issueradar.github.cache import MemoryEtagCache


async def test_rotated_token_reuses_etags_with_a_stable_identity(settings: Settings) -> None:
    fake = FakeGitHub()
    fake.add("/repos/o/r", example_repo("o/r"))
    cache = MemoryEtagCache()

    async def fetch(token: str, identity: str | None) -> bool:
        async with GitHubClient(
            settings.github, token, cache=cache, transport=fake.transport(), cache_identity=identity
        ) as client:
            return (await client.get("/repos/o/r")).from_cache

    assert await fetch("token-hour-1", "app") is False
    assert await fetch("token-hour-2", "app") is True  # same identity: 304 from the cache
    assert await fetch("token-hour-3", None) is False  # no identity: kept apart per token
