"""Security headers, settings that refuse unsafe cookies, invite-only sign-in,
deleting an account, metrics for alerts, and browser error reports."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from conftest import FakeJobs, add_card, csrf, sign_in
from firstpr_api.settings import Settings
from firstpr_platform.db import Notification, Profile, User, Workspace


def test_security_headers_on_every_answer(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in resp.headers["content-security-policy"]
    assert client.get("/api/v1/me").headers["x-frame-options"] == "DENY"  # errors too


def test_https_sites_must_use_secure_cookies() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(public_url="https://firstpr.dev", cookie_secure=False)
    assert Settings(public_url="https://firstpr.dev", cookie_secure=True).cookie_secure
    assert Settings(public_url="http://localhost:8080", cookie_secure=False)


def test_invite_only_sign_in(client: TestClient, settings: Settings, sync_db: OrmSession) -> None:
    live = client.app.state.settings  # type: ignore[attr-defined]
    live.invite_only = True
    resp = sign_in(client)
    assert resp.headers["location"] == "/?signin=invite"
    assert sync_db.scalar(select(func.count(User.id))) == 0  # nothing stored
    live.invite_logins = "someone, MuskanScripts"
    assert sign_in(client).headers["location"] == "/home"


def test_delete_my_account(client: TestClient, sync_db: OrmSession, jobs: FakeJobs) -> None:
    add_card(sync_db, "pallets/flask", 1)
    sign_in(client)
    client.put("/api/v1/me/profile", json={}, headers=csrf(client))
    client.get("/api/v1/me/today")
    uid = sync_db.scalar(select(User.id))
    sync_db.add(Notification(user_id=uid, kind="badge", title="t", body="b", dedupe_key="k"))
    sync_db.add(
        Workspace(
            user_id=uid,
            repo_full_name="a/b",
            number=1,
            issue_title="x",
            mode="local",
            status="ready",
            steps=[],
        )
    )
    sync_db.commit()

    assert (
        client.request("DELETE", "/api/v1/me", json={"confirm": "MuskanScripts"}).status_code == 403
    )
    wrong = client.request(
        "DELETE", "/api/v1/me", json={"confirm": "someone"}, headers=csrf(client)
    )
    assert wrong.status_code == 422
    done = client.request(
        "DELETE", "/api/v1/me", json={"confirm": "muskanscripts"}, headers=csrf(client)
    )
    assert done.status_code == 204
    assert client.get("/api/v1/me").status_code == 401
    sync_db.expire_all()
    for model in (User, Profile, Notification, Workspace):
        assert sync_db.scalar(select(func.count()).select_from(model)) == 0, model
    assert jobs.queued[-1][:2] == ("forget_user", (uid,))


def test_metrics_need_the_token(client: TestClient) -> None:
    client.get("/api/v1/health")
    assert client.get("/api/v1/metrics").status_code == 404  # off without a token
    live = client.app.state.settings  # type: ignore[attr-defined]
    live.metrics_token = SecretStr("metrics-secret")
    assert (
        client.get("/api/v1/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 404
    )
    redis = client.app.state.redis  # type: ignore[attr-defined]
    budget = json.dumps({"limit": 5000, "remaining": 500, "checked_at": time.time()})
    client.portal.call(redis.set, "firstpr:budget:app", budget)
    minute = int(time.time() // 60) - 1
    client.portal.call(redis.set, f"firstpr:requests:{minute}", 10)
    client.portal.call(redis.set, f"firstpr:errors:{minute}", 2)
    text = client.get("/api/v1/metrics", headers={"Authorization": "Bearer metrics-secret"}).text
    assert 'firstpr_github_budget_left_ratio{token="app"} 0.1' in text
    assert "firstpr_error_ratio_5m 0.2" in text
    assert "firstpr_queue_oldest_job_seconds" in text and "firstpr_workspace_failures_24h 0" in text


def test_browser_errors_are_accepted_and_limited(client: TestClient) -> None:
    for _ in range(12):
        resp = client.post(
            "/api/v1/client-errors", json={"message": "TypeError: x", "path": "/home"}
        )
        assert resp.status_code == 204
