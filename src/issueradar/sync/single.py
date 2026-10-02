"""Fetch one issue on demand, for ``explain`` on a repo that is not synced yet."""

from __future__ import annotations

import re

from sqlalchemy import select

from issueradar.config.settings import Settings
from issueradar.engine.rules import RepoRules
from issueradar.github.client import GitHubClient
from issueradar.storage.db import Database
from issueradar.storage.models import Issue, Repo
from issueradar.sync.enrich import Enricher
from issueradar.sync.normalize import is_pull_request, issue_fields
from issueradar.sync.service import SyncService

_ISSUE_URL = re.compile(
    r"^(?:https?://github\.com/)?(?P<repo>[\w.-]+/[\w.-]+)(?:/issues/|#)(?P<num>\d+)/?$"
)


class IssueUrlError(ValueError):
    pass


def parse_issue_ref(value: str) -> tuple[str, int]:
    """Accept https://github.com/o/r/issues/12, o/r/issues/12 or o/r#12."""
    text = value.strip()
    if "/pull/" in text:
        raise IssueUrlError("That is a pull request. explain works on issues.")
    match = _ISSUE_URL.match(text)
    if not match:
        raise IssueUrlError(
            f"'{value}' is not an issue link. Use https://github.com/owner/repo/issues/123."
        )
    return match.group("repo"), int(match.group("num"))


async def ensure_issue(
    db: Database,
    client: GitHubClient,
    settings: Settings,
    rules: dict[str, RepoRules],
    full_name: str,
    number: int,
) -> str:
    """Make sure the repo, the issue and its details are stored. Returns the repo name."""
    service = SyncService(db, client, settings)
    enricher = Enricher(db, client, settings, rules)
    repo_data = (await client.get(f"/repos/{full_name}")).data
    actual = str(repo_data["full_name"])
    issue_data = (await client.get(f"/repos/{actual}/issues/{number}")).data
    if is_pull_request(issue_data):
        raise IssueUrlError(f"{actual}#{number} is a pull request, not an issue.")
    pulls = await service._list(f"/repos/{actual}/pulls")

    now = service.clock()
    with db.sessions.begin() as session:
        repo = service._upsert_repo(session, full_name, repo_data, now)
        service._store_pulls(session, repo, pulls.items, pulls.complete, now)
        fields = issue_fields(issue_data)
        issue = session.scalar(select(Issue).where(Issue.github_id == fields["github_id"]))
        if issue is None:
            issue = Issue(repo_id=repo.id, **fields)
            session.add(issue)
        else:
            for key, value in fields.items():
                setattr(issue, key, value)
        session.flush()
        issue_id = issue.id
        needs_comments = issue.comments_count > 0
    if needs_comments:
        await enricher._read_comments(issue_id, actual, number)
    if settings.enrich.fetch_timeline:
        await enricher._read_timeline(issue_id, actual, number)
    await enricher.refresh_health(actual)
    return actual


def is_stored(db: Database, full_name: str, number: int) -> bool:
    with db.sessions() as session:
        repo = session.scalar(select(Repo).where(Repo.full_name.ilike(full_name)))
        if repo is None:
            return False
        issue = session.scalar(
            select(Issue).where(Issue.repo_id == repo.id, Issue.number == number)
        )
        return issue is not None and issue.timeline_checked_at is not None
