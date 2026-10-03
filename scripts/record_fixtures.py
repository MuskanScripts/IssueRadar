"""Record real GitHub API responses as test fixtures.

Usage (PowerShell, from the repository root, virtual environment active):

    python scripts/record_fixtures.py MuskanScripts/IssueRadar
    python scripts/record_fixtures.py --pr MuskanScripts/IssueRadar#15

Writes one JSON file per request into tests/fixtures/github/recorded/. Only
public data is requested, only GET is used (through the read-only client), and
no token or authorization header is ever written to disk.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from issueradar.config import load_settings
from issueradar.github import GitHubClient, token_from_env
from issueradar.github.cache import MemoryEtagCache

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "github" / "recorded"
KEEP_HEADERS = (
    "content-type",
    "etag",
    "link",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-used",
    "x-ratelimit-reset",
    "x-ratelimit-resource",
)


# temp_clone_token is a real token for private repos; performed_via_github_app is app
# metadata the tracker never reads.
SCRUB_KEYS = frozenset({"temp_clone_token", "performed_via_github_app"})


def scrub(value: Any) -> Any:
    """Blank out fields that can hold credentials before anything is written."""
    if isinstance(value, dict):
        return {k: None if k in SCRUB_KEYS else scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def slug(repo: str, name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"{repo}-{name}".lower()).strip("-")


async def record(repo: str) -> list[Path]:
    settings = load_settings()
    token, _ = token_from_env(os.environ)
    written: list[Path] = []
    requests = [
        ("repo", f"/repos/{repo}", None),
        (
            "issues-open",
            f"/repos/{repo}/issues",
            {"state": "open", "per_page": 100, "sort": "created", "direction": "asc"},
        ),
        (
            "pulls-open",
            f"/repos/{repo}/pulls",
            {"state": "open", "per_page": 100, "sort": "created", "direction": "asc"},
        ),
    ]
    async with GitHubClient(settings.github, token, cache=MemoryEtagCache()) as client:
        for name, path, params in requests:
            response = await client.get(path, params=params)
            fixture = {
                "source": "recorded",
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "authenticated": client.authenticated,
                "request": {"method": "GET", "url": response.url},
                "response": {
                    "status": response.status,
                    "headers": {
                        k: response.headers[k] for k in KEEP_HEADERS if k in response.headers
                    },
                    "body": scrub(response.data),
                },
            }
            target = OUT / f"{slug(repo, name)}.json"
            target.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
            written.append(target)
            if name == "repo":
                again = await client.get(path)  # conditional: records a real 304
                fixture_304 = {
                    **fixture,
                    "response": {
                        "status": again.status,
                        "headers": {
                            k: again.headers[k] for k in KEEP_HEADERS if k in again.headers
                        },
                        "body": None,
                    },
                }
                target = OUT / f"{slug(repo, 'repo-304')}.json"
                target.write_text(json.dumps(fixture_304, indent=2) + "\n", encoding="utf-8")
                written.append(target)
    return written


async def record_pr(ref: str) -> Path:
    """Everything the PR tracker reads for one PR, in one file."""
    repo, number = ref.split("#")
    settings = load_settings()
    token, _ = token_from_env(os.environ)
    async with GitHubClient(settings.github, token, cache=MemoryEtagCache()) as client:
        pr = (await client.get(f"/repos/{repo}/pulls/{number}")).data
        sha = pr["head"]["sha"]
        bundle = {
            "pull": pr,
            "reviews": (
                await client.get(f"/repos/{repo}/pulls/{number}/reviews", params={"per_page": 100})
            ).data,
            "check_runs": (
                await client.get(
                    f"/repos/{repo}/commits/{sha}/check-runs", params={"per_page": 100}
                )
            ).data,
            "status": (await client.get(f"/repos/{repo}/commits/{sha}/status")).data,
            "timeline": (
                await client.get(
                    f"/repos/{repo}/issues/{number}/timeline", params={"per_page": 100}
                )
            ).data,
        }
    fixture = {
        "source": "recorded",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pull_request": f"{repo}#{number}",
        "body": scrub(bundle),
    }
    target = OUT / "prs" / f"{slug(repo, 'pr-' + number)}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    OUT.mkdir(parents=True, exist_ok=True)
    args = sys.argv[1:]
    if args[0] == "--pr":
        for ref in args[1:]:
            path = asyncio.run(record_pr(ref))
            print(f"wrote {path.relative_to(OUT.parents[3])}")
        return
    for repo in args:
        for path in asyncio.run(record(repo)):
            print(f"wrote {path.relative_to(OUT.parents[3])}")


if __name__ == "__main__":
    main()
