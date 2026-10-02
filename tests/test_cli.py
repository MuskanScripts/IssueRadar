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
