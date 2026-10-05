"""Maintainers opt out with .github/firstpr.yml, and can come back."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from conftest import make_card
from firstpr_platform.db import CatalogueRepo, IssueCard
from firstpr_worker import jobs


class Repos:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.path}")
        repo = request.url.path.removeprefix("/repos/").split("/contents/")[0]
        if repo in self.files:
            return httpx.Response(200, text=self.files[repo])
        return httpx.Response(404, json={"message": "Not Found"})


def test_only_a_clear_opt_out_counts() -> None:
    assert jobs.wants_out("opt_out: true\n")
    assert not jobs.wants_out("opt_out: false")
    assert not jobs.wants_out("opt_out: yes please")
    assert not jobs.wants_out(": not yaml : [")
    assert not jobs.wants_out("")


async def test_an_opted_out_repo_leaves_and_can_come_back(
    ctx: dict[str, Any], sync_db: OrmSession
) -> None:
    repos = Repos()
    ctx["github_transport"] = httpx.MockTransport(repos.handler)
    for name in ("a/one", "b/two"):
        sync_db.add(CatalogueRepo(full_name=name, source="pack"))
    sync_db.commit()
    ctx["catalogue"].issues = {"a/one": [make_card("a/one", 1)], "b/two": [make_card("b/two", 2)]}
    await jobs.sync_catalogue(ctx)
    assert len(sync_db.scalars(select(IssueCard)).all()) == 2

    repos.files["a/one"] = "# FirstPR, please do not send people here\nopt_out: true\n"
    assert await jobs.check_opt_outs(ctx) == "a/one opted out"
    sync_db.expire_all()
    assert [c.repo_full_name for c in sync_db.scalars(select(IssueCard))] == ["b/two"]
    await jobs.sync_catalogue(ctx)
    assert ctx["catalogue"].calls[-1][1] == {"b/two"}  # no longer synced
    assert all(c.startswith("GET ") for c in repos.calls)  # reads only

    # Checked once a day: nothing is read again today.
    before = len(repos.calls)
    await jobs.check_opt_outs(ctx)
    assert len(repos.calls) == before

    del repos.files["a/one"]
    sync_db.execute(CatalogueRepo.__table__.update().values(opt_out_checked_at=None))
    sync_db.commit()
    assert await jobs.check_opt_outs(ctx) == "a/one is back"
