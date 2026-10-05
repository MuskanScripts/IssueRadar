"""The Start working flow: fork, sync, branch, Codespace, and the fallbacks."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fake_user_github import FakeUserGitHub
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from firstpr_platform import workspaces
from firstpr_platform.db import Base, User, Workspace, session_factory
from firstpr_platform.github_user import UserGitHub

UPSTREAM = "pallets/flask"


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'w.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory(engine)() as session:
        session.add(User(id=1, handle="MuskanScripts"))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.fixture
def github() -> FakeUserGitHub:
    fake = FakeUserGitHub()
    fake.upstream(UPSTREAM)
    return fake


async def no_sleep(_: float) -> None:
    return None


async def run(db: AsyncSession, github: FakeUserGitHub, mode: str = "codespace") -> Workspace:
    ws = Workspace(
        user_id=1,
        repo_full_name=UPSTREAM,
        number=42,
        issue_title="Docs: fix the broken link!",
        mode=mode,
        status=workspaces.QUEUED,
        steps=workspaces.new_steps(mode),
    )
    db.add(ws)
    await db.commit()
    async with UserGitHub("ghu_x", transport=github.transport()) as gh:
        await workspaces.start(db, ws, gh, "MuskanScripts", sleep=no_sleep)
    return ws


def states(ws: Workspace) -> dict[str, str]:
    return {s["key"]: s["state"] for s in ws.steps}


async def test_fork_branch_and_codespace(db: AsyncSession, github: FakeUserGitHub) -> None:
    ws = await run(db, github)
    assert ws.status == workspaces.READY
    assert set(states(ws).values()) == {"done"}
    assert ws.fork_full_name == "MuskanScripts/flask"
    assert ws.branch == "firstpr/42-docs-fix-the-broken-link"
    assert github.branches["muskanscripts/flask"][ws.branch] == "a" * 40  # from upstream
    space = github.codespaces[ws.codespace_name or ""]
    assert space["idle_timeout_minutes"] == 15
    assert space["retention_period_minutes"] == 7 * 24 * 60
    assert [m for m, _ in github.writes] == ["POST"] * 4  # fork, sync, branch, codespace


async def test_an_existing_fork_and_branch_are_reused(
    db: AsyncSession, github: FakeUserGitHub
) -> None:
    first = await run(db, github, mode="local")
    writes = len(github.writes)
    first.status = workspaces.QUEUED
    first.steps = workspaces.new_steps("local")
    await db.commit()
    async with UserGitHub("ghu_x", transport=github.transport()) as gh:
        await workspaces.start(db, first, gh, "MuskanScripts", sleep=no_sleep)
    assert first.status == workspaces.READY
    new = github.writes[writes:]
    assert [p for _, p in new] == ["/repos/MuskanScripts/flask/merge-upstream"]


async def test_not_installed_stops_at_the_first_step(
    db: AsyncSession, github: FakeUserGitHub
) -> None:
    github.installed = False
    ws = await run(db, github)
    assert ws.status == workspaces.FAILED
    assert states(ws)["install"] == "failed" and "Install FirstPR" in (ws.note or "")
    assert github.writes == []


async def test_a_fork_the_app_cannot_see_explains_what_to_do(
    db: AsyncSession, github: FakeUserGitHub
) -> None:
    github.fork_visible = False
    ws = await run(db, github)
    assert ws.status == workspaces.FAILED and states(ws)["fork"] == "failed"
    assert ws.help_url == workspaces.INSTALLATIONS_URL


async def test_a_codespace_that_cannot_start_falls_back_to_local(
    db: AsyncSession, github: FakeUserGitHub
) -> None:
    github.codespace_error = (403, "You have used all your Codespaces hours")
    ws = await run(db, github)
    assert ws.status == workspaces.READY and ws.mode == workspaces.LOCAL
    assert "Codespaces hours" in (ws.note or "") and "own computer" in (ws.note or "")
    assert states(ws)["codespace"] == "failed"


async def test_a_failed_codespace_state_falls_back_too(
    db: AsyncSession, github: FakeUserGitHub
) -> None:
    github.codespace_state = "Starting"
    ws = await run(db, github)
    assert ws.status == workspaces.WORKING
    github.codespace_state = "Failed"
    async with UserGitHub("ghu_x", transport=github.transport()) as gh:
        await workspaces.check_codespace(db, ws, gh)
    assert ws.status == workspaces.READY and ws.mode == workspaces.LOCAL


async def test_a_diverged_fork_still_gets_a_branch(
    db: AsyncSession, github: FakeUserGitHub
) -> None:
    github.sync_conflict = True
    ws = await run(db, github, mode="local")
    assert ws.status == workspaces.READY and states(ws)["sync"] == "skipped"
    assert ws.base_sha == "a" * 40


def test_branch_names() -> None:
    assert (
        workspaces.branch_name(7, "Add NO_COLOR support (CLI)")
        == "firstpr/7-add-no-color-support-cli"
    )
    assert workspaces.branch_name(7, "!!!") == "firstpr/7"
