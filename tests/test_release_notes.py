import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_notes.py"
spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
assert spec and spec.loader
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## [Unreleased]

- Not out yet.

## [0.2.0] - 2026-11-01

### Added

- Thing two.

## [0.1.0] - 2026-10-02

- Thing one.
"""


def test_picks_one_section() -> None:
    assert release_notes.section(CHANGELOG, "0.2.0") == "### Added\n\n- Thing two.\n"
    assert release_notes.section(CHANGELOG, "0.1.0") == "- Thing one.\n"


def test_missing_version_fails() -> None:
    with pytest.raises(SystemExit, match=r"no section for 9\.9\.9"):
        release_notes.section(CHANGELOG, "9.9.9")
