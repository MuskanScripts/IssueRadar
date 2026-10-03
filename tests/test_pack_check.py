"""`firstpr pack verify`: repo checks for starter packs. Fake GitHub only."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from fake_github import FakeGitHub, example_pull, example_repo
from issueradar.cli import app
from issueradar.config import Settings
from issueradar.engine.rules import load_rules
from issueradar.github import GitHubClient
from issueradar.sync.pack_check import check_repo

IMPORTER = "google/adk-python"  # its preset rule: accepted PRs get "ready to pull" and are closed
CLOSED = "/pulls?direction=desc&per_page=100&sort=updated&state=closed"


def closed_pr(n: int, *, merged: bool = False, labels: tuple[str, ...] = (), **kw: Any) -> Any:
    return example_pull(
        n,
        "",
        state="closed",
        author_association=kw.pop("assoc", "CONTRIBUTOR"),
        merged_at="2026-09-01T00:00:00Z" if merged else None,
        labels=[{"name": label} for label in labels],
        **kw,
    )


def serve(fake: FakeGitHub, repo: str, pulls: list[Any], *, contributing: bool = True) -> None:
    fake.add(f"/repos/{repo}", example_repo(repo, pushed_at="2026-10-02T10:00:00Z"))
    files = {"contributing": {"url": "x"} if contributing else None}
    fake.add(f"/repos/{repo}/community/profile", {"files": files})
    fake.add(f"/repos/{repo}{CLOSED}", pulls)


@pytest.mark.parametrize(
    ("repo", "accepted", "imported"),
    [(IMPORTER, 3, 2), ("someone/else", 1, 0)],  # same label means nothing without a rule
)
async def test_imported_prs_count_as_accepted_only_with_a_rule(
    settings: Settings, repo: str, accepted: int, imported: int
) -> None:
    fake = FakeGitHub()
    pulls = [
        closed_pr(1, labels=("ready to pull",)),
        closed_pr(2, labels=("Ready To Pull", "docs")),
        closed_pr(3, merged=True),
        closed_pr(4),  # really rejected
        closed_pr(5, merged=True, assoc="MEMBER"),  # maintainers don't count
        closed_pr(6, merged=True, user={"login": "dependabot[bot]", "type": "Bot"}),
    ]
    serve(fake, repo, pulls)
    async with GitHubClient(settings.github, "t", transport=fake.transport()) as client:
        result = await check_repo(client, repo, settings, load_rules())
    assert (result.outside, result.accepted, result.imported) == (4, accepted, imported)
    assert result.contributing and result.last_push == "2026-10-02" and not result.archived
    assert {r.method for r in fake.requests} == {"GET"}


async def test_errors_are_reported_per_repo(settings: Settings) -> None:
    fake = FakeGitHub()
    fake.add("/repos/gone/away", {"message": "Not Found"}, status=404)
    async with GitHubClient(settings.github, "t", transport=fake.transport()) as client:
        result = await check_repo(client, "gone/away", settings, load_rules())
    assert result.error and result.outside == 0


def test_verify_needs_a_pack_or_a_repo() -> None:
    assert CliRunner().invoke(app, ["pack", "verify"]).exit_code == 2
    assert CliRunner().invoke(app, ["pack", "verify", "no-such-pack"]).exit_code == 2
    assert CliRunner().invoke(app, ["pack", "verify", "--repo", "not a repo"]).exit_code == 2


def test_verify_cli_with_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeGitHub()
    serve(fake, IMPORTER, [closed_pr(1, labels=("ready to pull",)), closed_pr(2)])
    original = GitHubClient.__init__

    def with_fake(self: GitHubClient, *args: Any, **kw: Any) -> None:
        kw["transport"] = fake.transport()
        original(self, *args, **kw)

    monkeypatch.setattr(GitHubClient, "__init__", with_fake)
    result = CliRunner().invoke(app, ["pack", "verify", "--repo", IMPORTER], env={"COLUMNS": "200"})
    out = " ".join(result.stdout.split())
    assert result.exit_code == 0, result.stdout
    assert "1 of 2 (50%), 1 imported by a bot" in out
