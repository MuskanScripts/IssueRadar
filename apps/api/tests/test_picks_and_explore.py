"""Onboarding, today's pick, Show me another, Explore, the issue page and Refresh."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from conftest import FakeGitHub, FakeJobs, add_card, csrf, sign_in
from firstpr_platform.db import FeatureInterest, RecommendationEvent, Reservation

PYTHON_STRONG = {
    "level": "beginner",
    "skills": [{"kind": "languages", "name": "python", "level": "strong"}],
    "packs": [],
    "timezone": "Europe/Berlin",
}


def onboard(client: TestClient, profile: dict[str, object] | None = None) -> None:
    resp = client.put("/api/v1/me/profile", json=profile or PYTHON_STRONG, headers=csrf(client))
    assert resp.status_code == 200, resp.text


def as_someone_else(client: TestClient, github: FakeGitHub) -> httpx.Cookies:
    """Sign a second person in on the same test client. Returns the first one's cookies."""
    first = httpx.Cookies(client.cookies)
    client.cookies.clear()
    github.user = {"id": 777, "login": "friend", "name": "Friend", "email": None}
    sign_in(client)
    onboard(client)
    return first


def switch_to(client: TestClient, cookies: httpx.Cookies) -> None:
    client.cookies.clear()
    client.cookies.update(cookies)


def test_options_list_levels_skills_and_packs(client: TestClient) -> None:
    body = client.get("/api/v1/onboarding/options").json()
    assert set(body["levels"]) == {"beginner", "intermediate", "pro"}
    assert "python" in body["skills"]["languages"] and "react" in body["skills"]["frameworks"]
    assert any(p["key"] == "python-tooling" for p in body["packs"])


def test_onboarding_saves_the_profile(client: TestClient) -> None:
    sign_in(client)
    assert client.get("/api/v1/me").json()["onboarded"] is False
    assert client.put("/api/v1/me/profile", json=PYTHON_STRONG).status_code == 403
    onboard(client, {**PYTHON_STRONG, "packs": ["python-tooling"]})
    assert client.get("/api/v1/me").json()["onboarded"] is True
    profile = client.get("/api/v1/me/profile").json()
    assert profile["skills"] == [{"kind": "languages", "name": "python", "level": "strong"}]
    assert profile["packs"] == ["python-tooling"] and profile["timezone"] == "Europe/Berlin"

    for bad in (
        {**PYTHON_STRONG, "skills": [{"kind": "languages", "name": "klingon", "level": "strong"}]},
        {**PYTHON_STRONG, "packs": ["no-such-pack"]},
        {**PYTHON_STRONG, "timezone": "Mars/Base"},
        {**PYTHON_STRONG, "level": "wizard"},
    ):
        assert client.put("/api/v1/me/profile", json=bad, headers=csrf(client)).status_code == 422


def test_skipping_onboarding_still_finishes_it(client: TestClient) -> None:
    sign_in(client)
    onboard(client, {})
    assert client.get("/api/v1/me").json()["onboarded"] is True
    assert client.get("/api/v1/me/profile").json()["level"] == "beginner"


def test_todays_pick_is_the_best_fit_and_stays_the_same(
    client: TestClient, sync_db: OrmSession
) -> None:
    add_card(sync_db, "pallets/flask", 1, tier="pro")
    add_card(sync_db, "vitejs/vite", 2, language="TypeScript", languages=["typescript"])
    add_card(sync_db, "pallets/flask", 3)
    add_card(sync_db, "pallets/flask", 4, availability="claimed")
    sign_in(client)
    onboard(client)

    today = client.get("/api/v1/me/today").json()
    pick = today["pick"]
    assert (pick["repo"], pick["number"]) == ("pallets/flask", 3)
    assert pick["held_by_you"] and pick["fit"] > 50
    assert any("python (strong)" in line for line in pick["why"])
    held_until = datetime.fromisoformat(today["held_until"])
    assert timedelta(hours=47) < held_until - datetime.now(UTC) <= timedelta(hours=48)
    assert today["swaps_left"] == 3

    again = client.get("/api/v1/me/today").json()
    assert again["pick"]["number"] == 3
    assert len(sync_db.scalars(select(Reservation)).all()) == 1


def test_two_people_never_get_the_same_pick(
    client: TestClient, github: FakeGitHub, sync_db: OrmSession
) -> None:
    for number in range(1, 4):
        add_card(sync_db, "pallets/flask", number)
    sign_in(client)
    onboard(client)
    mine = client.get("/api/v1/me/today").json()["pick"]["number"]
    me = as_someone_else(client, github)
    theirs = client.get("/api/v1/me/today").json()["pick"]["number"]
    assert mine != theirs
    switch_to(client, me)
    # Explore hides an issue someone else holds, and shows yours as yours.
    listed = {i["number"]: i for i in client.get("/api/v1/issues").json()["items"]}
    assert theirs not in listed and listed[mine]["held_by_you"]
    page = client.get(f"/api/v1/issues/pallets/flask/{theirs}").json()
    assert page["why"] == ["Someone else is trying this issue for the next two days."]


def test_show_me_another_three_times_a_day(client: TestClient, sync_db: OrmSession) -> None:
    for number in range(1, 7):
        add_card(sync_db, "pallets/flask", number, comments=number)
    sign_in(client)
    onboard(client)
    seen = [client.get("/api/v1/me/today").json()["pick"]["number"]]
    for left in (2, 1, 0):
        resp = client.post("/api/v1/me/today/another", headers=csrf(client))
        assert resp.status_code == 200
        body = resp.json()
        assert body["swaps_left"] == left
        seen.append(body["pick"]["number"])
    assert len(set(seen)) == 4  # a swapped issue never comes back
    assert client.post("/api/v1/me/today/another", headers=csrf(client)).status_code == 429
    assert client.post("/api/v1/me/today/another").status_code == 403
    actions = [e.action for e in sync_db.scalars(select(RecommendationEvent))]
    assert actions.count("shown") == 4 and actions.count("swapped") == 3


def test_no_pick_before_the_first_sync(client: TestClient) -> None:
    sign_in(client)
    onboard(client)
    body = client.get("/api/v1/me/today").json()
    assert body["pick"] is None and "first sync" in body["empty_reason"]


def test_picks_come_from_the_chosen_packs(client: TestClient, sync_db: OrmSession) -> None:
    add_card(sync_db, "pallets/flask", 1, health=95)  # not in any pack
    add_card(sync_db, "pytest-dev/pytest", 2, health=40)
    sign_in(client)
    onboard(client, {**PYTHON_STRONG, "packs": ["python-tooling"]})
    assert client.get("/api/v1/me/today").json()["pick"]["repo"] == "pytest-dev/pytest"


def test_explore_filters_and_pages_without_repeats(client: TestClient, sync_db: OrmSession) -> None:
    now = datetime.now(UTC)
    for number in range(1, 26):
        add_card(
            sync_db,
            "pallets/flask" if number % 2 else "vitejs/vite",
            number,
            tier="beginner" if number <= 20 else "intermediate",
            language="Python" if number % 2 else "TypeScript",
            languages=["python"] if number % 2 else ["typescript"],
            frameworks=["react"] if number % 2 == 0 else [],
            updated_at=now - timedelta(days=number),
        )
    sign_in(client)
    onboard(client)

    seen: list[int] = []
    cursor = None
    while True:
        params = {"limit": 7, **({"cursor": cursor} if cursor else {})}
        body = client.get("/api/v1/issues", params=params).json()
        assert body["total"] == 25
        seen += [i["number"] for i in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == list(range(1, 26))
    fits = [i["fit"] for i in client.get("/api/v1/issues", params={"limit": 50}).json()["items"]]
    assert fits == sorted(fits, reverse=True)

    def numbers(**params: object) -> list[int]:
        resp = client.get("/api/v1/issues", params={"limit": 50, **params})
        return [i["number"] for i in resp.json()["items"]]

    assert set(numbers(level="intermediate")) == {21, 22, 23, 24, 25}
    assert all(n % 2 == 0 for n in numbers(skill="react"))
    assert all(n % 2 == 1 for n in numbers(language="python"))
    assert set(numbers(fresh=3)) == {1, 2}
    assert numbers(sort="newest")[:3] == [1, 2, 3]
    shuffled = numbers(sort="shuffle", seed="abc")
    assert shuffled == numbers(sort="shuffle", seed="abc")
    assert shuffled != numbers(sort="shuffle", seed="xyz")
    assert client.get("/api/v1/issues", params={"cursor": "nonsense"}).status_code == 422


def test_refresh_once_every_five_minutes(
    client: TestClient, sync_db: OrmSession, jobs: FakeJobs
) -> None:
    add_card(sync_db, "pallets/flask", 1)
    sign_in(client)
    onboard(client)
    assert client.post("/api/v1/me/refresh").status_code == 403
    first = client.post("/api/v1/me/refresh", headers=csrf(client))
    assert first.status_code == 200 and first.json()["next_allowed_at"]
    assert [j[0] for j in jobs.queued] == ["sync_catalogue"]
    again = client.post("/api/v1/me/refresh", headers=csrf(client))
    assert again.status_code == 429 and "min" in again.json()["detail"]
    assert client.get("/api/v1/me/refresh").json()["requested_at"]


def test_changes_since_a_refresh(client: TestClient, sync_db: OrmSession) -> None:
    before = datetime.now(UTC) - timedelta(minutes=5)
    add_card(sync_db, "pallets/flask", 1, changed_at=before - timedelta(hours=1))
    add_card(sync_db, "pallets/flask", 2)
    add_card(sync_db, "pallets/flask", 3, availability="claimed")
    sign_in(client)
    onboard(client)
    body = client.get("/api/v1/issues/changes", params={"since": before.isoformat()}).json()
    assert (body["new_activity"], body["now_taken"]) == (1, 1)


def test_issue_page_explains_and_checks_github_when_stale(
    client: TestClient, sync_db: OrmSession, github: FakeGitHub
) -> None:
    add_card(sync_db, "pallets/flask", 1)
    add_card(sync_db, "pallets/flask", 2, refreshed_at=datetime.now(UTC) - timedelta(hours=1))
    github.issues["pallets/flask#2"] = {
        "state": "open",
        "assignees": [{"login": "someone"}],
        "comments": 0,
    }
    sign_in(client)
    onboard(client)

    fresh = client.get("/api/v1/issues/pallets/flask/1").json()
    assert fresh["checklist"] and fresh["availability_reasons"] and fresh["live"] is None
    stale = client.get("/api/v1/issues/Pallets/Flask/2").json()
    assert stale["live"]["note"] == "Assigned to @someone since our last sync."
    # GitHub is newer than our copy, so the page does not offer it as free.
    assert stale["availability"] == "claimed" and stale["fit"] is None
    calls = len(github.requests)
    client.get("/api/v1/issues/pallets/flask/2")
    assert len(github.requests) == calls  # cached for a while
    assert client.get("/api/v1/issues/pallets/flask/99").status_code == 404


def test_events_and_interest_are_recorded(client: TestClient, sync_db: OrmSession) -> None:
    add_card(sync_db, "pallets/flask", 1)
    sign_in(client)
    onboard(client)
    event = {"repo": "pallets/flask", "number": 1, "surface": "explore", "action": "github"}
    assert client.post("/api/v1/me/events", json=event, headers=csrf(client)).status_code == 204
    logged = sync_db.scalar(select(RecommendationEvent))
    assert logged is not None and logged.action == "github" and logged.fit is not None

    for _ in range(2):
        resp = client.post(
            "/api/v1/me/interest", json={"feature": "ai-mentor"}, headers=csrf(client)
        )
        assert resp.json() == ["ai-mentor"]
    assert len(sync_db.scalars(select(FeatureInterest)).all()) == 1
    bad = client.post("/api/v1/me/interest", json={"feature": "time-travel"}, headers=csrf(client))
    assert bad.status_code == 422
