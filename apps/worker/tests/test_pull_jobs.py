"""Pull request tracking, notifications and email."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from test_jobs import add_user

from firstpr_platform import notify, workspaces
from firstpr_platform.crypto import TokenBox
from firstpr_platform.db import (
    EmailPrefs,
    Notification,
    Profile,
    TrackedPull,
    WebhookEvent,
    Workspace,
    utcnow,
)
from firstpr_worker import jobs
from firstpr_worker.catalogue import Tracked
from issueradar.prs.status import PullFacts, Review, derive, nudge

REPO = "a/one"


def pull(number: int = 5, *, review: str | None = None, merged: bool = False) -> Tracked:
    now = datetime.now(UTC)
    facts = PullFacts(
        repo=REPO,
        number=number,
        title="Fix the docs",
        author="ready",
        state="closed" if merged else "open",
        merged=merged,
        draft=False,
        mergeable=True,
        mergeable_state="clean",
        opened_at=now - timedelta(days=1),
        reviews=[Review("maintainer", review, now)] if review else [],
        url=f"https://github.com/{REPO}/pull/{number}",
    )
    status = derive(facts, now, 7)
    return Tracked(facts, status, nudge(facts, status), [])


class FakeResend:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "email-1"})


def with_mailer(ctx: dict[str, Any]) -> FakeResend:
    resend = FakeResend()
    ctx["mailer"] = notify.Mailer(
        "re_test",
        "FirstPR <hello@firstpr.dev>",
        "https://firstpr.dev",
        notify.signing_key("key"),
        transport=httpx.MockTransport(resend.handler),
    )
    return resend


def ready_user(sync_db: OrmSession, box: TokenBox) -> int:
    user = add_user(sync_db, box, "ready")
    user.email = "ready@example.com"
    sync_db.commit()
    return user.id


async def test_a_change_of_status_notifies_and_merges_are_emailed(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    resend = with_mailer(ctx)
    user_id = ready_user(sync_db, box)
    sync_db.add(
        Workspace(
            user_id=user_id,
            repo_full_name=REPO,
            number=1,
            issue_title="x",
            mode="local",
            status=workspaces.PR_OPEN,
            steps=[],
            pr_number=5,
            pr_url="u",
            pr_state="open",
        )
    )
    sync_db.commit()
    fake = ctx["catalogue"]

    fake.pulls = [pull()]
    await jobs.track_user(ctx, user_id)
    assert fake.track_calls[-1] == ("ready", [(REPO, 5)], True)  # the workspace's PR, and a search
    assert sync_db.scalars(select(Notification)).all() == []  # first sight is not news

    fake.pulls = [pull(review="CHANGES_REQUESTED")]
    await jobs.track_user(ctx, user_id)
    sync_db.expire_all()
    note = sync_db.scalar(select(Notification))
    assert note is not None and note.kind == "changes_requested" and note.emailed_at is not None
    assert resend.sent[-1]["to"] == ["ready@example.com"]
    assert resend.sent[-1]["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "/api/v1/email/unsubscribe?u=" in resend.sent[-1]["text"]

    fake.pulls = [pull(merged=True)]
    await jobs.track_pull(ctx, user_id, REPO, 5)
    sync_db.expire_all()
    kinds = [n.kind for n in sync_db.scalars(select(Notification).order_by(Notification.id))]
    assert [k for k in kinds if k != "badge"] == ["changes_requested", "pr_merged"]
    assert len(resend.sent) == 2  # badges are in the app only
    row = sync_db.scalar(select(TrackedPull))
    assert row is not None and row.status == "merged"
    ws = sync_db.scalar(select(Workspace))
    assert ws is not None and ws.pr_state == "merged"


async def test_the_same_change_twice_is_one_notification(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    user_id = ready_user(sync_db, box)
    fake = ctx["catalogue"]
    fake.pulls = [pull()]
    await jobs.track_user(ctx, user_id)
    fake.pulls = [pull(review="APPROVED")]
    await jobs.track_user(ctx, user_id)
    # A second webhook for the same review, before the first run saved anything.
    row = sync_db.scalar(select(TrackedPull))
    assert row is not None
    row.status = "waiting_for_review"
    sync_db.commit()
    await jobs.track_user(ctx, user_id)
    assert len(sync_db.scalars(select(Notification)).all()) == 1


async def test_turning_email_off_stops_every_email(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    resend = with_mailer(ctx)
    user_id = ready_user(sync_db, box)
    sync_db.add(EmailPrefs(user_id=user_id, enabled=False, digest=True))
    sync_db.add(Profile(user_id=user_id, level="beginner", packs=[], timezone="UTC"))
    sync_db.commit()
    fake = ctx["catalogue"]
    fake.pulls = [pull()]
    await jobs.track_user(ctx, user_id)
    fake.pulls = [pull(review="CHANGES_REQUESTED")]
    await jobs.track_user(ctx, user_id)
    fake.pulls = [pull(merged=True)]
    await jobs.track_user(ctx, user_id)
    for hour in range(24):  # whatever the time, no digest either
        jobs.utcnow = lambda h=hour: datetime(2026, 10, 6, h, 30, tzinfo=UTC)  # type: ignore[assignment]
        await jobs.send_digests(ctx)
    jobs.utcnow = utcnow  # type: ignore[assignment]
    kinds = [n.kind for n in sync_db.scalars(select(Notification))]
    assert [k for k in kinds if k != "badge"] == ["changes_requested", "pr_merged"]
    assert resend.sent == []


async def test_the_digest_comes_at_eight_once_and_only_with_news(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    resend = with_mailer(ctx)
    user_id = ready_user(sync_db, box)
    sync_db.add(Profile(user_id=user_id, level="beginner", packs=[], timezone="Asia/Kolkata"))
    sync_db.commit()
    eight_in_india = datetime(2026, 10, 6, 2, 40, tzinfo=UTC)
    try:
        jobs.utcnow = lambda: eight_in_india  # type: ignore[assignment]
        assert await jobs.send_digests(ctx) == 0  # nothing new: no email
        for kind in ("approved", "ci_failing"):
            sync_db.add(
                Notification(
                    user_id=user_id,
                    kind=kind,
                    title=f"{kind} on Fix",
                    body="b",
                    dedupe_key=kind,
                    created_at=eight_in_india - timedelta(hours=3),
                )
            )
        sync_db.commit()
        jobs.utcnow = lambda: eight_in_india - timedelta(hours=1)  # type: ignore[assignment]
        assert await jobs.send_digests(ctx) == 0  # 7 o'clock there
        jobs.utcnow = lambda: eight_in_india  # type: ignore[assignment]
        assert await jobs.send_digests(ctx) == 1
        assert resend.sent[0]["subject"] == "FirstPR: 2 updates on your pull requests"
        assert await jobs.send_digests(ctx) == 0  # once a day
    finally:
        jobs.utcnow = utcnow  # type: ignore[assignment]


async def test_a_review_webhook_checks_that_pull_request_soon(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    user_id = ready_user(sync_db, box)
    ctx["catalogue"].pulls = [pull()]
    await jobs.track_user(ctx, user_id)
    payloads = {
        "review": ("pull_request_review", {"pull_request": {"number": 5}}),
        "comment": ("issue_comment", {"issue": {"number": 5, "pull_request": {}}}),
        "checks": ("check_suite", {"check_suite": {"pull_requests": [{"number": 5}]}}),
        "other": ("pull_request", {"pull_request": {"number": 99}}),
    }
    for delivery, (event, payload) in payloads.items():
        sync_db.add(
            WebhookEvent(
                delivery_id=delivery,
                event=event,
                action="submitted",
                repo_full_name=REPO,
                payload=json.dumps(payload),
            )
        )
    sync_db.commit()
    queue = ctx["redis"].queued
    for delivery in ("review", "comment", "checks"):
        before = len(queue)
        assert await jobs.handle_webhook(ctx, delivery) == "1 pull request(s) to check"
        function, args, kwargs = queue[before]
        assert function == "track_pull" and args == (user_id, REPO, 5)
        assert kwargs["_defer_by"] <= 60
    assert await jobs.handle_webhook(ctx, "other") == "repo not tracked"


async def test_a_workspace_that_stops_is_a_notification(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox, user_github: Any
) -> None:
    resend = with_mailer(ctx)
    user_id = ready_user(sync_db, box)
    user_github.installed = False
    ws = Workspace(
        user_id=user_id,
        repo_full_name=REPO,
        number=7,
        issue_title="Fix",
        mode="local",
        status=workspaces.QUEUED,
        steps=workspaces.new_steps("local"),
    )
    sync_db.add(ws)
    sync_db.commit()
    await jobs.start_workspace(ctx, ws.id)
    note = sync_db.scalar(select(Notification))
    assert (
        note is not None
        and note.kind == "workspace_problem"
        and note.link == f"/workspaces/{ws.id}"
    )
    assert len(resend.sent) == 1
