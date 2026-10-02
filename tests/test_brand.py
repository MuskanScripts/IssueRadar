"""The product name lives in brand.json; pyproject.toml must agree (ADR 0002)."""

import tomllib
from pathlib import Path

from issueradar.brand import BRAND

ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_matches_brand() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == BRAND.distribution
    assert BRAND.cli in project["scripts"]


def test_env_names_use_prefix() -> None:
    assert BRAND.env("GITHUB_TOKEN") == f"{BRAND.env_prefix}_GITHUB_TOKEN"


def test_brand_name_not_hard_coded_in_python_sources() -> None:
    sources = (ROOT / "src" / "issueradar").rglob("*.py")
    offenders = [p.name for p in sources if BRAND.name in p.read_text(encoding="utf-8")]
    assert offenders == [], f"use BRAND.name instead of the literal name in {offenders}"
