"""Notifications in the app, and the emails that go with some of them.

Every email goes through `Mailer.send_to_user`, which checks the user's master
switch first. Turning email off in Settings (or clicking Unsubscribe in any
email) therefore stops every email: the ones sent straight away and the daily
digest alike.
"""

from __future__ import annotations

import hashlib
import hmac
import html
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_platform.db import EmailPrefs, Notification, User, utcnow

RESEND_URL = "https://api.resend.com/emails"
# Sent by email straight away; the rest wait for the daily digest.
IMMEDIATE = frozenset({"pr_merged", "changes_requested", "workspace_problem"})

# What a pull request's new status means for the user, keyed by the engine's status.
PR_KINDS: dict[str, tuple[str, str]] = {
    "merged": ("pr_merged", "Merged: {title}"),
    "changes_requested": ("changes_requested", "Changes requested on {title}"),
    "ci_failing": ("ci_failing", "Checks are failing on {title}"),
    "merge_conflict": ("merge_conflict", "Merge conflict on {title}"),
    "approved": ("approved", "Approved: {title}"),
    "stale": ("stale", "Gone quiet: {title}"),
    "closed_unmerged": ("closed_unmerged", "Closed without merging: {title}"),
}


async def prefs(db: AsyncSession, user_id: int) -> EmailPrefs:
    row = await db.get(EmailPrefs, user_id)
    if row is None:
        row = EmailPrefs(user_id=user_id, enabled=True, digest=True)
        db.add(row)
        await db.flush()
    return row


async def add(
    db: AsyncSession,
    user_id: int,
    kind: str,
    title: str,
    body: str,
    *,
    dedupe_key: str,
    link: str | None = None,
    external_url: str | None = None,
) -> Notification | None:
    """Store a notification. None when the same one was stored before.

    Uses INSERT ... ON CONFLICT DO NOTHING rather than catching the error, so a
    duplicate never rolls back the session (which would expire the caller's rows).
    """
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = (
        insert(Notification)
        .values(
            user_id=user_id,
            kind=kind,
            title=title[:300],
            body=body,
            link=link,
            external_url=external_url,
            dedupe_key=dedupe_key[:300],
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
        .returning(Notification.id)
    )
    new_id = await db.scalar(statement)
    await db.commit()
    if new_id is None:
        return None
    return await db.get(Notification, new_id)


# ------------------------------------------------------------ unsubscribe


def signing_key(token_keys: str) -> bytes:
    """A key for unsubscribe links, derived from the token key so nothing new is needed."""
    first = token_keys.split(",")[0].strip()
    return hashlib.sha256(b"firstpr-unsubscribe:" + first.encode()).digest()


def unsubscribe_token(key: bytes, user_id: int) -> str:
    return hmac.new(key, f"unsubscribe:{user_id}".encode(), hashlib.sha256).hexdigest()[:40]


def check_unsubscribe(key: bytes, user_id: int, token: str) -> bool:
    return hmac.compare_digest(unsubscribe_token(key, user_id), token)


# ----------------------------------------------------------------- email


@dataclass
class Email:
    subject: str
    text: str
    html: str


def render(notes: list[Notification], public_url: str, unsubscribe_url: str) -> Email:
    base = public_url.rstrip("/")
    if len(notes) == 1:
        subject = notes[0].title
    else:
        subject = f"FirstPR: {len(notes)} updates on your pull requests"
    text_parts, html_parts = [], []
    for note in notes:
        link = f"{base}{note.link}" if note.link else (note.external_url or base)
        text_parts.append(f"{note.title}\n{note.body}\n{link}")
        html_parts.append(
            f'<p><strong><a href="{html.escape(link)}">{html.escape(note.title)}</a></strong>'
            f"<br>{html.escape(note.body)}</p>"
        )
    footer = (
        "You get this because email is on in your FirstPR settings. "
        f"Turn it off with one click: {unsubscribe_url}"
    )
    return Email(
        subject=subject[:200],
        text="\n\n".join(text_parts) + f"\n\n--\n{footer}\n",
        html="".join(html_parts)
        + '<hr><p style="color:#666;font-size:12px">You get this because email is on in your '
        f'FirstPR settings. <a href="{html.escape(unsubscribe_url)}">Unsubscribe</a> '
        "with one click.</p>",
    )


class Mailer:
    """Sends through Resend's HTTP API. Without an API key it sends nothing."""

    def __init__(
        self,
        api_key: str,
        sender: str,
        public_url: str,
        unsubscribe_key: bytes,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        api_url: str = RESEND_URL,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.sender = sender
        self.public_url = public_url.rstrip("/")
        self.key = unsubscribe_key
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.sender)

    def unsubscribe_url(self, user_id: int) -> str:
        token = unsubscribe_token(self.key, user_id)
        return f"{self.public_url}/api/v1/email/unsubscribe?u={user_id}&t={token}"

    async def send_to_user(self, db: AsyncSession, user_id: int, notes: list[Notification]) -> bool:
        """Email these notifications, if the user has email on. True when sent."""
        if not notes or not self.configured:
            return False
        user = await db.get(User, user_id)
        settings = await prefs(db, user_id)
        if user is None or not user.email or not settings.enabled:
            return False
        unsubscribe = self.unsubscribe_url(user_id)
        email = render(notes, self.public_url, unsubscribe)
        async with httpx.AsyncClient(transport=self.transport, timeout=20) as client:
            resp = await client.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "from": self.sender,
                    "to": [user.email],
                    "subject": email.subject,
                    "text": email.text,
                    "html": email.html,
                    "headers": {
                        "List-Unsubscribe": f"<{unsubscribe}>",
                        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    },
                },
            )
        if resp.status_code >= 300:
            return False
        now = utcnow()
        for note in notes:
            note.emailed_at = now
        await db.commit()
        return True


async def unemailed(db: AsyncSession, user_id: int) -> list[Notification]:
    rows = await db.scalars(
        select(Notification)
        .where(Notification.user_id == user_id, Notification.emailed_at.is_(None))
        .order_by(Notification.id)
    )
    return list(rows)
