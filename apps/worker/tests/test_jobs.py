"""Which token syncs what, sync records, active users and webhooks."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from conftest import make_card
from firstpr_platform.crypto import TokenBox
from firstpr_platform.db import (
    CatalogueRepo,
    GitHubAccount,
    IssueCard,
    Profile,
    RepoSync,
    Reservation,
    Session,
    User,
    Watch,
    WebhookEvent,
    utcnow,
)
from firstpr_worker import jobs
from firstpr_worker.catalogue import APP_OWNER, engine_user_id, pack_repos


def add_user(sync_db: OrmSession, box: TokenBox, login: str, *, seen_days_ago: int = 1) -> User:
    user = User(handle=login)
    sync_db.add(user)
    sync_db.flush()
    sync_db.add(
        GitHubAccount(
            user_id=user.id,
            github_id=1000 + user.id,
            login=login,
            access_token=box.seal(f"ghu_{login}"),
            access_expires_at=utcnow() + timedelta(hours=8),
        )
    )
    sync_db.add(
        Session(
            id_hash=f"h-{login}",
            user_id=user.id,
            last_seen_at=utcnow() - timedelta(days=seen_days_ago),
            expires_at=utcnow() + timedelta(days=20),
        )
    )
    sync_db.commit()
    return user


def watch(sync_db: OrmSession, user: User, *repos: str) -> None:
    sync_db.add_all(Watch(user_id=user.id, repo_full_name=r) for r in repos)
    sync_db.commit()


async def test_seed_fills_an_empty_catalogue_once(ctx: dict[str, Any], sync_db: OrmSession) -> None:
    assert await jobs.seed_catalogue(ctx) == len(pack_repos()) > 10
    assert await jobs.seed_catalogue(ctx) == 0
    assert {r.source for r in sync_db.scalars(select(CatalogueRepo))} == {"pack"}


async def test_catalogue_sync_uses_the_app_token_for_shared_repos(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    alice, bob = add_user(sync_db, box, "alice"), add_user(sync_db, box, "bob")
    sync_db.add(CatalogueRepo(full_name="pallets/flask", source="pack"))
    sync_db.commit()
    watch(sync_db, alice, "vitejs/vite", "alice/own")
    watch(sync_db, bob, "vitejs/vite")

    assert await jobs.sync_catalogue(ctx) == "completed: 2 of 2 repos"
    owner, repos, token, identity = ctx["catalogue"].calls[0]
    assert (owner, token, identity) == (APP_OWNER, "ghs_app_token", "app")
    assert repos == {"pallets/flask", "vitejs/vite"}  # alice/own has one watcher: not here

    rows = {r.full_name: r for r in sync_db.scalars(select(RepoSync))}
    assert set(rows) == {"pallets/flask", "vitejs/vite"}
    assert rows["vitejs/vite"].token_kind == "app" and rows["vitejs/vite"].open_issues == 3
    budget = json.loads(await ctx["redis"].get("firstpr:budget:app"))
    assert budget["remaining"] == 4800 and budget["paused"] is False


async def test_an_interrupted_sync_marks_the_rest_paused(
    ctx: dict[str, Any], sync_db: OrmSession
) -> None:
    sync_db.add_all(
        CatalogueRepo(full_name=n, source="pack") for n in ("a/one", "b/two", "c/three")
    )
    sync_db.commit()
    ctx["catalogue"].interrupt_after = 1
    assert (await jobs.sync_catalogue(ctx)).startswith("interrupted")
    status = {r.full_name: r.status for r in sync_db.scalars(select(RepoSync))}
    assert status == {"a/one": "synced", "b/two": "paused", "c/three": "paused"}
    assert json.loads(await ctx["redis"].get("firstpr:budget:app"))["paused"] is True


async def test_catalogue_sync_waits_for_the_app(ctx: dict[str, Any]) -> None:
    ctx["app_tokens"] = None
    assert (await jobs.sync_catalogue(ctx)).startswith("skipped")


async def test_personal_sync_uses_only_that_users_token_and_repos(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    alice, bob = add_user(sync_db, box, "alice"), add_user(sync_db, box, "bob")
    watch(sync_db, alice, "alice/own", "shared/repo")
    watch(sync_db, bob, "shared/repo", "bob/own")

    assert await jobs.sync_user(ctx, alice.id) == "completed: 1 of 1 repos"
    owner, repos, token, identity = ctx["catalogue"].calls[-1]
    assert owner == engine_user_id(alice.id)
    assert repos == {"alice/own"}
    assert token == "ghu_alice" and identity == f"user:{alice.id}"
    assert sync_db.scalar(select(RepoSync.token_kind)) == "user"
    assert await ctx["redis"].get(f"firstpr:budget:user:{alice.id}") is not None


async def test_personal_sync_skips_reconnect_and_empty_lists(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    alice = add_user(sync_db, box, "alice")
    assert await jobs.sync_user(ctx, alice.id) == "nothing of their own to sync"
    assert ctx["catalogue"].cleared == [engine_user_id(alice.id)]

    watch(sync_db, alice, "alice/own")
    account = sync_db.scalar(select(GitHubAccount))
    assert account is not None
    account.status = "reconnect_needed"
    sync_db.commit()
    assert (await jobs.sync_user(ctx, alice.id)).startswith("skipped")
    assert ctx["catalogue"].calls == []


async def test_only_recent_users_with_watches_are_queued(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    recent = add_user(sync_db, box, "recent", seen_days_ago=2)
    old = add_user(sync_db, box, "old", seen_days_ago=40)
    add_user(sync_db, box, "nothing-watched", seen_days_ago=1)
    watch(sync_db, recent, "r/one")
    watch(sync_db, old, "o/one")
    assert await jobs.sync_active_users(ctx) == 1
    assert ctx["redis"].queued == [
        ("sync_user", (recent.id,), {"_job_id": f"sync-user:{recent.id}"})
    ]


def deliver(sync_db: OrmSession, delivery: str, event: str, **fields: Any) -> None:
    sync_db.add(WebhookEvent(delivery_id=delivery, event=event, payload="{}", **fields))
    sync_db.commit()


async def test_webhooks(ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox) -> None:
    alice = add_user(sync_db, box, "alice")
    sync_db.add(CatalogueRepo(full_name="pallets/flask", source="pack"))
    sync_db.commit()
    watch(sync_db, alice, "alice/own")

    deliver(sync_db, "1", "issues", action="opened", repo_full_name="Pallets/Flask")
    deliver(sync_db, "2", "pull_request", action="closed", repo_full_name="alice/own")
    deliver(sync_db, "3", "issues", action="opened", repo_full_name="someone/else")
    deliver(sync_db, "4", "star", action="created", repo_full_name="pallets/flask")
    deliver(
        sync_db, "5", "github_app_authorization", action="revoked", sender_github_id=1000 + alice.id
    )

    assert await jobs.handle_webhook(ctx, "1") == "catalogue sync queued"
    assert await jobs.handle_webhook(ctx, "2") == "personal sync queued"
    assert await jobs.handle_webhook(ctx, "3") == "repo not tracked"
    assert await jobs.handle_webhook(ctx, "4") == "ignored"
    assert await jobs.handle_webhook(ctx, "5") == "account marked reconnect needed"
    assert await jobs.handle_webhook(ctx, "1") == "already handled"

    queued = [(name, kwargs.get("_job_id")) for name, _, kwargs in ctx["redis"].queued]
    assert queued == [("sync_catalogue", "sync-catalogue"), ("sync_user", f"sync-user:{alice.id}")]
    sync_db.expire_all()
    assert sync_db.scalar(select(GitHubAccount.status)) == "reconnect_needed"
    assert all(e.processed_at for e in sync_db.scalars(select(WebhookEvent)))


async def test_each_sync_rebuilds_the_issue_cards(ctx: dict[str, Any], sync_db: OrmSession) -> None:
    sync_db.add(CatalogueRepo(full_name="a/one", source="pack"))
    sync_db.commit()
    fake = ctx["catalogue"]
    fake.issues["a/one"] = [make_card("a/one", 1), make_card("a/one", 2)]
    await jobs.sync_catalogue(ctx)
    cards = {c.number: c for c in sync_db.scalars(select(IssueCard))}
    assert set(cards) == {1, 2}
    first_change = cards[1].changed_at

    # Issue 2 was closed, issue 1 got claimed, issue 3 is new.
    fake.issues["a/one"] = [make_card("a/one", 1, availability="claimed"), make_card("a/one", 3)]
    await jobs.sync_catalogue(ctx)
    sync_db.expire_all()
    cards = {c.number: c for c in sync_db.scalars(select(IssueCard))}
    assert set(cards) == {1, 3}
    assert cards[1].availability == "claimed" and cards[1].changed_at > first_change


async def test_cards_are_built_once_when_there_are_none(ctx: dict[str, Any]) -> None:
    assert await jobs.cards_if_empty(ctx) is True
    assert ctx["redis"].queued[-1][0] == "refresh_cards"


async def test_daily_picks_for_active_people_who_finished_onboarding(
    ctx: dict[str, Any], sync_db: OrmSession, box: TokenBox
) -> None:
    sync_db.add(CatalogueRepo(full_name="a/one", source="pack"))
    sync_db.commit()
    ctx["catalogue"].issues["a/one"] = [make_card("a/one", n) for n in (1, 2, 3)]
    await jobs.sync_catalogue(ctx)
    ready = add_user(sync_db, box, "ready")
    add_user(sync_db, box, "new")  # has not finished onboarding
    away = add_user(sync_db, box, "away", seen_days_ago=30)
    for user in (ready, away):
        sync_db.add(
            Profile(
                user_id=user.id, level="beginner", packs=[], timezone="UTC", onboarded_at=utcnow()
            )
        )
    sync_db.commit()

    assert await jobs.make_daily_picks(ctx) == 1
    assert await jobs.make_daily_picks(ctx) == 1  # the same pick, not a second one
    holds = sync_db.scalars(select(Reservation)).all()
    assert [h.user_id for h in holds] == [ready.id]
