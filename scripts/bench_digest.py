"""Time digest generation on a generated database (no network).

Usage: python scripts/bench_digest.py [repos] [issues_per_repo]

The data is generated from GitHub's documented issue shape, so it measures
speed only; it says nothing about real repositories.
"""

from __future__ import annotations

import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from issueradar.config import load_settings
from issueradar.digest import DigestBuilder
from issueradar.engine.rules import load_rules
from issueradar.radar import Radar
from issueradar.storage import open_database
from issueradar.storage.models import Issue, Repo, Watchlist


def main() -> None:
    repos = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    per_repo = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    folder = Path(tempfile.mkdtemp())
    db = open_database(f"sqlite:///{(folder / 'bench.sqlite').as_posix()}")
    now = datetime.now(UTC)
    with db.sessions.begin() as session:
        for r in range(repos):
            repo = Repo(full_name=f"bench/repo{r}", github_id=r + 1, language="Python",
                        pushed_at=now, health={"score": 60 + r % 30, "reasons": [], "flags": {}})
            session.add(repo)
            session.add(Watchlist(user_id=1, repo_full_name=repo.full_name))
            session.flush()
            for n in range(per_repo):
                session.add(Issue(
                    github_id=r * 100_000 + n, repo_id=repo.id, number=n + 1,
                    title=f"Fix typo in docs page {n}" if n % 3 == 0 else f"Crash when parsing {n}",
                    body="Steps to reproduce: run it.\n" + "x" * (n * 7 % 2000),
                    state="open", labels=["good first issue"] if n % 4 == 0 else ["bug"],
                    assignees=[], comments_count=0, locked=False,
                    gh_created_at=now - timedelta(days=n % 90),
                    gh_updated_at=now - timedelta(days=n % 30), timeline_checked_at=now,
                    linked_pr=False,
                ))
    settings = load_settings()
    radar = Radar(db, settings, load_rules(), None)
    start = time.perf_counter()
    digest = DigestBuilder(db, settings, radar).build()
    elapsed = time.perf_counter() - start
    print(f"{repos} repos x {per_repo} issues = {repos * per_repo} open issues")
    print(f"digest built in {elapsed:.2f} s ({len(digest.free)} free items, "
          f"{len(digest.new_since)} new)")


if __name__ == "__main__":
    main()
