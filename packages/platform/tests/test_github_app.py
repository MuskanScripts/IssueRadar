"""The installation token source, against a fake GitHub."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from firstpr_platform.github_app import AppAuthError, AppTokenSource


@pytest.fixture(scope="module")
def keys() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public


class FakeGitHub:
    def __init__(self, public_key: str, now: float) -> None:
        self.public_key = public_key
        self.now = now
        self.issued = 0
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.path}")
        claims = jwt.decode(
            request.headers["authorization"].removeprefix("Bearer "),
            self.public_key,
            algorithms=["RS256"],
            options={"verify_exp": False, "verify_iat": False},
        )
        assert claims["iss"] == "12345"
        if request.url.path == "/app/installations":
            return httpx.Response(200, json=[{"id": 77, "account": {"login": "MuskanScripts"}}])
        if request.url.path == "/app/installations/77/access_tokens":
            self.issued += 1
            expires = datetime.fromtimestamp(self.now, UTC) + timedelta(hours=1)
            return httpx.Response(
                201,
                json={"token": f"ghs_test_{self.issued}", "expires_at": expires.isoformat()},
            )
        return httpx.Response(404)


async def test_token_is_cached_and_renewed_before_it_expires(keys: tuple[str, str]) -> None:
    private, public = keys
    clock = [1_800_000_000.0]
    fake = FakeGitHub(public, clock[0])
    source = AppTokenSource(
        "12345", private, transport=httpx.MockTransport(fake.handler), clock=lambda: clock[0]
    )
    assert await source.token() == "ghs_test_1"
    assert await source.token() == "ghs_test_1"
    assert fake.calls == ["GET /app/installations", "POST /app/installations/77/access_tokens"]

    clock[0] += 3600 - 200  # inside the last five minutes
    fake.now = clock[0]
    assert await source.token() == "ghs_test_2"
    assert fake.calls[-1] == "POST /app/installations/77/access_tokens"
    assert fake.calls.count("GET /app/installations") == 1


async def test_refusal_is_a_clear_error(keys: tuple[str, str]) -> None:
    private, _ = keys
    source = AppTokenSource(
        "12345",
        private,
        installation_id=77,
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={})),
    )
    with pytest.raises(AppAuthError, match="401"):
        await source.token()
