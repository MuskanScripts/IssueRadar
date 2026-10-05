"""Watching repos, and which token will sync them."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from conftest import FakeJobs, csrf, sign_in
from firstpr_platform.db import CatalogueRepo, User, Watch


def watch(client: TestClient, repo: str) -> tuple[int, object]:
    resp = client.post("/api/v1/me/watches", json={"repo": repo}, headers=csrf(client))
    return resp.status_code, resp.json()


def test_watching_a_repo_only_you_watch(
    client: TestClient, sync_db: OrmSession, jobs: FakeJobs
) -> None:
    sign_in(client)
    status, body = watch(client, "https://github.com/pallets/flask")
    assert status == 201
    assert body == [
        {
            "full_name": "pallets/flask",
            "added_at": body[0]["added_at"],
            "synced_with": "you",
            "last_sync": None,
        }  # type: ignore[index]
    ]
    assert jobs.queued[-1][0] == "sync_user"
    # Watching it again changes nothing.
    assert watch(client, "pallets/flask")[0] == 201
    assert len(sync_db.scalars(select(Watch)).all()) == 1


def test_a_second_watcher_or_the_catalogue_moves_it_to_the_app_token(
    client: TestClient, sync_db: OrmSession
) -> None:
    sign_in(client)
    watch(client, "pallets/flask")
    watch(client, "vitejs/vite")
    other = User(handle="someone", role="user")
    sync_db.add(other)
    sync_db.flush()
    sync_db.add(Watch(user_id=other.id, repo_full_name="pallets/flask"))
    sync_db.add(CatalogueRepo(full_name="vitejs/vite", source="pack"))
    sync_db.commit()
    body = client.get("/api/v1/me/watches").json()
    assert {w["full_name"]: w["synced_with"] for w in body} == {
        "pallets/flask": "app",
        "vitejs/vite": "app",
    }


def test_refused_repos(client: TestClient) -> None:
    sign_in(client)
    assert watch(client, "not a repo")[0] == 422
    assert watch(client, "nobody/nothing")[0] == 404
    status, body = watch(client, "MuskanScripts/notes")
    assert status == 422 and "Private repos" in body["detail"]  # type: ignore[index]


def test_csrf_and_removal(client: TestClient) -> None:
    sign_in(client)
    for name in ("pallets/flask", "vitejs/vite"):
        assert watch(client, name)[0] == 201
    no_csrf = client.post("/api/v1/me/watches", json={"repo": "pallets/flask"})
    assert no_csrf.status_code == 403

    left = client.delete("/api/v1/me/watches/pallets/flask", headers=csrf(client))
    assert left.status_code == 200 and [w["full_name"] for w in left.json()] == ["vitejs/vite"]


def test_watch_limit(client: TestClient, sync_db: OrmSession) -> None:
    sign_in(client)
    user = sync_db.scalar(select(User))
    assert user is not None
    for i in range(3):
        sync_db.add(Watch(user_id=user.id, repo_full_name=f"owner/repo{i}"))
    sync_db.commit()
    status, body = watch(client, "pallets/flask")
    assert status == 409 and "up to 3" in body["detail"]  # type: ignore[index]
