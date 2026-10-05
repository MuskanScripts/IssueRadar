"""HTTP for delivery channels (Telegram, Discord, Slack webhooks).

This is the only other module allowed to import httpx (see test_read_only.py).
It refuses any GitHub host, so a delivery bug can never post to GitHub.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from issueradar.github.errors import ReadOnlyViolation

GITHUB_HOSTS = ("github.com", "api.github.com", "uploads.github.com")


class DeliveryError(Exception):
    pass


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float = 15.0,
    transport: httpx.BaseTransport | None = None,
) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host in GITHUB_HOSTS or host.endswith(".github.com"):
        raise ReadOnlyViolation(f"Refused to send a digest to {host}: it never writes to GitHub.")
    with httpx.Client(timeout=timeout, transport=transport) as client:
        response = client.post(url, json=payload)
    if response.status_code >= 400:
        raise DeliveryError(f"{host} answered {response.status_code}: {response.text[:200]}")
