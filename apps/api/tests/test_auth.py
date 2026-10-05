"""Sign in with GitHub, sessions, CSRF, token storage, refresh and reconnect."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session as OrmSession

from conftest import FakeGitHub, FakeJobs, csrf, sign_in
from firstpr_api.main import create_app
from firstpr_api.settings import Settings
from firstpr_platform.db import GitHubAccount, Session, User, utcnow


def test_login_sends_the_browser_to_github_with_state_and_pkce(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/github/login", follow_redirects=False)
    assert resp.status_code == 302
    url = httpx.URL(resp.headers["location"])
    query = {k: v[0] for k, v in parse_qs(url.query.decode()).items()}
    assert str(url).startswith("https://github.com/login/oauth/authorize?")
    assert query["client_id"] == "Iv1.test"
    assert query["redirect_uri"] == "http://testserver/api/v1/auth/github/callback"
    assert query["code_challenge_method"] == "S256" and len(query["code_challenge"]) == 43
    assert client.cookies.get("firstpr_oauth") == query["state"]


def test_sign_in_creates_user_session_and_encrypted_tokens(
    client: TestClient, sync_db: OrmSession
) -> None:
    resp = sign_in(client)
    assert resp.status_code == 302 and resp.headers["location"] == "/home"
    assert client.cookies.get("firstpr_session") and client.cookies.get("firstpr_csrf")
    set_cookie = resp.headers.get_list("set-cookie")
    assert any(
        "firstpr_session=" in c and "HttpOnly" in c and "SameSite=lax" in c for c in set_cookie
    )

    me = client.get("/api/v1/me")
    assert me.status_code == 200
    body = me.json()
    assert body["handle"] == "MuskanScripts" and body["email"] == "muskan@example.com"
    assert body["github"] == {"login": "MuskanScripts", "status": "connected"}
    assert body["role"] == "user"
    assert "ghu_" not in me.text and "ghr_" not in me.text

    account = sync_db.scalar(select(GitHubAccount))
    assert account is not None and account.github_id == 4242
    assert b"ghu_test" not in account.access_token
    assert account.refresh_token is not None and b"ghr_test" not in account.refresh_token
    stored = sync_db.scalar(select(Session))
    assert stored is not None and stored.id_hash != client.cookies.get("firstpr_session")


def test_signing_in_again_updates_the_same_user(client: TestClient, sync_db: OrmSession) -> None:
    sign_in(client)
    sign_in(client)
    assert len(sync_db.scalars(select(User)).all()) == 1


def test_state_must_match_and_is_single_use(client: TestClient) -> None:
    login = client.get("/api/v1/auth/github/login", follow_redirects=False)
    state = parse_qs(httpx.URL(login.headers["location"]).query.decode())["state"][0]

    wrong = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "good-code", "state": "not-the-state"},
        follow_redirects=False,
    )
    assert wrong.headers["location"] == "/?signin=expired"

    client.cookies.set("firstpr_oauth", state, path="/api/v1/auth")
    first = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "good-code", "state": state},
        follow_redirects=False,
    )
    assert first.headers["location"] == "/home"
    client.cookies.set("firstpr_oauth", state, path="/api/v1/auth")
    again = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "good-code", "state": state},
        follow_redirects=False,
    )
    assert again.headers["location"] == "/?signin=expired"


def test_cancel_and_bad_code(client: TestClient) -> None:
    cancelled = client.get(
        "/api/v1/auth/github/callback", params={"error": "access_denied"}, follow_redirects=False
    )
    assert cancelled.headers["location"] == "/?signin=cancelled"

    login = client.get("/api/v1/auth/github/login", follow_redirects=False)
    state = parse_qs(httpx.URL(login.headers["location"]).query.decode())["state"][0]
    bad = client.get(
        "/api/v1/auth/github/callback",
        params={"code": "wrong", "state": state},
        follow_redirects=False,
    )
    assert bad.headers["location"] == "/?signin=failed"
    assert client.get("/api/v1/me").status_code == 401


def test_return_to_stays_on_this_site(client: TestClient) -> None:
    assert (
        sign_in(client, "/explore?level=beginner").headers["location"] == "/explore?level=beginner"
    )
    for evil in ("//evil.example", "https://evil.example", "/\\evil.example"):
        assert sign_in(client, evil).headers["location"] == "/home"


def test_logout_needs_csrf_and_ends_the_session(client: TestClient, sync_db: OrmSession) -> None:
    sign_in(client)
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "guess"}).status_code == 403
    old_cookie = client.cookies.get("firstpr_session")
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204
    assert client.get("/api/v1/me").status_code == 401
    # The old cookie does not work any more, even if someone kept a copy.
    client.cookies.set("firstpr_session", old_cookie or "")
    assert client.get("/api/v1/me").status_code == 401
    assert sync_db.scalar(select(Session.revoked_at)) is not None


def test_expired_session_is_rejected(client: TestClient, sync_db: OrmSession) -> None:
    sign_in(client)
    sync_db.execute(update(Session).values(expires_at=utcnow() - timedelta(minutes=1)))
    sync_db.commit()
    # The Redis entry never outlives the session; drop it as time passing would.
    client.portal.call(client.app.state.redis.flushall)  # type: ignore[union-attr]
    assert client.get("/api/v1/me").status_code == 401


def _age_verification(sync_db: OrmSession) -> None:
    sync_db.execute(update(GitHubAccount).values(last_verified_at=utcnow() - timedelta(hours=1)))
    sync_db.commit()


def test_revoked_app_shows_reconnect_and_signing_in_fixes_it(
    client: TestClient, sync_db: OrmSession, github: FakeGitHub
) -> None:
    sign_in(client)
    github.valid_tokens.clear()  # the user revoked the app on github.com
    _age_verification(sync_db)
    assert client.get("/api/v1/me").json()["github"]["status"] == "reconnect_needed"

    sign_in(client)
    assert client.get("/api/v1/me").json()["github"]["status"] == "connected"


def test_verification_is_not_repeated_on_every_request(
    client: TestClient, github: FakeGitHub
) -> None:
    sign_in(client)
    before = len(github.requests)
    for _ in range(5):
        client.get("/api/v1/me")
    assert len(github.requests) == before


def test_expiring_token_is_refreshed(
    client: TestClient, sync_db: OrmSession, github: FakeGitHub
) -> None:
    sign_in(client)
    sync_db.execute(update(GitHubAccount).values(access_expires_at=utcnow() + timedelta(minutes=1)))
    sync_db.commit()
    _age_verification(sync_db)
    assert client.get("/api/v1/me").json()["github"]["status"] == "connected"
    sync_db.expire_all()
    account = sync_db.scalar(select(GitHubAccount))
    assert account is not None and account.access_expires_at is not None
    assert account.access_expires_at > utcnow() + timedelta(hours=7)


def test_failed_refresh_means_reconnect(
    client: TestClient, sync_db: OrmSession, github: FakeGitHub
) -> None:
    sign_in(client)
    github.refresh_works = False
    sync_db.execute(update(GitHubAccount).values(access_expires_at=utcnow() - timedelta(minutes=1)))
    sync_db.commit()
    _age_verification(sync_db)
    assert client.get("/api/v1/me").json()["github"]["status"] == "reconnect_needed"


def test_login_is_rate_limited(client: TestClient, settings: Settings) -> None:
    for _ in range(settings.login_attempts_per_10_minutes):
        assert client.get("/api/v1/auth/github/login", follow_redirects=False).status_code == 302
    assert client.get("/api/v1/auth/github/login", follow_redirects=False).status_code == 429


def test_sign_in_off_until_configured(sync_db: OrmSession, settings: Settings) -> None:
    import fakeredis

    plain = settings.model_copy(update={"github_client_id": ""})
    with TestClient(create_app(plain, redis=fakeredis.FakeAsyncRedis())) as client:
        assert client.get("/api/v1/auth/github/login", follow_redirects=False).status_code == 503
        assert client.get("/api/v1/me").status_code == 401


def test_admin_logins_get_the_admin_role(
    sync_db: OrmSession, settings: Settings, github: FakeGitHub
) -> None:
    import fakeredis

    admin_settings = settings.model_copy(update={"admin_logins": " muskanscripts , other"})
    app = create_app(
        admin_settings,
        redis=fakeredis.FakeAsyncRedis(),
        github_transport=httpx.MockTransport(github.handler),
        jobs=FakeJobs(),
    )
    with TestClient(app, base_url="http://testserver") as client:
        sign_in(client)
        assert client.get("/api/v1/me").json()["role"] == "admin"
