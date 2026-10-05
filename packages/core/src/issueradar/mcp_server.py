"""MCP server (M8): the radar as read-only tools for an AI assistant.

Three tools, all read-only toward GitHub and toward your own data:

* ``find_issues``: free issues from your synced repos, best match first.
* ``explain_issue``: why one issue is or isn't free, its level, the repo's
  health and a checklist. Fetches that one issue (GET only) if it isn't stored.
* ``my_prs``: your tracked pull requests and what each one needs from you.

Answers come from the local database that ``firstpr sync`` and ``firstpr prs``
fill. Nothing here dismisses, snoozes, comments or writes anywhere; the
dashboard and CLI keep those actions. Runs over stdio: ``firstpr mcp``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from issueradar import __version__
from issueradar.api import profile as profile_store
from issueradar.api.app import IssueOut, PullOut, issue_out, pull_out
from issueradar.brand import BRAND
from issueradar.config.settings import Settings
from issueradar.engine.rules import RepoRules
from issueradar.engine.stack import SkillProfile
from issueradar.github.client import GitHubClient
from issueradar.github.errors import GitHubError
from issueradar.models import IssueType, PullRequestStatus, Tier, TimeBucket
from issueradar.prs.tracker import tracked
from issueradar.radar import Filters, IssueReport, Radar
from issueradar.storage.db import Database
from issueradar.sync import watchlist
from issueradar.sync.single import IssueUrlError, ensure_issue, is_stored, parse_issue_ref

INSTRUCTIONS = f"""{BRAND.name} finds open-source issues a person can actually work on, and \
tracks the pull requests they open. Use find_issues to suggest work, explain_issue before \
recommending a specific issue, and my_prs to see what their open pull requests need.

Everything is read-only. The data comes from the user's local {BRAND.name} database, filled \
by `{BRAND.cli} sync` and `{BRAND.cli} prs`; if a tool says nothing is synced, tell the user \
to run those commands. Nudge drafts in my_prs are for the user to copy; never post them."""

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)


class IssueSummary(BaseModel):
    """One line of find_issues: enough to pick, explain_issue for the rest."""

    issue: str = Field(description="owner/repo#number")
    title: str
    url: str | None
    level: Tier
    availability: str = Field(description="free or likely_free")
    time: TimeBucket
    type: IssueType
    language: str | None
    repo_health: int | None = Field(description="0 to 100, None if not measured yet")
    rank: float | None = Field(description="0 to 1, higher is a better match")
    why: str = Field(description="One line on why it is a good match")


class FindIssuesOut(BaseModel):
    issues: list[IssueSummary]
    note: str | None = Field(default=None, description="What to do when the list is empty")


class MyPrsOut(BaseModel):
    pull_requests: list[PullOut]
    last_checked: datetime | None = Field(description="When the PRs were last read from GitHub")
    note: str | None = None


def summary(report: IssueReport) -> IssueSummary:
    return IssueSummary(
        issue=f"{report.repo}#{report.number}",
        title=report.title,
        url=report.url,
        level=report.difficulty.tier,
        availability=report.availability.state.value,
        time=report.difficulty.time_bucket,
        type=report.difficulty.issue_type,
        language=report.language,
        repo_health=report.health_score,
        rank=round(report.rank.score, 3) if report.rank else None,
        why=report.rank.why if report.rank else "",
    )


def create_server(
    db: Database,
    settings: Settings,
    rules: dict[str, RepoRules],
    *,
    file_profile: SkillProfile | None = None,
    client_factory: Callable[[], GitHubClient] | None = None,
) -> MCPServer:
    """Build the server. ``client_factory`` lets explain_issue fetch an issue that
    isn't stored yet; without it (no token) only stored issues can be explained."""
    server = MCPServer(
        name=BRAND.cli,
        title=BRAND.name,
        description=BRAND.tagline,
        instructions=INSTRUCTIONS,
        website_url=BRAND.repository,
        version=__version__,
    )

    def radar() -> Radar:
        return Radar(db, settings, rules, profile_store.load(db) or file_profile)

    @server.tool(title="Find free issues", annotations=READ_ONLY)
    def find_issues(
        level: Annotated[
            list[Tier] | None, Field(description="Levels to include. Default: all.")
        ] = None,
        language: Annotated[
            list[str] | None, Field(description="Languages, for example python or java")
        ] = None,
        issue_type: Annotated[list[IssueType] | None, Field(description="Kinds of work")] = None,
        time: Annotated[list[TimeBucket] | None, Field(description="Rough time needed")] = None,
        repo: Annotated[list[str] | None, Field(description="Only these owner/name repos")] = None,
        min_health: Annotated[int | None, Field(ge=0, le=100)] = None,
        no_discussion: Annotated[
            bool, Field(description="Hide issues where a proposal is needed first")
        ] = False,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> FindIssuesOut:
        """Free issues from the user's watched repositories, best match for their level
        and skills first. Only issues nobody has claimed are listed."""
        filters = Filters(
            tiers=level or [],
            languages=language or [],
            issue_types=issue_type or [],
            times=time or [],
            repos=repo or [],
            min_health=min_health,
            exclude_discussion_first=no_discussion,
        )
        found = [summary(r) for r in radar().find(filters, limit)]
        note = None
        if not found:
            note = (
                f"Nothing watched yet. The user can add repos with `{BRAND.cli} watch add "
                f"owner/name` and then run `{BRAND.cli} sync`."
                if not watchlist.list_watched(db)
                else "No free issue matches these filters. Try fewer filters."
            )
        return FindIssuesOut(issues=found, note=note)

    @server.tool(
        title="Explain an issue",
        annotations=ToolAnnotations(
            read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True
        ),
    )
    async def explain_issue(
        issue: Annotated[
            str,
            Field(description="An issue link, or owner/repo#123"),
        ],
    ) -> IssueOut:
        """Why an issue is or isn't free, its level with reasons, the repo's health,
        things to know before starting (CLA, DCO, AI policy) and a checklist."""
        try:
            repo, number = parse_issue_ref(issue)
        except IssueUrlError as exc:
            raise ToolError(str(exc)) from exc
        if not is_stored(db, repo, number):
            if client_factory is None:
                raise ToolError(
                    f"{repo}#{number} isn't synced, and there is no GitHub token to fetch it. "
                    f"Set {BRAND.env('GITHUB_TOKEN')} or run `{BRAND.cli} explain` once."
                )
            try:
                async with client_factory() as client:
                    repo = await ensure_issue(db, client, settings, rules, repo, number)
            except (GitHubError, IssueUrlError) as exc:
                raise ToolError(f"Could not fetch {repo}#{number}: {exc}") from exc
        report = radar().report_for(repo, number)
        if report is None:
            raise ToolError(f"{repo}#{number} could not be found.")
        return issue_out(report, settings)

    @server.tool(title="My pull requests", annotations=READ_ONLY)
    def my_prs(
        needs_me_only: Annotated[
            bool, Field(description="Only PRs where the user has something to do")
        ] = False,
        include_closed: Annotated[bool, Field(description="Also merged and closed PRs")] = False,
    ) -> MyPrsOut:
        """The user's pull requests, most urgent first, with what each one needs and a
        nudge draft for quiet ones. The draft is for the user to send, never post it."""
        rows = tracked(db)
        if not include_closed:
            rows = [r for r in rows if r.state == "open"]
        if needs_me_only:
            rows = [r for r in rows if PullRequestStatus(r.status).needs_you]
        last = max((r.checked_at for r in tracked(db)), default=None)
        note = None
        if last is None:
            note = f"No pull requests tracked yet. The user can run `{BRAND.cli} prs`."
        elif not rows:
            note = "Nothing here needs the user right now."
        return MyPrsOut(pull_requests=[pull_out(r) for r in rows], last_checked=last, note=note)

    return server
