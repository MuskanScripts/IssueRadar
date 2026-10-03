"""Print one version's section of CHANGELOG.md, for the GitHub release.

python scripts/release_notes.py 0.1.0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def section(text: str, version: str) -> str:
    pattern = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", re.S | re.M)
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"CHANGELOG.md has no section for {version}. Add '## [{version}] - date'.")
    return match.group(1).strip() + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/release_notes.py <version>")
    sys.stdout.write(section(CHANGELOG.read_text(encoding="utf-8"), sys.argv[1].lstrip("v")))
