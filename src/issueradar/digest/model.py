"""What a digest contains. Renderers and channels only read these objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class IssueItem:
    key: str  # "issue:owner/repo#12"
    repo: str
    number: int
    title: str
    url: str | None
    tier: str  # beginner, intermediate, pro
    dots: str  # "●○○"
    state: str  # Free, Likely free
    why: str
    state_hash: str


@dataclass(frozen=True)
class PullItem:
    key: str  # "pr:owner/repo#12"
    repo: str
    number: int
    title: str
    url: str | None
    status: str  # sentence-case label
    needs_you: str
    state_hash: str
    nudge: str | None = None


@dataclass(frozen=True)
class Alert:
    key: str  # "repo:owner/repo:quiet"
    repo: str
    text: str
    state_hash: str


@dataclass
class Digest:
    created_at: datetime
    free: list[IssueItem] = field(default_factory=list)
    pulls: list[PullItem] = field(default_factory=list)
    new_since: list[IssueItem] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    quiet_message: str | None = None

    @property
    def items(self) -> list[IssueItem | PullItem | Alert]:
        return [*self.free, *self.pulls, *self.new_since, *self.alerts]

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def title(self) -> str:
        day = self.created_at.strftime("%Y-%m-%d")
        if self.is_empty:
            return f"Quiet day ({day})"
        count = len(self.free) + len(self.new_since)
        return f"{count} free issue{'s' if count != 1 else ''} for you ({day})"
