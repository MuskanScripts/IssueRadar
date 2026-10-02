"""Render a digest as Markdown, plain text or HTML. Sentence case, no emoji."""

from __future__ import annotations

from html import escape

from issueradar.brand import BRAND
from issueradar.digest.model import Digest, IssueItem


def _issue_md(item: IssueItem) -> str:
    link = f"[{item.title}]({item.url})" if item.url else item.title
    return f"- `{item.dots}` **{item.repo}#{item.number}** {link}. {item.state}. {item.why}"


def markdown(digest: Digest) -> str:
    lines = [f"# {BRAND.name}: {digest.title}", ""]
    if digest.quiet_message:
        lines += [digest.quiet_message, ""]
    if digest.free:
        lines += ["## Free for you", ""] + [_issue_md(i) for i in digest.free] + [""]
    if digest.pulls:
        lines += ["## Your pull requests", ""]
        for pr in digest.pulls:
            link = f"[{pr.title}]({pr.url})" if pr.url else pr.title
            lines.append(f"- **{pr.repo}#{pr.number}** {link}. {pr.status}. {pr.needs_you}")
            if pr.nudge:
                lines.append(f'  - Nudge draft (copy it if you want to send it): "{pr.nudge}"')
        lines.append("")
    if digest.new_since:
        lines += ["## New since yesterday", ""] + [_issue_md(i) for i in digest.new_since] + [""]
    if digest.alerts:
        lines += ["## Watchlist alerts", ""] + [f"- {a.text}" for a in digest.alerts] + [""]
    lines.append(f"_{BRAND.name} only reads from GitHub. It never comments or opens PRs for you._")
    return "\n".join(lines).rstrip() + "\n"


def text(digest: Digest) -> str:
    lines = [f"{BRAND.name}: {digest.title}", ""]
    if digest.quiet_message:
        lines += [digest.quiet_message, ""]

    def issues(title: str, items: list[IssueItem]) -> None:
        if items:
            lines.append(title)
            for i in items:
                lines.append(f"  {i.dots}  {i.repo}#{i.number}  {i.title}")
                lines.append(f"       {i.state}. {i.why} {i.url or ''}".rstrip())
            lines.append("")

    issues("Free for you", digest.free)
    if digest.pulls:
        lines.append("Your pull requests")
        for pr in digest.pulls:
            lines.append(f"  {pr.repo}#{pr.number}  {pr.status}: {pr.needs_you}")
            if pr.nudge:
                lines.append(f'       Nudge draft: "{pr.nudge}"')
        lines.append("")
    issues("New since yesterday", digest.new_since)
    if digest.alerts:
        lines += ["Watchlist alerts"] + [f"  {a.text}" for a in digest.alerts] + [""]
    return "\n".join(lines).rstrip() + "\n"


# Colours from the design tokens (light theme), inlined because email clients
# ignore stylesheets.
INK, MUTED, RULE, GROUND, AMBER, ACTION = (
    "#0E1B2C",
    "#4A5B6B",
    "#CBD5DB",
    "#F1F4F5",
    "#F2B01E",
    "#2455F4",
)


def html(digest: Digest) -> str:
    def section(title: str, rows: list[str]) -> str:
        if not rows:
            return ""
        return (
            f'<h2 style="font-size:18px;margin:24px 0 8px;color:{INK}">{escape(title)}</h2>'
            f'<ul style="list-style:none;padding:0;margin:0">{"".join(rows)}</ul>'
        )

    def issue(i: IssueItem) -> str:
        title = escape(i.title)
        link = f'<a href="{escape(i.url)}" style="color:{ACTION}">{title}</a>' if i.url else title
        pill = (
            f'<span style="background:{AMBER};color:{INK};border-radius:999px;'
            f'padding:1px 8px;font-size:12px;font-weight:600">{escape(i.state)}</span>'
        )
        return (
            f'<li style="padding:10px 0;border-bottom:1px solid {RULE}">'
            f'<span style="font-family:monospace;color:{INK}">{i.dots}</span> '
            f"<strong>{escape(i.repo)}#{i.number}</strong> {link} {pill}"
            f'<div style="color:{MUTED};font-size:14px">{escape(i.why)}</div></li>'
        )

    pulls = []
    for pr in digest.pulls:
        title = escape(pr.title)
        link = f'<a href="{escape(pr.url)}" style="color:{ACTION}">{title}</a>' if pr.url else title
        nudge = (
            (
                f'<div style="color:{MUTED};font-size:14px">Nudge draft (copy it if you want '
                f"to send it): &ldquo;{escape(pr.nudge)}&rdquo;</div>"
            )
            if pr.nudge
            else ""
        )
        pulls.append(
            f'<li style="padding:10px 0;border-bottom:1px solid {RULE}">'
            f"<strong>{escape(pr.repo)}#{pr.number}</strong> {link}: {escape(pr.status)}"
            f'<div style="color:{MUTED};font-size:14px">{escape(pr.needs_you)}</div>'
            f"{nudge}</li>"
        )
    body = "".join(
        [
            f'<p style="color:{MUTED}">{escape(digest.quiet_message)}</p>'
            if digest.quiet_message
            else "",
            section("Free for you", [issue(i) for i in digest.free]),
            section("Your pull requests", pulls),
            section("New since yesterday", [issue(i) for i in digest.new_since]),
            section(
                "Watchlist alerts",
                [f'<li style="padding:6px 0">{escape(a.text)}</li>' for a in digest.alerts],
            ),
        ]
    )
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape(BRAND.name)}: {escape(digest.title)}</title></head>"
        f'<body style="margin:0;background:{GROUND}">'
        f'<div style="max-width:640px;margin:0 auto;padding:24px;background:#FFFFFF;'
        f'font-family:Segoe UI,Helvetica,sans-serif;color:{INK};line-height:1.5">'
        f'<h1 style="font-size:22px;margin:0 0 4px">{escape(BRAND.name)}</h1>'
        f'<p style="color:{MUTED};margin:0">{escape(digest.title)}</p>{body}'
        f'<p style="color:{MUTED};font-size:12px;margin-top:24px">{escape(BRAND.name)} only '
        "reads from GitHub. It never comments or opens PRs for you.</p></div></body></html>"
    )
