"""Signing in with the FirstPR GitHub App (user authorization flow).

GitHub gives back a user access token that expires after 8 hours and a refresh
token that lasts about 6 months. Only reads are made here; the token exchange is
a POST to github.com's OAuth endpoint, not to the REST API.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from firstpr_api.db import utcnow

GITHUB_URL = "https://github.com"
API_URL = "https://api.github.com"


class GitHubAuthError(Exception):
    """GitHub refused the code or refresh token, or the token no longer works."""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    access_expires_at: datetime | None
    refresh_token: str | None
    refresh_expires_at: datetime | None


@dataclass(frozen=True)
class GitHubUser:
    id: int
    login: str
    name: str | None
    avatar_url: str | None
    email: str | None


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _expires(seconds: Any) -> datetime | None:
    return utcnow() + timedelta(seconds=int(seconds)) if seconds else None


class GitHubOAuth:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        transport: httpx.AsyncBaseTransport | None = None,
        web_url: str = GITHUB_URL,
        api_url: str = API_URL,
    ) -> None:
        self.client_id = client_id
        self._secret = client_secret
        self.redirect_uri = redirect_uri
        self._transport = transport
        self._web = web_url.rstrip("/")
        self._api = api_url.rstrip("/")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=15,
            headers={"Accept": "application/json", "User-Agent": "FirstPR"},
        )

    def authorize_url(self, state: str, code_challenge: str) -> str:
        query = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "allow_signup": "true",
        }
        return f"{self._web}/login/oauth/authorize?{urlencode(query)}"

    async def _token_request(self, data: dict[str, str]) -> Tokens:
        payload = {"client_id": self.client_id, "client_secret": self._secret, **data}
        async with self._client() as client:
            resp = await client.post(f"{self._web}/login/oauth/access_token", data=payload)
        body = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if resp.status_code != 200 or "access_token" not in body:
            # body["error"] is a short code such as bad_verification_code; safe to show.
            raise GitHubAuthError(str(body.get("error", f"HTTP {resp.status_code}")))
        return Tokens(
            access_token=body["access_token"],
            access_expires_at=_expires(body.get("expires_in")),
            refresh_token=body.get("refresh_token"),
            refresh_expires_at=_expires(body.get("refresh_token_expires_in")),
        )

    async def exchange(self, code: str, code_verifier: str) -> Tokens:
        return await self._token_request(
            {"code": code, "redirect_uri": self.redirect_uri, "code_verifier": code_verifier}
        )

    async def refresh(self, refresh_token: str) -> Tokens:
        return await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        )

    async def get_user(self, access_token: str) -> GitHubUser:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with self._client() as client:
            me = await client.get(f"{self._api}/user", headers=headers)
            if me.status_code == 401:
                raise GitHubAuthError("token no longer valid")
            me.raise_for_status()
            data = me.json()
            email = data.get("email")
            if not email:
                # Needs the "Email addresses: read" account permission; skipped if missing.
                emails = await client.get(f"{self._api}/user/emails", headers=headers)
                if emails.status_code == 200:
                    email = next(
                        (
                            e["email"]
                            for e in emails.json()
                            if e.get("primary") and e.get("verified")
                        ),
                        None,
                    )
        return GitHubUser(
            id=int(data["id"]),
            login=str(data["login"]),
            name=data.get("name"),
            avatar_url=data.get("avatar_url"),
            email=email,
        )
