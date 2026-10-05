"""Admin overview, the shared catalogue, and GitHub webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session as OrmSession

from conftest import FakeJobs, csrf, sign_in
from firstpr_platform.db import CatalogueRepo, RepoSync, User, WebhookEvent, utcnow

SECRET = "webhook-test-secret"


def make_admin(sync_db: OrmSession) -> None:
    sync_db.execute(update(User).values(role="admin"))
    sync_db.commit()


def test_admin_pages_are_for_admins_only(client: TestClient, sync_db: OrmSession) -> None:
    assert client.get("/api/v1/admin/sync").status_code == 401
    sign_in(client)
    assert client.get("/api/v1/admin/sync").status_code == 403
    make_admin(sync_db)
    assert client.get("/api/v1/admin/sync").status_code == 200


def test_overview_shows_repos_problems_first_and_budgets(
    client: TestClient, sync_db: OrmSession
) -> None:
    sign_in(client)
    make_admin(sync_db)
    sync_db.add_all(
        [
            CatalogueRepo(full_name="pallets/flask", source="pack"),
            CatalogueRepo(full_name="vitejs/vite", source="pack"),
            RepoSync(
                full_name="vitejs/vite",
                token_kind="app",
                status="failed",
                note="HTTP 502",
                open_issues=0,
                synced_at=utcnow(),
            ),
        ]
    )
    sync_db.commit()
    budget = {"remaining": 4100, "limit": 5000, "paused": False}
    client.portal.call(  # type: ignore[union-attr]
        client.app.state.redis.set,
        "firstpr:budget:app",
        json.dumps(budget),  # type: ignore[attr-defined]
    )
    body = client.get("/api/v1/admin/sync").json()
    assert [r["full_name"] for r in body["repos"]] == ["vitejs/vite", "pallets/flask"]
    assert body["repos"][0]["status"] == "failed" and body["repos"][0]["token"] == "app"
    assert body["budgets"] == {"app": budget}


def test_catalogue_add_and_remove(client: TestClient, sync_db: OrmSession, jobs: FakeJobs) -> None:
    sign_in(client)
    make_admin(sync_db)
    resp = client.post(
        "/api/v1/admin/catalogue", json={"repo": "pallets/flask"}, headers=csrf(client)
    )
    assert resp.status_code == 201
    assert sync_db.scalar(select(CatalogueRepo.full_name)) == "pallets/flask"
    assert jobs.queued[-1][0] == "sync_catalogue"
    gone = client.delete("/api/v1/admin/catalogue/pallets/flask", headers=csrf(client))
    assert gone.status_code == 204
    sync_db.expire_all()
    assert sync_db.scalar(select(CatalogueRepo.full_name)) is None


def deliver(
    client: TestClient,
    payload: dict[str, object],
    *,
    delivery: str = "d-1",
    event: str = "issues",
    secret: str = SECRET,
) -> int:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    resp = client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery,
            "Content-Type": "application/json",
        },
    )
    return resp.status_code


def test_webhook_is_checked_stored_once_and_queued(
    client: TestClient, sync_db: OrmSession, jobs: FakeJobs
) -> None:
    payload = {
        "action": "closed",
        "repository": {"full_name": "pallets/flask"},
        "sender": {"id": 4242},
    }
    assert deliver(client, payload, secret="wrong") == 401
    assert deliver(client, {"zen": "hi"}, event="ping", delivery="p-1") == 200
    assert deliver(client, payload) == 202
    assert deliver(client, payload) == 202  # GitHub retried the same delivery
    rows = sync_db.scalars(select(WebhookEvent)).all()
    assert len(rows) == 1
    assert (rows[0].event, rows[0].action, rows[0].repo_full_name) == (
        "issues",
        "closed",
        "pallets/flask",
    )
    assert [q[0] for q in jobs.queued] == ["handle_webhook"]
    assert jobs.queued[0][1] == ("d-1",)
