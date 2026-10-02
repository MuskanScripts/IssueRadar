"""Delivery channels. RSS and Markdown need no setup; the rest are off until configured.

Secrets (SMTP password, bot token, webhook URLs) are read from environment
variables named in config, never from the config file itself.
"""

from __future__ import annotations

import os
import smtplib
import ssl
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Protocol

from issueradar.brand import BRAND
from issueradar.config.settings import DigestSettings
from issueradar.delivery.http import DeliveryError, post_json
from issueradar.digest import render
from issueradar.digest.model import Digest

TELEGRAM_LIMIT = 4000  # Telegram allows 4096 characters per message
DISCORD_LIMIT = 1900  # Discord allows 2000


class Channel(Protocol):
    name: str

    def send(self, digest: Digest) -> str: ...


def _secret(env: Mapping[str, str], name: str, channel: str) -> str:
    value = env.get(name, "")
    if not value:
        raise DeliveryError(f"{channel}: set the {name} environment variable first.")
    return value


@dataclass
class MarkdownChannel:
    folder: Path
    name: str = "markdown"

    def send(self, digest: Digest) -> str:
        self.folder.mkdir(parents=True, exist_ok=True)
        text = render.markdown(digest)
        dated = self.folder / f"{digest.created_at:%Y-%m-%d}.md"
        dated.write_text(text, encoding="utf-8")
        (self.folder / "latest.md").write_text(text, encoding="utf-8")
        return f"wrote {dated}"


@dataclass
class RssChannel:
    path: Path
    max_items: int
    link: str
    name: str = "rss"

    def send(self, digest: Digest) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            tree = ET.parse(self.path)  # noqa: S314 (our own file)
            channel = tree.getroot().find("channel")
        else:
            channel = None
        if channel is None:
            root = ET.Element("rss", version="2.0")
            channel = ET.SubElement(root, "channel")
            ET.SubElement(channel, "title").text = f"{BRAND.name} digest"
            ET.SubElement(channel, "link").text = self.link or BRAND.repository
            ET.SubElement(channel, "description").text = BRAND.tagline
            tree = ET.ElementTree(root)
        item = ET.Element("item")
        ET.SubElement(item, "title").text = digest.title
        ET.SubElement(
            item, "guid", isPermaLink="false"
        ).text = f"{BRAND.cli}-{digest.created_at.isoformat()}"
        ET.SubElement(item, "pubDate").text = format_datetime(digest.created_at)
        ET.SubElement(item, "description").text = render.html(digest)
        if self.link:
            ET.SubElement(item, "link").text = self.link
        existing = channel.findall("item")
        first = existing[0] if existing else None
        if first is not None:
            channel.insert(list(channel).index(first), item)
        else:
            channel.append(item)
        for old in channel.findall("item")[self.max_items :]:
            channel.remove(old)
        ET.indent(tree)
        tree.write(self.path, encoding="utf-8", xml_declaration=True)
        return f"updated {self.path}"


@dataclass
class EmailChannel:
    host: str
    port: int
    starttls: bool
    username: str
    sender: str
    recipient: str
    password: str
    name: str = "email"
    smtp_factory: Callable[[str, int], Any] = smtplib.SMTP

    def send(self, digest: Digest) -> str:
        message = EmailMessage()
        message["Subject"] = f"{BRAND.name}: {digest.title}"
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(render.text(digest))
        message.add_alternative(render.html(digest), subtype="html")
        with self.smtp_factory(self.host, self.port) as smtp:
            if self.starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)
        return f"sent to {self.recipient}"


def _chunks(text: str, limit: int) -> list[str]:
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > limit and current:
            parts.append(current)
            current = ""
        current += line[:limit]
    if current:
        parts.append(current)
    return parts


@dataclass
class TelegramChannel:
    token: str
    chat_id: str
    name: str = "telegram"

    def send(self, digest: Digest) -> str:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        parts = _chunks(render.text(digest), TELEGRAM_LIMIT)
        for part in parts:
            post_json(
                url, {"chat_id": self.chat_id, "text": part, "disable_web_page_preview": True}
            )
        return f"sent {len(parts)} message(s)"


@dataclass
class WebhookChannel:
    url: str
    name: str

    def send(self, digest: Digest) -> str:
        parts = _chunks(render.markdown(digest), DISCORD_LIMIT if self.name == "discord" else 3000)
        key = "content" if self.name == "discord" else "text"
        for part in parts:
            post_json(self.url, {key: part})
        return f"sent {len(parts)} message(s)"


def enabled_channels(
    settings: DigestSettings, env: Mapping[str, str] | None = None, base: Path | None = None
) -> list[Channel]:
    """Build the channels switched on in config. Raises DeliveryError on missing secrets."""
    env = dict(os.environ) if env is None else env
    folder = (base or Path.cwd()) / settings.output_folder
    cfg = settings.channels
    channels: list[Channel] = []
    if cfg.markdown.enabled:
        channels.append(MarkdownChannel(folder))
    if cfg.rss.enabled:
        channels.append(RssChannel(folder / "feed.xml", cfg.rss.max_items, cfg.rss.link))
    if cfg.email.enabled:
        e = cfg.email
        if not (e.smtp_host and e.sender and e.recipient):
            raise DeliveryError("email: set smtp_host, sender and recipient in your config.")
        password = _secret(env, e.password_env, "email") if e.username else ""
        channels.append(
            EmailChannel(
                e.smtp_host, e.smtp_port, e.starttls, e.username, e.sender, e.recipient, password
            )
        )
    if cfg.telegram.enabled:
        if not cfg.telegram.chat_id:
            raise DeliveryError("telegram: set chat_id in your config.")
        channels.append(
            TelegramChannel(_secret(env, cfg.telegram.token_env, "telegram"), cfg.telegram.chat_id)
        )
    if cfg.discord.enabled:
        channels.append(WebhookChannel(_secret(env, cfg.discord.webhook_env, "discord"), "discord"))
    if cfg.slack.enabled:
        channels.append(WebhookChannel(_secret(env, cfg.slack.webhook_env, "slack"), "slack"))
    return channels
