"""The real engine behind the worker: watchlist mirroring and a full sync.

Uses the core test suite's fake GitHub and scenario (repo-root tests/), so the
whole sync path runs: lists, ETags, enrichment and health. SQLite by default;
Postgres when FIRSTPR_TEST_CATALOGUE_URL is set (CI sets it).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

CORE_TESTS = Path(__file__).resolve().parents[3] / "tests"
sys.path.insert(0, str(CORE_TESTS))

from fake_github import FakeGitHub  # noqa: E402
from firstpr_worker.catalogue import APP_OWNER, Catalogue, engine_user_id  # noqa: E402
from issueradar.storage.models import Issue, Watchlist  # noqa: E402
from scenario import REPO, build  # noqa: E402


@pytest.fixture
def catalogue_url(tmp_path: Path) -> str:
    return os.environ.get("FIRSTPR_TEST_CATALOGUE_URL") or f"sqlite:///{tmp_path / 'catalogue.db'}"


def test_watchlists_mirror_each_owner(catalogue_url: str) -> None:
    catalogue = Catalogue(catalogue_url, pause_share=0.2)
    owner = engine_user_id(9)
    catalogue.set_watchlist(owner, {"a/one", "b/two"})
    catalogue.set_watchlist(owner, {"B/two", "c/three"})
    with catalogue.db.sessions() as session:
        names = set(
            session.scalars(select(Watchlist.repo_full_name).where(Watchlist.user_id == owner))
        )
    assert names == {"b/two", "c/three"}
    catalogue.clear_watchlist(owner)
    with catalogue.db.sessions() as session:
        assert session.scalar(select(Watchlist).where(Watchlist.user_id == owner)) is None


async def test_full_sync_then_mostly_304s(catalogue_url: str) -> None:
    fake = FakeGitHub()
    build(fake)
    catalogue = Catalogue(catalogue_url, pause_share=0.2, transport=fake.transport())

    first = await catalogue.sync(APP_OWNER, {REPO}, "ghs_hour_one", "app")
    assert first.status == "completed"
    assert [(o.full_name, o.status) for o in first.outcomes] == [(REPO, "synced")]
    assert first.outcomes[0].open_issues > 0
    with catalogue.db.sessions() as session:
        assert session.scalar(select(Issue).limit(1)) is not None

    # An hour later the installation token is a new one; ETags still apply.
    second = await catalogue.sync(APP_OWNER, {REPO}, "ghs_hour_two", "app")
    assert second.status == "completed"
    assert second.budget["not_modified"] > 0


async def test_cards_carry_the_engines_verdicts(catalogue_url: str) -> None:
    fake = FakeGitHub()
    build(fake)
    catalogue = Catalogue(catalogue_url, pause_share=0.2, transport=fake.transport())
    await catalogue.sync(APP_OWNER, {REPO}, "ghs_token", "app")

    by_repo = catalogue.cards({REPO, "nobody/synced-this"})
    assert set(by_repo) == {REPO}  # repos the engine never saw are left out
    cards = by_repo[REPO]
    assert cards and all(c.repo_full_name == REPO for c in cards)
    states = {c.availability for c in cards}
    assert states & {"free", "likely_free"}
    sample = cards[0]
    assert sample.tier in {"beginner", "intermediate", "pro"} and sample.time_bucket
    assert sample.checklist and sample.availability_reasons


async def test_tracking_reads_recorded_pull_requests(catalogue_url: str) -> None:
    from test_prs import REPO as PR_REPO
    from test_prs import serve_pr

    fake = FakeGitHub()
    recorded = serve_pr(fake, 16)
    serve_pr(fake, 14)
    catalogue = Catalogue(catalogue_url, pause_share=0.2, transport=fake.transport())
    result = await catalogue.track(
        "ghu_token",
        "user:1",
        "MuskanScripts",
        [(PR_REPO, 16), (PR_REPO, 14)],
        discover=False,
        now=recorded,
    )
    assert result.failed == {}
    statuses = {t.facts.number: t.status.status.value for t in result.pulls}
    assert statuses == {16: "waiting_for_review", 14: "merged"}
    assert all(r.method == "GET" for r in fake.requests)


def test_the_catalogue_database_is_created_when_missing() -> None:
    url = os.environ.get("FIRSTPR_TEST_CATALOGUE_URL")
    if not url or not url.startswith("postgresql"):
        pytest.skip("needs Postgres (CI sets FIRSTPR_TEST_CATALOGUE_URL)")
    from sqlalchemy import create_engine, make_url, text

    from firstpr_worker.catalogue import ensure_database

    target = make_url(url).set(database="firstpr_catalogue_created_by_test")
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}"'))
    assert ensure_database(target.render_as_string(hide_password=False)) is True
    assert ensure_database(target.render_as_string(hide_password=False)) is False
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{target.database}"'))
    admin.dispose()
