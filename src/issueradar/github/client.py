"""The only module that talks to GitHub.

* REST: ``GET`` only, with ETag caching. Any other method is refused before a
  request is built.
* GraphQL: queries only. Mutations and subscriptions are refused after parsing
  the document.
* Every response updates the API budget; a request is not started when the
  budget is inside its safety margin.
* Rate limits are handled the way GitHub's docs describe: honour
  ``retry-after``, otherwise wait at least a minute for a secondary limit, back
  off exponentially, and give up after a fixed number of retries. A primary
  limit that is used up stops the run with ``QuotaExhausted`` instead of
  sleeping for up to an hour, so the caller can save progress and resume later.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import httpx

from issueradar.brand import BRAND
from issueradar.config.settings import GitHubSettings
from issueradar.github.budget import ApiBudget
from issueradar.github.cache import CachedResponse, EtagCache, MemoryEtagCache, token_fingerprint
from issueradar.github.errors import (
    GitHubHTTPError,
    Gone,
    GraphQLQueryError,
    GraphQLTimeout,
    NotFound,
    QuotaExhausted,
    ReadOnlyViolation,
    SecondaryRateLimited,
)
from issueradar.github.guard import ensure_read_only_graphql, ensure_read_only_rest

log = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
_LINK_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')
API_VERSION = "2022-11-28"


@dataclass(frozen=True)
class GitHubResponse:
    url: str
    status: int
    data: Any
    headers: Mapping[str, str]
    from_cache: bool
    link: str | None

    @property
    def next_url(self) -> str | None:
        if not self.link:
            return None
        match = _LINK_NEXT.search(self.link)
        return match.group(1) if match else None


def _resource_for(url: str, graphql_url: str) -> str:
    if url.startswith(graphql_url):
        return "graphql"
    if "/search/" in url:
        return "search"
    return "core"


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        return str(body.get("message", ""))[:200]
    return ""


class GitHubClient:
    def __init__(
        self,
        settings: GitHubSettings,
        token: str | None,
        *,
        cache: EtagCache | None = None,
        budget: ApiBudget | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.budget = budget or ApiBudget(settings.budget.safety_margin)
        self.cache: EtagCache = cache or MemoryEtagCache()
        self._fingerprint = token_fingerprint(token)
        self._sleep = sleep
        self._clock = clock
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": settings.user_agent,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.authenticated = bool(token)
        self._http = httpx.AsyncClient(
            headers=headers,
            timeout=settings.request_timeout_seconds,
            transport=transport,
            follow_redirects=True,  # renamed and transferred repositories redirect
        )
        self._semaphore = asyncio.Semaphore(settings.concurrency.max_in_flight)

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ REST

    def url_for(self, path: str, params: Mapping[str, Any] | None = None) -> str:
        base = path if path.startswith("http") else f"{self.settings.api_url}{path}"
        url = httpx.URL(base)
        if params:
            merged = dict(url.params)
            merged.update({k: str(v) for k, v in params.items()})
            url = url.copy_with(params=sorted(merged.items()))
        return str(url)

    async def request(
        self, method: str, path: str, *, params: Mapping[str, Any] | None = None
    ) -> GitHubResponse:
        """Generic entry point. Exists so the guard is exercised on every path."""
        ensure_read_only_rest(method)
        return await self.get(path, params=params)

    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        conditional: bool = True,
    ) -> GitHubResponse:
        url = self.url_for(path, params)
        key = f"{self._fingerprint}:{url}"
        cached = self.cache.get(key) if conditional else None
        extra = {"If-None-Match": cached.etag} if cached else {}
        response = await self._send("GET", url, headers=extra)
        if response.status_code == 304 and cached is not None:
            return GitHubResponse(
                url=url,
                status=304,
                data=json.loads(cached.body),
                headers=response.headers,
                from_cache=True,
                link=cached.link,
            )
        data = response.json() if response.content else None
        link = response.headers.get("link")
        etag = response.headers.get("etag")
        if conditional and etag and response.status_code == 200:
            self.cache.put(key, url, CachedResponse(etag=etag, body=response.text, link=link))
        return GitHubResponse(
            url=url,
            status=response.status_code,
            data=data,
            headers=response.headers,
            from_cache=False,
            link=link,
        )

    async def paginate(
        self, path: str, *, params: Mapping[str, Any] | None = None, max_pages: int
    ) -> AsyncIterator[GitHubResponse]:
        """Yield each page, following ``Link: rel="next"`` up to ``max_pages``."""
        response = await self.get(path, params=params)
        yield response
        pages = 1
        while response.next_url and pages < max_pages:
            response = await self.get(response.next_url)
            pages += 1
            yield response

    # --------------------------------------------------------------- GraphQL

    async def graphql(self, query: str, variables: Mapping[str, Any] | None = None) -> Any:
        """Run a read-only GraphQL query and return its ``data``.

        GitHub can report failures, including rate limits, inside an HTTP 200
        response, so the ``errors`` array is always checked.
        """
        ensure_read_only_graphql(query)
        payload = {"query": query, "variables": dict(variables or {})}
        for attempt in range(self.settings.retry.max_retries + 1):
            response = await self._send("POST", self.settings.graphql_url, json_body=payload)
            body = response.json()
            errors = body.get("errors") or []
            data = body.get("data")
            if isinstance(data, dict):
                rate = data.get("rateLimit")
                if isinstance(rate, dict) and isinstance(rate.get("cost"), int):
                    self.budget.add_graphql_cost(rate["cost"])
                    log.info("graphql cost=%s remaining=%s", rate["cost"], rate.get("remaining"))
            if not errors:
                return data
            if any(_is_rate_limit_error(e) for e in errors):
                if response.headers.get("x-ratelimit-remaining") == "0":
                    raise QuotaExhausted("graphql", _reset(response.headers))
                if attempt == self.settings.retry.max_retries:
                    raise SecondaryRateLimited("GraphQL kept hitting a secondary rate limit.")
                await self._sleep(self._secondary_wait(response.headers, attempt))
                continue
            raise GraphQLQueryError(errors, data)
        raise SecondaryRateLimited("GraphQL kept hitting a secondary rate limit.")  # unreachable

    # ------------------------------------------------------------- transport

    async def _send(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Any = None,
    ) -> httpx.Response:
        # Second line of defence: the only non-GET request is a GraphQL POST
        # whose document already passed ensure_read_only_graphql.
        if method != "GET" and not (method == "POST" and url == self.settings.graphql_url):
            raise ReadOnlyViolation(f"Refused {method} {url}: {BRAND.name} only reads from GitHub.")
        resource = _resource_for(url, self.settings.graphql_url)
        retry = self.settings.retry
        for attempt in range(retry.max_retries + 1):
            self.budget.check(resource)
            async with self._semaphore:
                started = self._clock()
                response = await self._http.request(method, url, headers=headers, json=json_body)
                elapsed = self._clock() - started
            self.budget.observe(
                resource, response.headers, not_modified=response.status_code == 304
            )
            log.debug("%s %s -> %s in %.2fs", method, url, response.status_code, elapsed)
            status = response.status_code

            if status in (200, 201, 304):
                if resource == "graphql" and status == 200 and _is_timeout_body(response):
                    raise GraphQLTimeout("GitHub stopped the GraphQL query after its time limit.")
                return response
            if status in (403, 429):
                message = _message(response)
                secondary = (
                    "secondary rate limit" in message.lower() or "retry-after" in response.headers
                )
                if not secondary and response.headers.get("x-ratelimit-remaining") == "0":
                    raise QuotaExhausted(resource, _reset(response.headers))
                if not secondary:
                    raise GitHubHTTPError(status, message, url)
                if attempt == retry.max_retries:
                    raise SecondaryRateLimited(
                        f"GitHub kept answering with a secondary rate limit for {url}; "
                        f"gave up after {retry.max_retries} retries."
                    )
                await self._sleep(self._secondary_wait(response.headers, attempt))
                continue
            if status == 404:
                raise NotFound(f"Not found: {url} (it may be private, deleted or renamed).")
            if status == 410:
                raise Gone(f"Gone: {url} (deleted, or issues are turned off for this repo).")
            if status == 502 and resource == "graphql":
                raise GraphQLTimeout("GitHub stopped the GraphQL query after its time limit.")
            if status >= 500 and attempt < retry.max_retries:
                wait = min(
                    retry.server_error_wait_seconds * retry.backoff_factor**attempt,
                    retry.max_wait_seconds,
                )
                await self._sleep(wait)
                continue
            raise GitHubHTTPError(status, _message(response), url)
        raise GitHubHTTPError(0, "retries exhausted", url)  # pragma: no cover

    def _secondary_wait(self, headers: Mapping[str, str], attempt: int) -> float:
        """Wait time for a secondary limit, following GitHub's documented order."""
        retry = self.settings.retry
        after = headers.get("retry-after")
        if after is not None:
            try:
                return min(float(after), retry.max_wait_seconds)
            except ValueError:
                pass
        if headers.get("x-ratelimit-remaining") == "0":
            reset = _reset(headers)
            if reset is not None:
                return min(max(reset - self._clock(), 0.0), retry.max_wait_seconds)
        backoff = retry.min_secondary_wait_seconds * retry.backoff_factor**attempt
        return min(backoff, retry.max_wait_seconds)


def _reset(headers: Mapping[str, str]) -> float | None:
    value = headers.get("x-ratelimit-reset")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _is_rate_limit_error(error: Mapping[str, Any]) -> bool:
    kind = str(error.get("type", "")).upper()
    message = str(error.get("message", "")).lower()
    return kind == "RATE_LIMITED" or "rate limit" in message


def _is_timeout_body(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    errors = body.get("errors") if isinstance(body, dict) else None
    if not isinstance(errors, list):
        return False
    return any(
        "couldn't respond to your request in time" in str(e.get("message", "")) for e in errors
    )


def token_from_env(env: Mapping[str, str]) -> tuple[str | None, str]:
    """Pick a token from the environment and say where it came from."""
    own = BRAND.env("GITHUB_TOKEN")
    if env.get(own):
        return env[own], own
    if env.get("GITHUB_TOKEN"):
        return env["GITHUB_TOKEN"], "GITHUB_TOKEN"
    return None, "none"
