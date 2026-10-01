"""Command-line interface.

M0 ships ``--version``, ``demo`` and ``doctor``. The other commands in the
brief (init, watch, sync, find, explain, prs, digest, export) arrive in M1-M3.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from issueradar import __version__
from issueradar.brand import BRAND
from issueradar.config import ConfigError, load_settings
from issueradar.demo import load_demo
from issueradar.models import level_dots

app = typer.Typer(
    name=BRAND.cli,
    help=f"{BRAND.name}: {BRAND.tagline}",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

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


@app.command()
def doctor(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Your config file, if you have one."),
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

    if os.environ.get(TOKEN_ENV):
        warn(f"{TOKEN_ENV} is set. Checking it against GitHub arrives in milestone M1.")
    else:
        warn(
            f"{TOKEN_ENV} is not set. That is fine for `{BRAND.cli} demo`. "
            "See docs/human-tasks.md to create a read-only token."
        )

    if problems:
        console.print(f"\n{problems} problem(s) found.")
        raise typer.Exit(code=1)
    console.print("\nAll checks passed.")


if __name__ == "__main__":  # pragma: no cover
    app()
