"""Email rendering, unsubscribe links, and the master switch."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from firstpr_platform import notify
from firstpr_platform.db import Base, EmailPrefs, Notification, User, session_factory


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'n.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory(engine)() as session:
        session.add(User(id=1, handle="u", email="u@example.com"))
        await session.commit()
        yield session
    await engine.dispose()


def test_unsubscribe_tokens_are_per_user_and_per_key() -> None:
    key = notify.signing_key("key-one,old-key")
    token = notify.unsubscribe_token(key, 7)
    assert notify.check_unsubscribe(key, 7, token)
    assert not notify.check_unsubscribe(key, 8, token)
    assert not notify.check_unsubscribe(notify.signing_key("other"), 7, token)


def test_email_text_is_escaped_and_links_to_the_app() -> None:
    note = Notification(title="Merged: <script>", body="a & b", link="/pulls")
    email = notify.render([note], "https://firstpr.dev/", "https://firstpr.dev/unsub")
    assert "<script>" not in email.html and "&lt;script&gt;" in email.html
    assert "https://firstpr.dev/pulls" in email.text and "unsub" in email.text


async def test_the_master_switch_and_the_same_notification_twice(db: AsyncSession) -> None:
    sent: list[dict[str, object]] = []

    def resend(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "1"})

    mailer = notify.Mailer(
        "re_x",
        "FirstPR <a@b.c>",
        "https://f.dev",
        notify.signing_key("k"),
        transport=httpx.MockTransport(resend),
    )
    first = await notify.add(db, 1, "pr_merged", "Merged", "b", dedupe_key="same")
    assert first is not None
    assert await notify.add(db, 1, "pr_merged", "Merged", "b", dedupe_key="same") is None

    db.add(EmailPrefs(user_id=1, enabled=False, digest=True))
    await db.commit()
    assert await mailer.send_to_user(db, 1, [first]) is False and sent == []
    prefs = await notify.prefs(db, 1)
    prefs.enabled = True
    await db.commit()
    assert await mailer.send_to_user(db, 1, [first]) is True and len(sent) == 1
    assert first.emailed_at is not None

    unset = notify.Mailer("", "x", "https://f.dev", b"k")
    assert unset.configured is False and await unset.send_to_user(db, 1, [first]) is False
