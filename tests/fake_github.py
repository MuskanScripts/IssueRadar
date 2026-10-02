"""A fake GitHub API for tests. No network.

It serves responses registered per URL, behaves like GitHub for the parts our
client depends on, and records every request:

* ETags: if ``If-None-Match`` matches the route's ETag, it answers 304.
* Primary rate limit: every non-304 response uses one request; when the
  budget is used up it answers 403 with ``x-ratelimit-remaining: 0``, as the
  docs describe. 304 responses do not use budget (documented for
  authenticated requests, and measured in RESULTS.md).
* Bodies come from recorded real responses or GitHub's documented examples
  (see tests/fixtures/github/README.md).
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent / "fixtures" / "github"
API = "https://api.github.com"


def load_fixture(relative: str) -> dict[str, Any]:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def example_issue(number: int, *, title: str = "Example issue", **changes: Any) -> dict[str, Any]:
    """An issue built from GitHub's documented issue example (not real data)."""
    base = copy.deepcopy(load_fixture("examples/issue-items.json")["body"][0])
    base.pop("pull_request", None)  # the documented example is linked to a PR
    base.update(
        id=10_000_000_000 + number,  # above 2**31 on purpose: GitHub ids are that large
        number=number,
        title=title,
        state="open",
        assignees=[],
        assignee=None,
        labels=[],
    )
    base.update(changes)
    return base


def example_pull(number: int, body: str, **changes: Any) -> dict[str, Any]:
    base = copy.deepcopy(load_fixture("examples/pull-request-simple-items.json")["body"][0])
    base.update(id=20_000_000_000 + number, number=number, body=body, state="open")
    base.update(changes)
    return base


def example_repo(full_name: str, **changes: Any) -> dict[str, Any]:
    base = copy.deepcopy(load_fixture("examples/full-repository.json")["body"])
    owner, name = full_name.split("/")
    base.update(id=abs(hash(full_name)) % 10**9, full_name=full_name, name=name, archived=False)
    base["owner"]["login"] = owner
    base.update(changes)
    return base


@dataclass
class Route:
    status: int
    body: Any
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def etag(self) -> str:
        digest = hashlib.sha256(json.dumps(self.body, sort_keys=True).encode()).hexdigest()
        return f'"{digest[:32]}"'


class FakeGitHub:
    def __init__(self, *, limit: int = 5000, remaining: int | None = None) -> None:
        self.routes: dict[str, Route] = {}
        self.limit = limit
        self.remaining = limit if remaining is None else remaining
        self.reset_at = 1_900_000_000
        self.requests: list[httpx.Request] = []
        self.statuses: list[int] = []
        self.secondary_limited: list[dict[str, str]] = []  # queued secondary-limit responses
        self.graphql_responses: list[tuple[int, dict[str, Any], dict[str, str]]] = []

    # registration ----------------------------------------------------------

    def add(
        self, url: str, body: Any, *, status: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        self.routes[str(httpx.URL(url if url.startswith("http") else API + url))] = Route(
            status, body, headers or {}
        )

    def add_list(
        self, path: str, items: list[Any], params: dict[str, Any], *, page_size: int
    ) -> None:
        """Register a paginated list the way GitHub serves it, with Link headers."""
        pages = [items[i : i + page_size] for i in range(0, len(items), page_size)] or [[]]
        for index, chunk in enumerate(pages, start=1):
            query = dict(params, per_page=page_size)
            if index > 1:
                query["page"] = index
            url = httpx.URL(API + path).copy_with(
                params=sorted((k, str(v)) for k, v in query.items())
            )
            headers = {}
            if index < len(pages):
                nxt = httpx.URL(API + path).copy_with(
                    params=sorted(
                        (k, str(v))
                        for k, v in dict(params, per_page=page_size, page=index + 1).items()
                    )
                )
                headers["link"] = f'<{nxt}>; rel="next"'
            self.routes[str(url)] = Route(200, chunk, headers)

    # transport -------------------------------------------------------------

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _rate_headers(self, resource: str) -> dict[str, str]:
        return {
            "x-ratelimit-limit": str(self.limit),
            "x-ratelimit-remaining": str(self.remaining),
            "x-ratelimit-used": str(self.limit - self.remaining),
            "x-ratelimit-reset": str(self.reset_at),
            "x-ratelimit-resource": resource,
        }

    def _respond(self, status: int, body: Any, headers: dict[str, str]) -> httpx.Response:
        self.statuses.append(status)
        content = b"" if body is None else json.dumps(body).encode()
        return httpx.Response(status, content=content, headers=headers)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        is_graphql = request.url.path == "/graphql"
        resource = (
            "graphql" if is_graphql else ("search" if "/search/" in request.url.path else "core")
        )

        if self.secondary_limited:
            extra = self.secondary_limited.pop(0)
            return self._respond(
                403,
                {"message": "You have exceeded a secondary rate limit."},
                {**self._rate_headers(resource), **extra},
            )
        if self.remaining <= 0:
            return self._respond(
                403, {"message": "API rate limit exceeded."}, self._rate_headers(resource)
            )
        if is_graphql:
            self.remaining -= 1
            status, body, headers = self.graphql_responses.pop(0)
            return self._respond(status, body, {**self._rate_headers("graphql"), **headers})

        url = str(request.url.copy_with(params=sorted(request.url.params.multi_items())))
        route = self.routes.get(url)
        if route is None:
            self.remaining -= 1
            return self._respond(404, {"message": "Not Found"}, self._rate_headers(resource))
        if route.status == 200 and request.headers.get("if-none-match") == route.etag:
            # GitHub: an authenticated 304 does not count against the primary limit.
            return self._respond(304, None, {**self._rate_headers(resource), "etag": route.etag})
        self.remaining -= 1
        headers = {**self._rate_headers(resource), **route.headers}
        if route.status == 200:
            headers["etag"] = route.etag
        return self._respond(route.status, route.body, headers)

    # helpers ---------------------------------------------------------------

    @property
    def count_200(self) -> int:
        return self.statuses.count(200)

    @property
    def count_304(self) -> int:
        return self.statuses.count(304)
