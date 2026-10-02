"""Command-line interface.

Shipped so far: ``--version``, ``demo``, ``doctor``, ``watch`` and ``sync``.
The other commands in the brief (init, find, explain, prs, digest, export)
arrive in M2 and M3.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from rich.console import Console
from rich.table import Table

from issueradar import __version__
from issueradar.brand import BRAND
from issueradar.config import ConfigError, Settings, load_settings
from issueradar.demo import load_demo
from issueradar.github import GitHubClient, GitHubError, token_from_env
from issueradar.models import level_dots
from issueradar.storage import Database, open_database, resolve_database_url
from issueradar.storage.etag_cache import SqlEtagCache
from issueradar.sync import SyncService, watchlist
from issueradar.sync.etag_check import measure

T = TypeVar("T")

app = typer.Typer(
    name=BRAND.cli,
    help=f"{BRAND.name}: {BRAND.tagline}",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
watch_app = typer.Typer(help="Choose the repositories to watch.", no_args_is_help=True)
app.add_typer(watch_app, name="watch")

TOKEN_ENV = BRAND.env("GITHUB_TOKEN")
MIN_PYTHON = (3, 11)


def _ensure_utf8_output() -> None:
    """Level dots are Unicode. Redirected output on Windows defaults to a legacy
    code page, so switch stdout to UTF-8 rather than crash."""
    stream = sys.stdout
    encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
    if encoding != "utf8" and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"{BRAND.name} {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show the version."
        ),
    ] = False,
) -> None:
    """Find open-source issues you can actually work on."""
    _ensure_utf8_output()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def demo(
    limit: Annotated[int, typer.Option(min=1, help="How many free issues to show.")] = 5,
) -> None:
    """Show the radar using bundled demo data. Needs no token and makes no API calls."""
    data = load_demo()
    free = [i for i in data.issues if i.availability.rankable]
    hidden = len(data.issues) - len(free)

    console.print(f"[bold]{BRAND.name}[/bold]  [reverse] {data.label} [/reverse]")
    console.print(f"[dim]{data.note}[/dim]\n")

    table = Table(title="Free for you", title_justify="left", show_lines=False)
    table.add_column("Level", no_wrap=True)
    table.add_column("Repo", style="cyan", no_wrap=True)
    table.add_column("Issue")
    table.add_column("Status", no_wrap=True)
    table.add_column("Why it is here", style="dim")
    for issue in free[:limit]:
        table.add_row(
            level_dots(issue.tier),
            f"{issue.repo}#{issue.number}",
            issue.title,
            f"[black on yellow] {issue.availability.label} [/]",
            issue.why_here,
        )
    console.print(table)
    console.print(
        f"[dim]{hidden} claimed, in-review or not-ready issues were filtered out.[/dim]\n"
    )

    prs = Table(title="Your pull requests", title_justify="left")
    prs.add_column("PR", no_wrap=True)
    prs.add_column("Status", no_wrap=True)
    prs.add_column("What needs you")
    for pr in data.pull_requests:
        prs.add_row(f"{pr.repo}#{pr.number}", pr.status.label, pr.needs_you)
    console.print(prs)
    console.print(f"\n[dim]API budget used: 0 requests ({data.label.lower()}, no API calls).[/dim]")


ConfigOption = Annotated[
    Path | None, typer.Option("--config", "-c", help="Your config file, if you have one.")
]


def _settings(config: Path | None) -> Settings:
    try:
        return load_settings(config)
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc


def _database(settings: Settings) -> Database:
    return open_database(resolve_database_url(settings))


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    async def runner() -> T:
        return await coro_fn()

    return asyncio.run(runner())


def _client(settings: Settings, db: Database | None) -> GitHubClient:
    token, _source = token_from_env(os.environ)
    cache = SqlEtagCache(db.sessions) if db is not None else None
    return GitHubClient(settings.github, token, cache=cache)


@app.command()
def doctor(
    config: ConfigOption = None,
    measure_etag: Annotated[
        str | None,
        typer.Option(
            "--measure-etag",
            metavar="OWNER/REPO",
            help="Measure whether a 304 response costs rate limit (makes 3 API requests).",
        ),
    ] = None,
) -> None:
    """Check that this installation is ready to run."""
    problems = 0

    def ok(message: str) -> None:
        console.print(f"[green]ok[/green]    {message}")

    def warn(message: str) -> None:
        console.print(f"[yellow]note[/yellow]  {message}")

    def fail(message: str) -> None:
        nonlocal problems
        problems += 1
        console.print(f"[red]fix[/red]   {message}")

    version = sys.version_info
    if version[:2] >= MIN_PYTHON:
        ok(f"Python {version.major}.{version.minor}.{version.micro}")
    else:
        fail(f"Python {version.major}.{version.minor} is too old; install 3.11 or newer.")

    settings: Settings | None = None
    try:
        settings = load_settings(config)
        ok(f"Config is valid ({config or 'built-in defaults'})")
        search = settings.github.search
        ok(
            "GitHub limits loaded: "
            f"REST {settings.github.rest.authenticated_per_hour}/h, "
            f"GraphQL {settings.github.graphql.points_per_hour} points/h, "
            f"search {search.requests_per_minute}/min"
        )
    except ConfigError as exc:
        fail(str(exc))

    try:
        data = load_demo()
        ok(f"{data.label} loads ({len(data.repos)} repos, {len(data.issues)} issues)")
    except Exception as exc:  # report any fixture problem instead of a traceback
        fail(f"Demo fixtures failed to load: {exc}")

    if settings is not None:
        try:
            db = _database(settings)
            ok(f"Database is ready ({db.url})")
        except Exception as exc:  # any driver or migration error
            fail(f"Database could not be opened: {exc}")

    token, source = token_from_env(os.environ)
    if token:
        ok(f"Token found in {source}")
        if source == "GITHUB_TOKEN":
            warn("GITHUB_TOKEN in Actions is limited to 1,000 requests per hour per repo.")
        if settings is not None:
            problems += _check_token(settings, token)
    else:
        warn(
            f"{TOKEN_ENV} is not set. That is fine for `{BRAND.cli} demo`; `sync` needs it "
            "for a useful budget. See docs/human-tasks.md to create a read-only token."
        )

    if measure_etag and settings is not None:
        _measure_etag(settings, measure_etag)

    if problems:
        console.print(f"\n{problems} problem(s) found.")
        raise typer.Exit(code=1)
    console.print("\nAll checks passed.")


def _check_token(settings: Settings, token: str) -> int:
    async def check() -> int:
        async with GitHubClient(settings.github, token) as client:
            # GET /rate_limit does not count against the primary rate limit.
            response = await client.get("/rate_limit", conditional=False)
        resources = response.data.get("resources", {})
        for name in ("core", "search", "graphql"):
            item = resources.get(name)
            if item:
                console.print(
                    f"[green]ok[/green]    {name}: {item['remaining']}/{item['limit']} remaining"
                )
        return 0

    try:
        return _run(check)
    except GitHubError as exc:
        console.print(f"[red]fix[/red]   The token did not work: {exc}")
        return 1


def _measure_etag(settings: Settings, repo: str) -> None:
    async def run() -> None:
        token, _ = token_from_env(os.environ)
        async with GitHubClient(settings.github, token) as client:
            result = await measure(client, watchlist.normalise_repo(repo))
        console.print(f"\nConditional request check on {result.url}")
        console.print(f"  authenticated: {result.authenticated}")
        console.print(
            f"  statuses: {result.statuses[0]}, {result.statuses[1]}, {result.statuses[2]}"
        )
        console.print(f"  x-ratelimit-used after each: {result.used}")
        console.print(f"  {result.verdict()}")

    try:
        _run(run)
    except (GitHubError, watchlist.WatchlistError) as exc:
        console.print(f"[red]fix[/red]   Could not measure: {exc}")


@watch_app.command("add")
def watch_add(
    repos: Annotated[list[str], typer.Argument(help="owner/name or a GitHub URL")],
    config: ConfigOption = None,
) -> None:
    """Start watching one or more repositories."""
    db = _database(_settings(config))
    for repo in repos:
        try:
            name, added = watchlist.add(db, repo)
        except watchlist.WatchlistError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=2) from exc
        console.print(f"Watching {name}." if added else f"Already watching {name}.")


@watch_app.command("remove")
def watch_remove(
    repos: Annotated[list[str], typer.Argument(help="owner/name or a GitHub URL")],
    config: ConfigOption = None,
) -> None:
    """Stop watching repositories. Data already fetched stays until the next cleanup."""
    db = _database(_settings(config))
    for repo in repos:
        try:
            removed = watchlist.remove(db, repo)
        except watchlist.WatchlistError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=2) from exc
        console.print(f"Stopped watching {repo}." if removed else f"{repo} was not on the list.")


@watch_app.command("list")
def watch_list(config: ConfigOption = None) -> None:
    """Show the watched repositories."""
    db = _database(_settings(config))
    names = watchlist.list_watched(db)
    if not names:
        console.print(f"Nothing watched yet. Add one with `{BRAND.cli} watch add owner/name`.")
        return
    for name in names:
        console.print(name)


@app.command()
def sync(config: ConfigOption = None) -> None:
    """Fetch the watched repositories, their open issues and open pull requests."""
    settings = _settings(config)
    db = _database(settings)
    if not watchlist.list_watched(db):
        console.print(f"Nothing to sync. Add a repo first: `{BRAND.cli} watch add owner/name`.")
        raise typer.Exit(code=1)
    token, _ = token_from_env(os.environ)
    if not token:
        console.print(
            f"[yellow]note[/yellow]  No token set ({TOKEN_ENV}). Unauthenticated requests "
            "are limited to 60 per hour, so only a small watchlist will finish."
        )

    async def run():  # type: ignore[no-untyped-def]
        async with _client(settings, db) as client:
            return await SyncService(db, client, settings).run()

    report = _run(run)
    if report.resumed:
        console.print("Continuing the sync that stopped last time.")
    table = Table(title="Sync", title_justify="left")
    table.add_column("Repo", style="cyan", no_wrap=True)
    table.add_column("Result")
    table.add_column("Open issues", justify="right")
    table.add_column("Open PRs", justify="right")
    table.add_column("Notes", style="dim")
    for outcome in report.outcomes:
        table.add_row(
            outcome.full_name,
            outcome.status,
            str(outcome.open_issues),
            str(outcome.open_pull_requests),
            outcome.note or "",
        )
    console.print(table)
    if report.message:
        console.print(f"[yellow]{report.message}[/yellow]")
    if report.budget is not None:
        console.print(f"[dim]{report.budget.line()}[/dim]")
    if report.status != "completed":
        raise typer.Exit(code=3)


if __name__ == "__main__":  # pragma: no cover
    app()
