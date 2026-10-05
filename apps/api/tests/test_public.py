"""Public pages: real numbers, the stack picker, Trending, previews, profiles,
the sitemap, the rate limit, and the analytics funnel."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from conftest import add_card, csrf, sign_in
from firstpr_api import public
from firstpr_platform.analytics import Analytics
from firstpr_platform.db import Profile, Reservation, TrackedPull, User, Workspace


def merged_pull(sync_db: OrmSession, uid: int, number: int, days_ago: int) -> None:
    when = datetime.now(UTC) - timedelta(days=days_ago)
    sync_db.add(
        Workspace(
            user_id=uid,
            repo_full_name="pallets/flask",
            number=number,
            issue_title="x",
            mode="local",
            status="pr_open",
            steps=[],
            pr_number=100 + number,
            pr_url="u",
            pr_state="merged",
        )
    )
    sync_db.add(
        TrackedPull(
            user_id=uid,
            repo_full_name="pallets/flask",
            number=100 + number,
            title=f"Fix {number}",
            url="https://github.com/pallets/flask/pull/1",
            state="closed",
            merged=True,
            draft=False,
            status="merged",
            needs_you="",
            reasons=[],
            days_quiet=0,
            timeline=[],
            closed_at=when,
        )
    )
    sync_db.commit()


def test_every_number_comes_from_the_database(client: TestClient, sync_db: OrmSession) -> None:
    for n in range(1, 4):
        add_card(sync_db, "pallets/flask", n)
    add_card(sync_db, "vitejs/vite", 9, availability="claimed")
    sign_in(client)
    uid = sync_db.scalar(select(User.id))
    assert uid is not None
    merged_pull(sync_db, uid, 1, days_ago=2)
    merged_pull(sync_db, uid, 2, days_ago=30)
    client.cookies.clear()
    stats = client.get("/api/v1/public/stats").json()
    assert stats == {
        "free_issues": 3,
        "repos": 2,
        "people": 1,
        "merged_this_week": 1,
        "merged_total": 2,
    }
    merged = client.get("/api/v1/public/trending", params={"tab": "merged"}).json()["merged"]
    assert [m["title"] for m in merged] == ["Fix 1"] and merged[0]["handle"] is None  # private


def test_stack_picker_shows_free_issues_in_that_stack(
    client: TestClient, sync_db: OrmSession
) -> None:
    for n in range(1, 6):
        add_card(sync_db, "pallets/flask", n)
    add_card(sync_db, "vitejs/vite", 7, language="TypeScript", languages=["typescript"])
    sign_in(client)
    held = sync_db.scalar(select(Reservation))
    assert held is None
    uid = sync_db.scalar(select(User.id))
    first_card = 1
    sync_db.add(
        Reservation(
            user_id=uid,
            card_id=first_card,
            status="active",
            day="2026-10-05",
            fit=0.5,
            expires_at=datetime.now(UTC) + timedelta(days=2),
        )
    )
    sync_db.commit()
    python = client.get("/api/v1/public/issues", params={"stack": "python"}).json()["items"]
    assert len(python) == 4 and all(i["language"] == "Python" for i in python)
    assert 1 not in [i["number"] for i in python]  # someone is working on it
    ts = client.get("/api/v1/public/issues", params={"stack": "typescript"}).json()["items"]
    assert [i["number"] for i in ts] == [7]
    assert client.get("/api/v1/public/issues", params={"stack": "cobol"}).status_code == 422


def test_trending_tabs_and_previews(client: TestClient, sync_db: OrmSession) -> None:
    add_card(sync_db, "pallets/flask", 1, tier="beginner")
    add_card(sync_db, "pallets/flask", 2, tier="pro")
    for tab in ("fresh", "beginner", "repos", "merged"):
        assert client.get("/api/v1/public/trending", params={"tab": tab}).status_code == 200
    beginner = client.get("/api/v1/public/trending", params={"tab": "beginner"}).json()
    assert [i["number"] for i in beginner["issues"]] == [1]
    repos = client.get("/api/v1/public/trending", params={"tab": "repos"}).json()["repos"]
    assert repos[0]["repo"] == "pallets/flask" and repos[0]["free_issues"] == 2
    preview = client.get("/api/v1/public/issues/pallets/flask/1").json()
    assert preview["checklist"] and preview["availability_label"] == "Free"
    assert client.get("/api/v1/public/issues/pallets/flask/99").status_code == 404


def test_profiles_are_public_only_when_switched_on(client: TestClient, sync_db: OrmSession) -> None:
    sign_in(client)
    client.put("/api/v1/me/profile", json={}, headers=csrf(client))
    uid = sync_db.scalar(select(User.id))
    assert uid is not None
    merged_pull(sync_db, uid, 1, days_ago=1)
    private = client.get("/api/v1/public/profiles/MuskanScripts")
    missing = client.get("/api/v1/public/profiles/nobody")
    assert private.status_code == missing.status_code == 404
    assert private.json() == missing.json()  # nothing tells the two apart
    client.put("/api/v1/me/profile/visibility", json={"public": True}, headers=csrf(client))
    body = client.get("/api/v1/public/profiles/muskanscripts").json()
    assert body["handle"] == "MuskanScripts" and body["merged"] == 1 and len(body["calendar"]) > 360
    assert "email" not in json.dumps(body)
    paths = [e["path"] for e in client.get("/api/v1/public/sitemap").json()["entries"]]
    assert "/u/MuskanScripts" in paths and "/" in paths
    assert sync_db.scalar(select(Profile.public)) is True


def test_responses_are_cached(client: TestClient, sync_db: OrmSession) -> None:
    add_card(sync_db, "pallets/flask", 1)
    assert client.get("/api/v1/public/stats").json()["free_issues"] == 1
    add_card(sync_db, "pallets/flask", 2)
    assert client.get("/api/v1/public/stats").json()["free_issues"] == 1  # 5-minute cache


def test_rate_limit_per_ip(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setattr(public, "REQUESTS_PER_MINUTE", 3)
    codes = [client.get("/api/v1/public/stats").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_the_funnel_links_the_visitor_to_the_user(client: TestClient) -> None:
    sent: list[dict[str, Any]] = []

    def posthog(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"status": 1})

    client.app.state.analytics = Analytics(  # type: ignore[attr-defined]
        "phc_test", transport=httpx.MockTransport(posthog)
    )
    event = {
        "event": "stack_picker_used",
        "anonymous_id": "anon-12345678",
        "properties": {"stack": "python"},
    }
    assert client.post("/api/v1/public/events", json=event).status_code == 204
    bad = client.post("/api/v1/public/events", json={**event, "event": "signed_in"})
    assert bad.status_code == 422  # only browser events from the browser
    client.cookies.set("firstpr_aid", "anon-12345678")
    sign_in(client)
    names = [(e["event"], e["distinct_id"]) for e in sent]
    assert names[0] == ("stack_picker_used", "anon-12345678")
    assert ("$identify", "user:1") in names and ("signed_in", "user:1") in names
    identify = next(e for e in sent if e["event"] == "$identify")
    assert identify["properties"]["$anon_distinct_id"] == "anon-12345678"
