from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from fake_github import FakeGitHub
from issueradar.cli import app
from issueradar.config import Settings
from issueradar.delivery.http import DeliveryError
from issueradar.digest import DigestBuilder, mark, record_sent, render
from issueradar.digest import channels as ch
from issueradar.digest.builder import issue_key
from issueradar.digest.model import Digest, PullItem
from issueradar.engine.rules import load_rules
from issueradar.radar import Radar
from issueradar.storage import Database
from scenario import REPO


def builder(
    db: Database, settings: Settings, now: datetime | None = None, **kw: Any
) -> DigestBuilder:
    clock = (lambda: now) if now else None
    radar = Radar(db, settings, load_rules(), None, **({"clock": clock} if clock else {}))
    return DigestBuilder(db, settings, radar, **({"clock": clock} if clock else {}), **kw)


async def test_first_digest_lists_free_issues(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    digest = builder(db, settings).build()
    keys = {i.key for i in digest.free}
    assert keys == {issue_key(REPO, n) for n in (1, 3, 4)}
    assert all(i.state in ("Free", "Likely free") for i in digest.free)
    assert digest.quiet_message is None


async def test_second_digest_after_sending_is_empty(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    first = builder(db, settings).build()
    record_sent(db, first, ["markdown"])
    second = builder(db, settings).build()
    assert second.is_empty
    assert second.quiet_message is None  # already sent today: nothing at all


async def test_quiet_message_when_nothing_new_and_nothing_sent_today(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    first = builder(db, settings).build()
    record_sent(db, first, ["markdown"])
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    digest = builder(db, settings, now=tomorrow).build()
    assert digest.free == [] and digest.quiet_message


async def test_changed_item_comes_back(
    db: Database, settings: Settings, synced: FakeGitHub
) -> None:
    first = builder(db, settings).build()
    record_sent(db, first, ["markdown"])
    from sqlalchemy import update

    from issueradar.storage.models import Issue

    with db.sessions.begin() as session:
        session.execute(
            update(Issue).where(Issue.number == 1).values(title="Fix typo in the README file")
        )
    again = builder(db, settings).build()
    assert [i.number for i in again.free] == [1]


async def test_dismiss_and_snooze(db: Database, settings: Settings, synced: FakeGitHub) -> None:
    mark(db, issue_key(REPO, 1), "dismissed")
    mark(db, issue_key(REPO, 4), "snoozed", until=datetime.now(UTC) + timedelta(days=3))
    keys = {i.key for i in builder(db, settings).build().free}
    assert keys == {issue_key(REPO, 3)}
    later = datetime.now(UTC) + timedelta(days=4)
    keys = {i.key for i in builder(db, settings, now=later).build().free}
    assert issue_key(REPO, 4) in keys and issue_key(REPO, 1) not in keys


async def test_pull_items_and_alerts(db: Database, settings: Settings, synced: FakeGitHub) -> None:
    pr = PullItem(
        "pr:a/b#9", "a/b", 9, "Fix it", None, "Changes requested", "2 comments wait", "h1"
    )
    far = datetime.now(UTC) + timedelta(days=90)  # the repo was pushed "yesterday"
    digest = builder(db, settings, now=far, pulls=lambda: [pr]).build()
    assert digest.pulls == [pr]
    assert any("no push for" in a.text for a in digest.alerts)


def sample_digest() -> Digest:
    from issueradar.digest.model import Alert, IssueItem

    return Digest(
        created_at=datetime(2026, 10, 2, 7, 0, tzinfo=UTC),
        free=[
            IssueItem(
                "issue:o/r#1",
                "o/r",
                1,
                "Fix <typo>",
                "https://github.com/o/r/issues/1",
                "beginner",
                "●○○",
                "Free",
                "Healthy repo",
                "x",
            )
        ],
        pulls=[
            PullItem(
                "pr:o/r#2",
                "o/r",
                2,
                "My PR",
                None,
                "Stale",
                "Quiet for 9 days",
                "y",
                nudge="Hi, just checking in.",
            )
        ],
        alerts=[Alert("repo:o/r:quiet", "o/r", "o/r has had no push for 70 days.", "z")],
    )


def test_renderers() -> None:
    d = sample_digest()
    md = render.markdown(d)
    assert "## Free for you" in md and "`●○○`" in md and "Nudge draft" in md
    assert "never comments" in md
    text = render.text(d)
    assert "Your pull requests" in text and "Watchlist alerts" in text
    html = render.html(d)
    assert "Fix &lt;typo&gt;" in html and "#F2B01E" in html


def test_pr_status_is_not_said_twice() -> None:
    def pr(status: str, needs: str) -> PullItem:
        return PullItem("pr:o/r#3", "o/r", 3, "T", None, status, needs, "h")

    d = sample_digest()
    d.pulls[:] = [
        pr("Merged", "Merged. Nothing to do."),
        pr("Waiting for review", "Waiting for a first review. Nothing to do yet."),
        pr("Stale", "Quiet for 9 days"),
    ]
    md = render.markdown(d)
    assert "Merged. Merged." not in md and "T. Merged. Nothing to do." in md
    assert "Waiting for review. Waiting" not in md
    assert "T. Stale. Quiet for 9 days" in md
    assert "o/r#3  Merged. Nothing to do." in render.text(d)


def test_markdown_and_rss_files(tmp_path: Path) -> None:
    d = sample_digest()
    assert "wrote" in ch.MarkdownChannel(tmp_path).send(d)
    assert (tmp_path / "latest.md").read_text("utf-8").startswith("# ")
    rss = ch.RssChannel(tmp_path / "feed.xml", max_items=2, link="")
    for hour in (7, 8, 9):
        rss.send(Digest(created_at=d.created_at.replace(hour=hour), free=d.free))
    items = ET.parse(tmp_path / "feed.xml").getroot().findall("channel/item")  # noqa: S314
    assert len(items) == 2  # max_items
    assert "09:00" in (items[0].findtext("pubDate") or "")  # newest first


def test_email_channel_uses_starttls_and_login() -> None:
    calls: list[str] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int) -> None:
            calls.append(f"connect {host}:{port}")

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, *args: object) -> None:
            calls.append("quit")

        def starttls(self, context: object) -> None:
            calls.append("starttls")

        def login(self, user: str, password: str) -> None:
            calls.append(f"login {user}")

        def send_message(self, message: Any) -> None:
            calls.append(f"send {message['To']} {message.is_multipart()}")

    channel = ch.EmailChannel(
        "smtp.example.com",
        587,
        True,
        "me",
        "me@example.com",
        "me@example.com",
        "pw",
        smtp_factory=FakeSMTP,
    )
    channel.send(sample_digest())
    assert calls == [
        "connect smtp.example.com:587",
        "starttls",
        "login me",
        "send me@example.com True",
        "quit",
    ]


def test_webhooks_split_long_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(ch, "post_json", lambda url, payload: sent.append((url, payload)))
    big = sample_digest()
    big.free = big.free * 60
    ch.WebhookChannel("https://discord.example/hook", "discord").send(big)
    assert len(sent) > 1 and all(len(p["content"]) <= 2000 for _, p in sent)
    sent.clear()
    ch.TelegramChannel("TOKEN", "42").send(sample_digest())
    assert sent[0][0] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert sent[0][1]["chat_id"] == "42"


def test_missing_secret_is_a_clear_error(settings: Settings) -> None:
    cfg = settings.digest.model_copy(
        update={
            "channels": settings.digest.channels.model_copy(
                update={
                    "slack": settings.digest.channels.slack.model_copy(update={"enabled": True})
                }
            )
        }
    )
    with pytest.raises(DeliveryError, match="FIRSTPR_SLACK_WEBHOOK"):
        ch.enabled_channels(cfg, env={})


async def test_digest_send_twice_sends_nothing_new(
    db: Database, synced: FakeGitHub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIRSTPR_DB_URL", db.url)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    first = runner.invoke(app, ["digest", "--send"])
    assert first.exit_code == 0, first.stdout
    assert "markdown: wrote" in first.stdout and "rss: updated" in first.stdout
    feed = (tmp_path / "digests" / "feed.xml").read_text("utf-8")
    second = runner.invoke(app, ["digest", "--send"])
    assert second.exit_code == 0, second.stdout
    assert "Nothing new since the last digest" in second.stdout
    assert (tmp_path / "digests" / "feed.xml").read_text("utf-8") == feed


def test_digest_preview_on_empty_database() -> None:
    result = CliRunner().invoke(app, ["digest", "--format", "markdown"])
    assert result.exit_code == 0, result.stdout
    assert "Quiet day" in result.stdout


def test_dismiss_rejects_bad_link() -> None:
    assert CliRunner().invoke(app, ["dismiss", "not a link"]).exit_code == 2


def test_init_creates_files_once(tmp_path: Path) -> None:
    runner = CliRunner()
    first = runner.invoke(app, ["init", "--folder", str(tmp_path)])
    assert first.exit_code == 0 and (tmp_path / "skills.yaml").exists()
    assert (tmp_path / "firstpr.yaml").exists()
    second = runner.invoke(app, ["init", "--folder", str(tmp_path)])
    assert "already exists" in " ".join(second.stdout.split())
    from issueradar.config import load_settings

    load_settings(tmp_path / "firstpr.yaml")  # the generated config is valid


async def test_export(
    db: Database, synced: FakeGitHub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    monkeypatch.setenv("FIRSTPR_DB_URL", db.url)
    out = tmp_path / "export.json"
    result = CliRunner().invoke(app, ["export", "--out", str(out)])
    assert result.exit_code == 0, result.stdout
    data = json.loads(out.read_text("utf-8"))
    assert data["watchlist"] == [REPO] and len(data["issues"]) == 9


async def test_digest_writes_github_step_summary(
    db: Database, synced: FakeGitHub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIRSTPR_DB_URL", db.url)
    monkeypatch.chdir(tmp_path)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    result = CliRunner().invoke(app, ["digest", "--send"])
    assert result.exit_code == 0, result.stdout
    assert "## Free for you" in summary.read_text("utf-8")

    again = CliRunner().invoke(app, ["digest", "--send"])
    assert again.exit_code == 0, again.stdout
    assert (
        summary.read_text("utf-8")
        .rstrip()
        .endswith("Nothing new since the last digest, so nothing was sent.")
    )


def test_daily_runs_every_step_and_reports_problems() -> None:
    result = CliRunner().invoke(app, ["daily", "--skip-prs"])
    out = " ".join(result.stdout.split())
    assert "Sync" in out and "Digest" in out
    assert result.exit_code == 1  # nothing is watched yet, so sync reports a problem
    assert "Finished with problems in: Sync" in out
