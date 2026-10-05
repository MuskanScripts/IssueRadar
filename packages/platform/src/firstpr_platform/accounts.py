"""Storing a GitHub sign-in, and keeping its token usable."""

from __future__ import annotations

from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_platform.crypto import TokenBox
from firstpr_platform.db import GitHubAccount, User, utcnow
from firstpr_platform.github_oauth import GitHubAuthError, GitHubOAuth, GitHubUser, Tokens

CONNECTED = "connected"
RECONNECT_NEEDED = "reconnect_needed"
# Refresh a little before the 8-hour token runs out.
REFRESH_MARGIN = timedelta(minutes=5)


def _store_tokens(account: GitHubAccount, tokens: Tokens, box: TokenBox) -> None:
    account.access_token = box.seal(tokens.access_token)
    account.access_expires_at = tokens.access_expires_at
    account.refresh_token = box.seal(tokens.refresh_token) if tokens.refresh_token else None
    account.refresh_expires_at = tokens.refresh_expires_at


async def upsert(
    db: AsyncSession,
    gh: GitHubUser,
    tokens: Tokens,
    box: TokenBox,
    admin_logins: frozenset[str] = frozenset(),
) -> User:
    account = await db.scalar(select(GitHubAccount).where(GitHubAccount.github_id == gh.id))
    if account is None:
        user = User(handle=gh.login, name=gh.name, email=gh.email, avatar_url=gh.avatar_url)
        account = GitHubAccount(github_id=gh.id, login=gh.login, user=user)
        db.add(user)
    else:
        user = account.user
        user.handle, user.name, user.avatar_url = gh.login, gh.name, gh.avatar_url
        user.email = gh.email or user.email
        account.login = gh.login
    _store_tokens(account, tokens, box)
    account.status = CONNECTED
    account.last_verified_at = utcnow()
    # Checked on every sign-in, so removing a login from the list takes the role away.
    user.role = "admin" if gh.login.lower() in admin_logins else "user"
    await db.commit()
    return user


async def usable_token(
    db: AsyncSession, account: GitHubAccount, box: TokenBox, oauth: GitHubOAuth
) -> str | None:
    """The user's access token, refreshed if it is about to expire.

    Returns None, and marks the account, when GitHub no longer accepts it.
    """
    if account.status != CONNECTED:
        return None
    now = utcnow()
    expires = account.access_expires_at
    if expires is None or expires - REFRESH_MARGIN > now:
        return box.open(account.access_token)
    if account.refresh_token is None or (
        account.refresh_expires_at is not None and account.refresh_expires_at <= now
    ):
        await mark_reconnect(db, account)
        return None
    try:
        tokens = await oauth.refresh(box.open(account.refresh_token))
    except GitHubAuthError:
        await mark_reconnect(db, account)
        return None
    _store_tokens(account, tokens, box)
    await db.commit()
    return tokens.access_token


async def mark_reconnect(db: AsyncSession, account: GitHubAccount) -> None:
    account.status = RECONNECT_NEEDED
    await db.commit()


async def verify(
    db: AsyncSession,
    account: GitHubAccount,
    box: TokenBox,
    oauth: GitHubOAuth,
    every_seconds: int,
) -> None:
    """Check with GitHub, at most every `every_seconds`, that access still works.

    This is how a revoked app shows up as "reconnect needed". If GitHub cannot
    be reached, nothing changes.
    """
    if account.status != CONNECTED:
        return
    last = account.last_verified_at
    if last is not None and (utcnow() - last).total_seconds() < every_seconds:
        return
    token = await usable_token(db, account, box, oauth)
    if token is None:
        return
    try:
        await oauth.get_user(token)
    except GitHubAuthError:
        await mark_reconnect(db, account)
        return
    except httpx.HTTPError:
        return
    account.last_verified_at = utcnow()
    await db.commit()
