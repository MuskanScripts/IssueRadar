"""Heartbeats, the activity calendar, streaks, badges and the public switch."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from conftest import csrf, sign_in
from firstpr_api import progress as api_progress
from firstpr_platform.db import DailyActivity, Profile, User


def onboard(client: TestClient, tz: str = "UTC") -> None:
    resp = client.put("/api/v1/me/profile", json={"timezone": tz}, headers=csrf(client))
    assert resp.status_code == 200


def beat(client: TestClient, visible: bool = True, idle: int = 5) -> dict[str, object]:
    resp = client.post(
        "/api/v1/me/heartbeat",
        json={"visible": visible, "idle_seconds": idle},
        headers=csrf(client),
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, object] = resp.json()
    return body


def test_a_background_tab_or_an_idle_user_earns_nothing(client: TestClient) -> None:
    sign_in(client)
    onboard(client)
    assert (
        client.post("/api/v1/me/heartbeat", json={"visible": True, "idle_seconds": 0}).status_code
        == 403
    )
    for _ in range(60):  # an hour of beats from a hidden tab
        assert beat(client, visible=False)["counted"] is False
    assert beat(client, idle=600)["counted"] is False  # nobody at the keyboard
    assert beat(client)["today_minutes"] == 1
    # Beats come once a minute; more often still counts one minute.
    for _ in range(10):
        assert beat(client)["counted"] is False
    assert beat(client)["today_minutes"] == 1


def test_minutes_count_on_the_users_own_day(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(client)
    onboard(client, tz="Asia/Kolkata")
    late = datetime(2026, 10, 5, 18, 20, tzinfo=UTC)  # 23:50 in India
    monkeypatch.setattr(api_progress, "utcnow", lambda: late)
    beat(client)
    keys = client.portal.call(client.app.state.redis.keys, "firstpr:activity:*")  # type: ignore[union-attr]
    names = {k.decode() for k in keys}
    assert any(name.endswith(":2026-10-05") for name in names)


def test_progress_has_the_calendar_streak_and_badges(
    client: TestClient, sync_db: OrmSession
) -> None:
    sign_in(client)
    onboard(client)
    uid = sync_db.scalar(select(User.id))
    today = datetime.now(UTC).date()
    for back in (1, 2, 4):  # day 3 missed: the weekly freeze may bridge it
        d = today - timedelta(days=back)
        sync_db.add(
            DailyActivity(
                user_id=uid, day=d.isoformat(), web_minutes=20, codespace_minutes=0, commits=0
            )
        )
    sync_db.commit()
    beat(client)  # one minute today, still in Redis

    body = client.get("/api/v1/me/progress").json()
    calendar = body["calendar"]
    assert date.fromisoformat(calendar[0]["day"]).weekday() == 0  # starts on a Monday
    assert calendar[-1]["day"] == today.isoformat() and len(calendar) > 16 * 7
    assert body["today_minutes"] == 1 and body["goal_minutes"] == 15
    assert body["streak"]["current"] >= 2
    assert len(body["badges"]) == 6 and all(b["earned_at"] is None for b in body["badges"])
    year = client.get("/api/v1/me/progress", params={"weeks": 53}).json()
    assert len(year["calendar"]) > 52 * 7
    assert client.get("/api/v1/me/progress", params={"weeks": 60}).status_code == 422


def test_public_switch(client: TestClient, sync_db: OrmSession) -> None:
    sign_in(client)
    onboard(client)
    assert client.get("/api/v1/me/profile").json()["public"] is False
    resp = client.put("/api/v1/me/profile/visibility", json={"public": True}, headers=csrf(client))
    assert resp.json() == {"public": True}
    assert sync_db.scalar(select(Profile.public)) is True
    assert client.get("/api/v1/me/profile").json()["public"] is True
