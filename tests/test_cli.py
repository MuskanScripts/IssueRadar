from pathlib import Path

import pytest
from typer.testing import CliRunner

from issueradar import __version__
from issueradar.brand import BRAND
from issueradar.cli import TOKEN_ENV, app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_demo_shows_label_and_only_free_issues() -> None:
    result = runner.invoke(app, ["demo", "--limit", "20"])
    assert result.exit_code == 0, result.stdout
    assert BRAND.demo_label in result.stdout
    assert "Free for you" in result.stdout
    assert "Typo in the error message" not in result.stdout  # claimed in the fixture
    assert "API budget used: 0 requests" in result.stdout


def test_doctor_passes_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.stdout
    assert "All checks passed" in result.stdout
    assert f"{TOKEN_ENV} is not set" in result.stdout


def test_doctor_fails_on_bad_config(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("digest:\n  top_n: 0\n", encoding="utf-8")
    result = runner.invoke(app, ["doctor", "--config", str(bad)])
    assert result.exit_code == 1
    assert "digest.top_n" in result.stdout


def test_watch_add_list_remove() -> None:
    added = runner.invoke(app, ["watch", "add", "octocat/Hello-World", "https://github.com/a/b"])
    assert added.exit_code == 0, added.stdout
    assert "Watching octocat/Hello-World." in added.stdout
    listed = runner.invoke(app, ["watch", "list"])
    assert listed.stdout.split() == ["octocat/Hello-World", "a/b"]
    again = runner.invoke(app, ["watch", "add", "octocat/hello-world"])
    assert "Already watching octocat/Hello-World." in again.stdout
    removed = runner.invoke(app, ["watch", "remove", "a/b"])
    assert "Stopped watching a/b." in removed.stdout


def test_watch_add_from_file(tmp_path: Path) -> None:
    listing = tmp_path / "watchlist.txt"
    listing.write_text(
        "# repos I like\noctocat/Hello-World\n\nhttps://github.com/a/b  # trailing note\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["watch", "add", "--file", str(listing)])
    assert result.exit_code == 0, result.stdout
    assert "Watching octocat/Hello-World." in result.stdout
    assert "Watching a/b." in result.stdout

    listing.write_text("a/b\n", encoding="utf-8")
    exact = runner.invoke(app, ["watch", "add", "--file", str(listing), "--exact"])
    assert "Stopped watching octocat/Hello-World." in exact.stdout
    assert runner.invoke(app, ["watch", "list"]).stdout.split() == ["a/b"]


def test_watch_add_needs_something() -> None:
    assert runner.invoke(app, ["watch", "add"]).exit_code == 2
    assert runner.invoke(app, ["watch", "add", "--file", "missing.txt"]).exit_code == 2


def test_watch_rejects_bad_names() -> None:
    result = runner.invoke(app, ["watch", "add", "not-a-repo"])
    assert result.exit_code == 2
    assert "is not a repository" in result.stdout


def test_sync_with_empty_watchlist_explains_what_to_do() -> None:
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1
    assert "watch add" in result.stdout


def test_doctor_reports_database() -> None:
    result = runner.invoke(app, ["doctor"])
    assert "Database is ready" in result.stdout


def test_network_is_blocked_in_tests() -> None:
    import asyncio

    import httpx

    async def call() -> None:
        async with httpx.AsyncClient() as client:
            await client.get("https://api.github.com/rate_limit")

    with pytest.raises(RuntimeError, match="must not touch the network"):
        asyncio.run(call())
