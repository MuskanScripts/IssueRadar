"""Measure whether a conditional request (304) costs primary rate limit.

GitHub's docs say an authenticated 304 does not count. One third-party library
says this is unreliable, so we measure it: plain GET, conditional GET, plain
GET again, recording ``x-ratelimit-used`` after each. Runs on GitHub, not in tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from issueradar.github.client import GitHubClient


@dataclass
class EtagMeasurement:
    url: str
    authenticated: bool
    statuses: tuple[int, int, int]
    used: tuple[int | None, int | None, int | None]

    @property
    def conditional_cost(self) -> int | None:
        before, after, _ = self.used
        if before is None or after is None:
            return None
        return after - before

    @property
    def plain_cost(self) -> int | None:
        _, before, after = self.used
        if before is None or after is None:
            return None
        return after - before

    def verdict(self) -> str:
        if self.statuses[1] != 304:
            return (
                "GitHub did not answer the conditional request with 304, so nothing was measured."
            )
        if self.conditional_cost is None or self.plain_cost is None:
            return "GitHub did not send x-ratelimit-used headers, so nothing was measured."
        if self.conditional_cost == 0 and self.plain_cost >= 1:
            return "The 304 response did not count against the primary rate limit."
        return (
            f"The 304 response changed x-ratelimit-used by {self.conditional_cost} "
            f"(a normal request changed it by {self.plain_cost})."
        )


def _used(headers: object) -> int | None:
    value = getattr(headers, "get", lambda _k: None)("x-ratelimit-used")
    return int(value) if value is not None else None


async def measure(client: GitHubClient, repo: str) -> EtagMeasurement:
    """``client`` should have an empty cache so the first call is a plain 200."""
    path = f"/repos/{repo}"
    first = await client.get(path)  # 200, stores the ETag
    second = await client.get(path)  # conditional: expect 304
    third = await client.get(path, conditional=False)  # plain 200 again
    return EtagMeasurement(
        url=client.url_for(path),
        authenticated=client.authenticated,
        statuses=(first.status, second.status, third.status),
        used=(_used(first.headers), _used(second.headers), _used(third.headers)),
    )
