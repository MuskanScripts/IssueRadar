"""Product analytics: the sign-up funnel, sent to PostHog's capture API.

Off unless a PostHog project key is set. Failures never reach users: a lost
event is better than a slow or broken page. Events carry ids, never names,
emails or tokens.

The funnel: intro_viewed, stack_picker_used, sign_in_clicked (from the web
page, by an anonymous id), signed_in (linked to that id), first_pick_started,
first_pr_merged.
"""

from __future__ import annotations

from typing import Any

import httpx

FUNNEL = (
    "intro_viewed",
    "stack_picker_used",
    "sign_in_clicked",
    "signed_in",
    "first_pick_started",
    "first_pr_merged",
)
# Events the web page may send for an anonymous visitor.
FROM_BROWSER = frozenset(
    {"intro_viewed", "stack_picker_used", "sign_in_clicked", "trending_viewed"}
)


def user_id(platform_user_id: int) -> str:
    return f"user:{platform_user_id}"


class Analytics:
    def __init__(
        self,
        key: str,
        host: str = "https://us.i.posthog.com",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.key = key
        self.host = host.rstrip("/")
        self.transport = transport

    @property
    def on(self) -> bool:
        return bool(self.key)

    async def capture(
        self, event: str, distinct_id: str, properties: dict[str, Any] | None = None
    ) -> bool:
        if not self.on or not distinct_id:
            return False
        body = {
            "api_key": self.key,
            "event": event,
            "distinct_id": distinct_id,
            "properties": {**(properties or {}), "$lib": "firstpr"},
        }
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=3) as client:
                resp = await client.post(f"{self.host}/capture/", json=body)
            return resp.status_code < 300
        except httpx.HTTPError:
            return False

    async def identify(self, platform_user_id: int, anonymous_id: str | None) -> bool:
        """Join the visitor's anonymous events to the signed-in user."""
        props = {"$anon_distinct_id": anonymous_id} if anonymous_id else {}
        return await self.capture("$identify", user_id(platform_user_id), props)
