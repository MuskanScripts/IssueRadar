"""Copy the built dashboard into the Python package, so `firstpr serve` has it.

Run after `npm run build` in web/, before `python -m build`:

    cd web; npm ci; npm run build; cd ..
    python scripts/bundle_web.py
    python -m build
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web" / "dist"
TARGET = ROOT / "src" / "issueradar" / "web"


def main() -> None:
    if not (SOURCE / "index.html").is_file():
        sys.exit("web/dist is missing. Run `npm run build` in web/ first.")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(SOURCE, TARGET)
    count = sum(1 for p in TARGET.rglob("*") if p.is_file())
    print(f"Copied {count} files to {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
