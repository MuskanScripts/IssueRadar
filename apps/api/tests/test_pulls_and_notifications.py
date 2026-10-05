"""My pull requests, notifications and their stream, email settings and unsubscribe."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from conftest import FakeJobs, csrf, sign_in
from firstpr_api import notifications as api_notifications
from firstpr_api.settings import Settings
from firstpr_platform import notify
from firstpr_platform.db import EmailPrefs, Notification, TrackedPull, User


def user_id(sync_db: OrmSession) -> int:
    found = sync_db.scalar(select(User.id))
    assert found is not None
    return found


def add_pull(sync_db: OrmSession, uid: int, number: int, status: str, **values: object) -> None:
    now = datetime.now(UTC)
    sync_db.add(
        TrackedPull(
            user_id=uid,
            repo_full_name="pallets/flask",
            number=number,
            title=f"PR {number}",
            url=f"https://github.com/pallets/flask/pull/{number}",
            state="closed" if status in ("merged", "closed_unmerged") else "open",
            merged=status == "merged",
            draft=False,
            status=status,
            needs_you="Do the thing",
            reasons=["because"],
            nudge="Hi! Just checking in" if status == "stale" else None,
            days_quiet=9 if status == "stale" else 1,
            timeline=[{"at": now.isoformat(), "text": "@maintainer reviewed"}],
            checked_at=now,
            changed_at=now - timedelta(minutes=number),
            **values,
        )
    )
    sync_db.commit()


def test_my_pull_requests_put_what_needs_me_first(client: TestClient, sync_db: OrmSession) -> None:
    sign_in(client)
    uid = user_id(sync_db)
    add_pull(sync_db, uid, 1, "merged")
    add_pull(sync_db, uid, 2, "waiting_for_review")
    add_pull(sync_db, uid, 3, "stale")
    add_pull(sync_db, uid, 4, "changes_requested")
    body = client.get("/api/v1/me/pulls").json()
    assert [p["number"] for p in body["items"]] == [4, 3, 2, 1]
    stale = body["items"][1]
    assert stale["needs_you"] and stale["nudge"].startswith("Hi!")
    assert stale["status_label"] == "Stale" and stale["timeline"]
    assert body["items"][2]["needs_you"] is False


def test_refresh_pull_requests_once_in_a_while(client: TestClient, jobs: FakeJobs) -> None:
    sign_in(client)
    assert client.post("/api/v1/me/pulls/refresh").status_code == 403
    first = client.post("/api/v1/me/pulls/refresh", headers=csrf(client))
    assert first.status_code == 200 and first.json()["next_refresh_at"]
    assert jobs.queued[-1][0] == "track_user"
    assert client.post("/api/v1/me/pulls/refresh", headers=csrf(client)).status_code == 429


def test_notifications_read_and_unread(client: TestClient, sync_db: OrmSession) -> None:
    sign_in(client)
    uid = user_id(sync_db)
    for i in range(3):
        sync_db.add(
            Notification(
                user_id=uid,
                kind="approved",
                title=f"T{i}",
                body="b",
                dedupe_key=f"k{i}",
                link="/pulls",
            )
        )
    sync_db.commit()
    body = client.get("/api/v1/me/notifications").json()
    assert body["unread"] == 3 and [n["title"] for n in body["items"]] == ["T2", "T1", "T0"]
    first_id = body["items"][-1]["id"]
    assert client.post("/api/v1/me/notifications/read", json={"ids": [first_id]}).status_code == 403
    one = client.post(
        "/api/v1/me/notifications/read", json={"ids": [first_id]}, headers=csrf(client)
    ).json()
    assert one["unread"] == 2
    every = client.post(
        "/api/v1/me/notifications/read", json={"all": True}, headers=csrf(client)
    ).json()
    assert every["unread"] == 0


def test_the_stream_starts_with_the_unread_count(
    client: TestClient, sync_db: OrmSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_notifications, "STREAM_SECONDS", 0)
    sign_in(client)
    sync_db.add(
        Notification(user_id=user_id(sync_db), kind="approved", title="T", body="b", dedupe_key="k")
    )
    sync_db.commit()
    resp = client.get("/api/v1/me/notifications/stream")
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.text == "event: unread\ndata: 1\n\n"
    client.cookies.clear()
    assert client.get("/api/v1/me/notifications/stream").status_code == 401


def test_email_settings(client: TestClient, sync_db: OrmSession) -> None:
    sign_in(client)
    body = client.get("/api/v1/me/email").json()
    assert body == {
        "address": "muskan@example.com",
        "enabled": True,
        "digest": True,
        "sending": False,
    }
    saved = client.put(
        "/api/v1/me/email", json={"enabled": False, "digest": True}, headers=csrf(client)
    ).json()
    assert saved["enabled"] is False
    prefs = sync_db.scalar(select(EmailPrefs))
    assert prefs is not None and prefs.enabled is False


def test_one_click_unsubscribe(client: TestClient, sync_db: OrmSession, settings: Settings) -> None:
    sign_in(client)
    uid = user_id(sync_db)
    client.cookies.clear()  # the link works without being signed in
    key = notify.signing_key(settings.token_keys.get_secret_value())
    good = notify.unsubscribe_token(key, uid)

    bad = client.get(f"/api/v1/email/unsubscribe?u={uid}&t=nope", follow_redirects=False)
    assert bad.headers["location"] == "/email-off?bad=1"
    other = notify.unsubscribe_token(key, uid + 1)
    assert (
        client.get(f"/api/v1/email/unsubscribe?u={uid}&t={other}", follow_redirects=False).headers[
            "location"
        ]
        == "/email-off?bad=1"
    )

    resp = client.get(f"/api/v1/email/unsubscribe?u={uid}&t={good}", follow_redirects=False)
    assert resp.headers["location"] == "/email-off"
    prefs = sync_db.scalar(select(EmailPrefs))
    assert prefs is not None and prefs.enabled is False

    prefs.enabled = True
    sync_db.commit()
    one_click = client.post(
        f"/api/v1/email/unsubscribe?u={uid}&t={good}",
        content="List-Unsubscribe=One-Click",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert one_click.status_code == 200
    sync_db.expire_all()
    assert sync_db.scalar(select(EmailPrefs.enabled)) is False
    assert client.post(f"/api/v1/email/unsubscribe?u={uid}&t=nope").status_code == 400
