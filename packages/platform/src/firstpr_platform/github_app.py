"""The app's own installation token, used to sync the shared catalogue.

GitHub issues it for one hour in exchange for a short-lived JWT signed with the
app's private key. It is kept in memory only and renewed five minutes before it
runs out.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

import httpx
import jwt

API_URL = "https://api.github.com"
RENEW_BEFORE_SECONDS = 300


class AppAuthError(Exception):
    """The app's ID, key or installation is wrong, or GitHub refused them."""


class AppTokenSource:
    def __init__(
        self,
        app_id: str,
        private_key: str,
        installation_id: int | None = None,
        *,
        api_url: str = API_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._app_id = app_id
        self._key = private_key
        self._installation_id = installation_id
        self._api = api_url.rstrip("/")
        self._transport = transport
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0

    def app_jwt(self) -> str:
        now = int(self._clock())
        # Issued a minute in the past to allow for clock drift, valid for 9 minutes.
        claims = {"iat": now - 60, "exp": now + 540, "iss": self._app_id}
        return jwt.encode(claims, self._key, algorithm="RS256")

    async def token(self) -> str:
        if self._token and self._expires_at - RENEW_BEFORE_SECONDS > self._clock():
            return self._token
        headers = {
            "Authorization": f"Bearer {self.app_jwt()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "FirstPR",
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=15) as client:
            installation = self._installation_id
            if installation is None:
                found = await client.get(f"{self._api}/app/installations", headers=headers)
                if found.status_code != 200 or not found.json():
                    raise AppAuthError(f"no installation found (HTTP {found.status_code})")
                installation = int(found.json()[0]["id"])
                self._installation_id = installation
            resp = await client.post(
                f"{self._api}/app/installations/{installation}/access_tokens", headers=headers
            )
        if resp.status_code != 201:
            raise AppAuthError(f"GitHub refused the installation token (HTTP {resp.status_code})")
        body = resp.json()
        self._token = str(body["token"])
        expires = datetime.fromisoformat(str(body["expires_at"]).replace("Z", "+00:00"))
        self._expires_at = expires.timestamp()
        return self._token
