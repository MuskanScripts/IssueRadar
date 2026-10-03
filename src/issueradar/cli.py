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
from platformdirs import user_config_dir
from rich.console import Console
from rich.table import Table

from issueradar import __version__, evaluation
from issueradar.brand import BRAND
from issueradar.config import ConfigError, Settings, load_settings
from issueradar.delivery.http import DeliveryError
from issueradar.demo import load_demo
from issueradar.digest import DigestBuilder, mark, record_sent
from issueradar.digest import render as digest_render
from issueradar.digest.builder import issue_key
from issueradar.digest.channels import enabled_channels
from issueradar.engine import coach
from issueradar.engine.rules import RepoRules, load_packs, load_rules
from issueradar.engine.stack import SkillProfile, load_profile
from issueradar.github import GitHubClient, GitHubError, token_from_env
from issueradar.models import IssueType, Tier, TimeBucket, level_dots
from issueradar.radar import Filters, IssueReport, Radar
from issueradar.storage import Database, open_database, resolve_database_url
from issueradar.storage.etag_cache import SqlEtagCache
from issueradar.sync import SyncService, watchlist
from issueradar.sync.enrich import Enricher
from issueradar.sync.etag_check import measure
from issueradar.sync.single import IssueUrlError, ensure_issue, is_stored, parse_issue_ref

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
eval_app = typer.Typer(
    help="Measure the engines against issues you labelled.", no_args_is_help=True
)
app.add_typer(eval_app, name="eval")
pack_app = typer.Typer(help="Starter packs of repositories to watch.", no_args_is_help=True)
app.add_typer(pack_app, name="pack")

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


SkillsOption = Annotated[
    Path | None,
    typer.Option("--skills", help="Your skills.yaml (default: ./skills.yaml if it exists)."),
]


def _config_home() -> Path:
    return Path(user_config_dir(BRAND.cli, appauthor=False))


def _profile(path: Path | None) -> SkillProfile | None:
    candidates = [path] if path else []
    env = os.environ.get(BRAND.env("SKILLS"))
    if env:
        candidates.append(Path(env))
    candidates += [Path("skills.yaml"), _config_home() / "skills.yaml"]
    for candidate in candidates:
        if candidate and candidate.is_file():
            try:
                return load_profile(candidate)
            except Exception as exc:  # show which file is broken and why
                console.print(f"[red]{candidate}: {exc}[/red]")
                raise typer.Exit(code=2) from exc
    if path:
        console.print(f"[red]{path} does not exist.[/red]")
        raise typer.Exit(code=2)
    return None


def _rules() -> dict[str, RepoRules]:
    folder = os.environ.get(BRAND.env("RULES_DIR"))
    return load_rules(Path(folder) if folder else _config_home() / "rules")


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
    rules = _rules()

    async def run():  # type: ignore[no-untyped-def]
        async with _client(settings, db) as client:
            service = SyncService(
                db,
                client,
                settings,
                enricher=Enricher(db, client, settings, rules),
                radar=Radar(db, settings, rules, None),
            )
            return await service.run()

    report = _run(run)
    if report.resumed:
        console.print("Continuing the sync that stopped last time.")
    table = Table(title="Sync", title_justify="left")
    table.add_column("Repo", style="cyan", no_wrap=True)
    table.add_column("Result")
    table.add_column("Open issues", justify="right")
    table.add_column("Open PRs", justify="right")
    table.add_column("Checked", justify="right")
    table.add_column("Health", justify="right")
    table.add_column("Notes", style="dim")
    for outcome in report.outcomes:
        table.add_row(
            outcome.full_name,
            outcome.status,
            str(outcome.open_issues),
            str(outcome.open_pull_requests),
            str(outcome.finalists),
            "" if outcome.health is None else str(outcome.health),
            outcome.note or "",
        )
    console.print(table)
    if report.message:
        console.print(f"[yellow]{report.message}[/yellow]")
    if report.budget is not None:
        console.print(f"[dim]{report.budget.line()}[/dim]")
    if report.status != "completed":
        raise typer.Exit(code=3)


def _free_pill(report: IssueReport) -> str:
    state = report.availability.state
    if state.rankable:
        return f"[black on yellow] {state.label} [/]"
    return state.label


@app.command()
def explain(
    issue: Annotated[str, typer.Argument(help="https://github.com/owner/repo/issues/123")],
    config: ConfigOption = None,
    skills: SkillsOption = None,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Fetch the issue again even if it is stored.")
    ] = False,
) -> None:
    """Explain why an issue is (or isn't) free, its level, and its repo's health."""
    settings = _settings(config)
    db = _database(settings)
    rules = _rules()
    try:
        repo, number = parse_issue_ref(issue)
    except IssueUrlError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    if refresh or not is_stored(db, repo, number):

        async def fetch() -> str:
            async with _client(settings, db) as client:
                name = await ensure_issue(db, client, settings, rules, repo, number)
                console.print(f"[dim]{client.budget.summary().line()}[/dim]")
                return name

        try:
            repo = _run(fetch)
        except (GitHubError, IssueUrlError) as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

    radar = Radar(db, settings, rules, _profile(skills))
    report = radar.report_for(repo, number)
    if report is None:
        console.print(f"[red]{repo}#{number} is not in the database.[/red]")
        raise typer.Exit(code=1)
    _print_report(report)


def _print_report(report: IssueReport) -> None:
    diff = report.difficulty
    console.print(f"\n[bold]{report.title}[/bold]")
    console.print(f"[cyan]{report.repo}#{report.number}[/cyan]  {report.url or ''}\n")

    console.print(f"[bold]Is it free?[/bold]  {_free_pill(report)}")
    for reason in report.availability.reasons:
        console.print(f"  - {reason}")

    console.print(
        f"\n[bold]Level[/bold]  {level_dots(diff.tier)} {diff.tier.label}, score {diff.score}, "
        f"{diff.time_bucket.label.lower()}, {diff.issue_type.value}"
    )
    for reason in diff.reasons:
        console.print(f"  - {reason}")

    health = "not measured yet" if report.health_score is None else str(report.health_score)
    console.print(f"\n[bold]Repo health[/bold]  {health}")
    for line in report.health_reasons:
        console.print(f"  - {line}")
    flag_reasons = report.flags.get("reasons") or []
    if isinstance(flag_reasons, list):
        for reason in flag_reasons:
            console.print(f"  - {reason}")
    if report.repo_notes:
        console.print(f"  - Repo notes: {report.repo_notes}")
    console.print("\n[bold]Before you start[/bold]")
    for line in coach.checklist(
        report.repo,
        report.flags,
        discussion_first=report.difficulty.discussion_first,
        open_unreviewed_prs=_open_unreviewed(),
    ):
        console.print(f"  [ ] {line}", markup=False)

    console.print("\n[bold]Your stack[/bold]")
    for reason in report.stack.reasons:
        console.print(f"  - {reason}")
    if report.rank:
        console.print(f"\n[bold]Rank[/bold]  {report.rank.score:.2f}: {report.rank.why}")
    else:
        console.print("\n[bold]Rank[/bold]  not ranked (only free issues are ranked)")


def _choices(values: list[str] | None, kind: type, what: str) -> list:  # type: ignore[type-arg]
    picked = []
    for value in values or []:
        try:
            picked.append(kind(value.lower().replace(" ", "_")))
        except ValueError as exc:
            allowed = ", ".join(m.value for m in kind)  # type: ignore[attr-defined]
            console.print(f"[red]Unknown {what} '{value}'. Use one of: {allowed}.[/red]")
            raise typer.Exit(code=2) from exc
    return picked


@app.command()
def find(
    config: ConfigOption = None,
    skills: SkillsOption = None,
    level: Annotated[
        list[str] | None, typer.Option("--level", help="beginner, intermediate or pro")
    ] = None,
    language: Annotated[list[str] | None, typer.Option("--language")] = None,
    framework: Annotated[list[str] | None, typer.Option("--framework")] = None,
    domain: Annotated[list[str] | None, typer.Option("--domain")] = None,
    issue_type: Annotated[
        list[str] | None, typer.Option("--type", help="docs, tests, bug, feature, refactor, ci")
    ] = None,
    time: Annotated[
        list[str] | None,
        typer.Option("--time", help="under_an_hour, half_a_day, a_weekend, a_week_or_more"),
    ] = None,
    min_health: Annotated[int | None, typer.Option("--min-health")] = None,
    min_stars: Annotated[int | None, typer.Option("--min-stars")] = None,
    max_stars: Annotated[int | None, typer.Option("--max-stars")] = None,
    updated_within: Annotated[int | None, typer.Option("--updated-within", help="days")] = None,
    max_comments: Annotated[
        int | None, typer.Option("--max-comments", help="lower means less competition")
    ] = None,
    no_discussion: Annotated[
        bool, typer.Option("--no-discussion", help="hide issues that need a proposal first")
    ] = False,
    repo: Annotated[list[str] | None, typer.Option("--repo")] = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 20,
) -> None:
    """List free issues from synced repos, best match first."""
    settings = _settings(config)
    db = _database(settings)
    radar = Radar(db, settings, _rules(), _profile(skills))
    filters = Filters(
        tiers=_choices(level, Tier, "level"),
        languages=language or [],
        frameworks=framework or [],
        domains=domain or [],
        issue_types=_choices(issue_type, IssueType, "type"),
        times=_choices(time, TimeBucket, "time"),
        min_health=min_health,
        min_stars=min_stars,
        max_stars=max_stars,
        max_age_days=updated_within,
        max_comments=max_comments,
        exclude_discussion_first=no_discussion,
        repos=repo or [],
    )
    results = radar.find(filters, limit)
    if not results:
        console.print(
            "Nothing matches right now. Try fewer filters, or watch more repos with "
            f"`{BRAND.cli} watch add` and run `{BRAND.cli} sync`."
        )
        return
    table = Table(title="Free for you", title_justify="left")
    table.add_column("Level", no_wrap=True)
    table.add_column("Issue", style="cyan", no_wrap=True)
    table.add_column("Title")
    table.add_column("Status", no_wrap=True)
    table.add_column("Rank", justify="right")
    table.add_column("Why it is here", style="dim")
    for item in results:
        table.add_row(
            level_dots(item.difficulty.tier),
            f"{item.repo}#{item.number}",
            item.title,
            _free_pill(item),
            f"{item.rank.score:.2f}" if item.rank else "",
            item.rank.why if item.rank else "",
        )
    console.print(table)
    console.print(f"[dim]Explain one with `{BRAND.cli} explain <url>`.[/dim]")


@eval_app.command("sample")
def eval_sample(
    out: Annotated[Path, typer.Option("--out")] = Path("eval/labels.csv"),
    per_repo: Annotated[int, typer.Option("--per-repo", min=1)] = 10,
    repo: Annotated[list[str] | None, typer.Option("--repo")] = None,
    config: ConfigOption = None,
) -> None:
    """Write a labelling sheet of open issues from synced repos."""
    settings = _settings(config)
    radar = Radar(_database(settings), settings, _rules(), None)
    if out.exists():
        console.print(f"[red]{out} already exists; pick another --out so labels aren't lost.[/red]")
        raise typer.Exit(code=2)
    count = evaluation.sample(radar, out, per_repo=per_repo, repos=repo)
    console.print(f"Wrote {count} issues to {out}. Label them as described in eval/README.md.")


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


@eval_app.command("run")
def eval_run(
    labels: Annotated[Path, typer.Argument(help="Your labelled CSV")],
    json_out: Annotated[Path | None, typer.Option("--json", help="Also write results here")] = None,
    config: ConfigOption = None,
) -> None:
    """Print precision and recall for FREE detection and tier accuracy."""
    if not labels.is_file():
        console.print(f"[red]{labels} does not exist.[/red]")
        raise typer.Exit(code=2)
    settings = _settings(config)
    radar = Radar(_database(settings), settings, _rules(), None)
    report = evaluation.run(radar, labels)
    console.print(
        f"Labelled rows: {report.rows} (free: {report.labelled_free}, tier: {report.labelled_tier})"
    )
    if report.missing:
        console.print(
            f"[yellow]{len(report.missing)} not in the database (skipped); run "
            f"`{BRAND.cli} explain <url>` on them first.[/yellow]"
        )
    if report.bad_rows:
        console.print(f"[yellow]{len(report.bad_rows)} rows without a valid issue link.[/yellow]")
    for name in ("strict", "lenient"):
        score = getattr(report, name)
        console.print(
            f"FREE detection ({name}): precision {_pct(score.precision)}, "
            f"recall {_pct(score.recall)} (tp {score.tp}, fp {score.fp}, fn {score.fn}, "
            f"tn {score.tn})"
        )
    console.print(
        f"Tier accuracy: {_pct(report.tier_accuracy)} exact, "
        f"{_pct(report.tier_within_one / report.labelled_tier if report.labelled_tier else None)}"
        " within one tier"
    )
    table = Table(title="Tiers (rows: your label, columns: predicted)", title_justify="left")
    table.add_column("")
    for tier in Tier:
        table.add_column(tier.label, justify="right")
    for actual, row in report.tier_confusion.items():
        table.add_row(actual.capitalize(), *(str(row[t.value]) for t in Tier))
    console.print(table)
    if json_out:
        json_out.write_text(report.to_json() + "\n", encoding="utf-8")
        console.print(f"Wrote {json_out}.")


@pack_app.command("list")
def pack_list() -> None:
    """Show the starter packs."""
    for key, pack in load_packs().items():
        status = "verified" if pack.verified else "not verified yet"
        console.print(f"[bold]{key}[/bold]  {pack.name} ({status})")
        console.print(f"  {pack.description}")
        console.print(f"  {', '.join(pack.repos)}")


@pack_app.command("add")
def pack_add(name: str, config: ConfigOption = None) -> None:
    """Watch every repository in a starter pack."""
    packs = load_packs()
    if name not in packs:
        console.print(f"[red]No pack '{name}'. Try `{BRAND.cli} pack list`.[/red]")
        raise typer.Exit(code=2)
    pack = packs[name]
    if not pack.verified:
        console.print(
            f"[yellow]This pack is not verified yet. `{BRAND.cli} pack verify {name}` "
            "checks each repo is active and takes outside contributions.[/yellow]"
        )
    db = _database(_settings(config))
    for repo in pack.repos:
        added_name, added = watchlist.add(db, repo)
        console.print(f"Watching {added_name}." if added else f"Already watching {added_name}.")


@pack_app.command("verify")
def pack_verify(name: str, config: ConfigOption = None) -> None:
    """Check each repo in a pack: active, open to outside PRs, has contributor docs."""
    packs = load_packs()
    if name not in packs:
        console.print(f"[red]No pack '{name}'. Try `{BRAND.cli} pack list`.[/red]")
        raise typer.Exit(code=2)
    settings = _settings(config)
    maintainers = {a.upper() for a in settings.availability.maintainer_associations}

    async def check() -> list[tuple[str, str, str, str]]:
        rows = []
        async with _client(settings, None) as client:
            for repo in packs[name].repos:
                try:
                    data = (await client.get(f"/repos/{repo}")).data
                    pushed = (data.get("pushed_at") or "")[:10]
                    active = "archived" if data.get("archived") else f"last push {pushed}"
                    community = (await client.get(f"/repos/{repo}/community/profile")).data
                    docs = "yes" if (community.get("files") or {}).get("contributing") else "no"
                    closed = (
                        await client.get(
                            f"/repos/{repo}/pulls",
                            params={
                                "state": "closed",
                                "per_page": 100,
                                "sort": "updated",
                                "direction": "desc",
                            },
                        )
                    ).data
                    outside = [
                        p
                        for p in closed
                        if (p.get("author_association") or "").upper() not in maintainers
                        and (p.get("user") or {}).get("type") != "Bot"
                    ]
                    merged = sum(1 for p in outside if p.get("merged_at"))
                    rows.append((repo, active, f"{merged} of {len(outside)} merged", docs))
                except GitHubError as exc:
                    rows.append((repo, f"error: {exc}", "", ""))
        return rows

    table = Table(title=f"Pack {name}", title_justify="left")
    for column in ("Repo", "Active", "Outside PRs (last 100 closed)", "CONTRIBUTING"):
        table.add_column(column)
    for row in _run(check):
        table.add_row(*row)
    console.print(table)
    console.print("[dim]If every repo looks good, set `verified: true` in the pack file.[/dim]")


@app.command()
def digest(
    send: Annotated[
        bool, typer.Option("--send", help="Deliver it and remember what was sent.")
    ] = False,
    fmt: Annotated[
        str, typer.Option("--format", help="Preview format: text, markdown or html")
    ] = "text",
    config: ConfigOption = None,
    skills: SkillsOption = None,
) -> None:
    """Build today's digest. Without --send it is only a preview and nothing is remembered."""
    settings = _settings(config)
    db = _database(settings)
    radar = Radar(db, settings, _rules(), _profile(skills))
    built = DigestBuilder(db, settings, radar, pulls=_pull_items(db, settings)).build()
    if not send:
        renderers = {
            "text": digest_render.text,
            "markdown": digest_render.markdown,
            "html": digest_render.html,
        }
        if fmt not in renderers:
            console.print("[red]--format must be text, markdown or html.[/red]")
            raise typer.Exit(code=2)
        console.print(renderers[fmt](built), markup=False, highlight=False)
        return
    if built.is_empty and not built.quiet_message:
        console.print("Nothing new since the last digest, so nothing was sent.")
        return
    try:
        channels = enabled_channels(settings.digest)
    except DeliveryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    if not channels:
        console.print("[yellow]No channels are switched on in your config.[/yellow]")
        raise typer.Exit(code=2)
    delivered = []
    for channel in channels:
        try:
            console.print(f"{channel.name}: {channel.send(built)}")
            delivered.append(channel.name)
        except Exception as exc:  # one broken channel must not stop the others
            console.print(f"[red]{channel.name}: {exc}[/red]")
    if delivered:
        record_sent(db, built, delivered)
    if len(delivered) < len(channels):
        raise typer.Exit(code=1)


def _open_unreviewed() -> int:
    """Your open PRs still waiting for a first review. Filled in by the PR tracker (M4)."""
    return 0


def _pull_items(db: Database, settings: Settings):  # type: ignore[no-untyped-def]
    """PR items for the digest. Filled in by the PR tracker (M4)."""
    return None


def _item_key(value: str) -> str:
    try:
        repo, number = parse_issue_ref(value)
    except IssueUrlError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    return issue_key(repo, number)


@app.command()
def dismiss(
    issue: Annotated[str, typer.Argument(help="Issue link")], config: ConfigOption = None
) -> None:
    """Never show this issue in a digest again."""
    key = _item_key(issue)
    mark(_database(_settings(config)), key, "dismissed")
    console.print(f"Dismissed {key.removeprefix('issue:')}.")


@app.command()
def snooze(
    issue: Annotated[str, typer.Argument(help="Issue link")],
    days: Annotated[int, typer.Option("--days", min=1)] = 7,
    config: ConfigOption = None,
) -> None:
    """Hide this issue from digests for a while."""
    from datetime import timedelta

    from issueradar.storage.models import utcnow

    key = _item_key(issue)
    until = utcnow() + timedelta(days=days)
    mark(_database(_settings(config)), key, "snoozed", until=until)
    console.print(f"Snoozed {key.removeprefix('issue:')} until {until:%Y-%m-%d}.")


@app.command()
def init(
    folder: Annotated[Path, typer.Option("--folder", help="Where to create the files")] = Path(),
) -> None:
    """Create firstpr.yaml and skills.yaml to edit, and say what to do next."""
    from importlib.resources import files as package_files

    created = []
    targets = {
        f"{BRAND.cli}.yaml": _EXAMPLE_CONFIG,
        "skills.yaml": package_files("issueradar.presets")
        .joinpath("skills.example.yaml")
        .read_text(encoding="utf-8"),
    }
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in targets.items():
        path = folder / name
        if path.exists():
            console.print(f"{path} already exists; left it as it is.")
            continue
        path.write_text(text, encoding="utf-8")
        created.append(path)
        console.print(f"Created {path}.")
    console.print(
        "\nNext steps:\n"
        "  1. Edit skills.yaml so it matches you.\n"
        f"  2. Set {TOKEN_ENV} to a read-only token (see docs/human-tasks.md).\n"
        f"  3. {BRAND.cli} pack list, then {BRAND.cli} pack add <name> or "
        f"{BRAND.cli} watch add owner/repo\n"
        f"  4. {BRAND.cli} sync, then {BRAND.cli} find or {BRAND.cli} digest"
    )


_EXAMPLE_CONFIG = """# Your settings. Anything left out uses the defaults
# (src/issueradar/config/defaults.yaml).

digest:
  top_n: 5
  channels:
    markdown:
      enabled: true
    rss:
      enabled: true
    # email:
    #   enabled: true
    #   smtp_host: smtp.example.com
    #   username: you@example.com
    #   sender: you@example.com
    #   recipient: you@example.com
    #   (password goes in the FIRSTPR_SMTP_PASSWORD environment variable)

availability:
  stale_claim_days: 14

pull_requests:
  stale_days: 7
"""


@app.command()
def export(
    out: Annotated[
        Path | None, typer.Option("--out", help="File to write (default: print)")
    ] = None,
    config: ConfigOption = None,
    skills: SkillsOption = None,
) -> None:
    """Export your watchlist and the scored open issues as JSON."""
    import json

    settings = _settings(config)
    db = _database(settings)
    radar = Radar(db, settings, _rules(), _profile(skills))
    filters = Filters(include_unavailable=True)
    data = {
        "watchlist": watchlist.list_watched(db),
        "issues": [
            {
                "repo": r.repo,
                "number": r.number,
                "title": r.title,
                "url": r.url,
                "availability": r.availability.state.value,
                "availability_reasons": [str(x) for x in r.availability.reasons],
                "tier": r.difficulty.tier.value,
                "difficulty_score": r.difficulty.score,
                "time": r.difficulty.time_bucket.value,
                "health": r.health_score,
                "rank": r.rank.score if r.rank else None,
            }
            for r in radar.find(filters)
        ],
    }
    text = json.dumps(data, indent=2)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
        console.print(f"Wrote {len(data['issues'])} issues to {out}.")  # type: ignore[arg-type]
    else:
        console.print(text, markup=False, highlight=False)


if __name__ == "__main__":  # pragma: no cover
    app()
