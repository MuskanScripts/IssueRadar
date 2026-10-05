"""Per-repo rules (brief 5.8): label maps, not-ready labels and contribution rules.

Presets ship in ``issueradar/presets/rules``. A user can add or override
files in their own rules folder; a user file for the same repo wins.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["beginner", "intermediate", "pro"]


class AcceptedByBot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str | None = None
    closing_comment_contains: str | None = None


class RepoRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repo: str
    label_tiers: dict[str, Tier] = Field(default_factory=dict)
    not_ready_labels: list[str] = Field(default_factory=list)
    maintainer_only_labels: list[str] = Field(default_factory=list)
    issue_required_before_pr: bool = False
    discussion_first_keywords: list[str] = Field(default_factory=list)
    accepted_by_bot: AcceptedByBot | None = None
    notes: str | None = None

    @classmethod
    def empty(cls, repo: str) -> RepoRules:
        return cls(repo=repo)


class StarterPack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    verified: bool = False
    repos: list[str]


def _load_dir(text_files: list[tuple[str, str]]) -> dict[str, RepoRules]:
    rules: dict[str, RepoRules] = {}
    for name, text in text_files:
        data = yaml.safe_load(text) or {}
        try:
            rule = RepoRules.model_validate(data)
        except Exception as exc:  # report which file is broken
            raise ValueError(f"{name}: {exc}") from exc
        rules[rule.repo.lower()] = rule
    return rules


def load_rules(user_dir: Path | None = None) -> dict[str, RepoRules]:
    """Presets first, then the user's own files on top."""
    preset_dir = files("issueradar.presets").joinpath("rules")
    texts = [
        (p.name, p.read_text(encoding="utf-8"))
        for p in sorted(preset_dir.iterdir(), key=lambda x: x.name)
        if p.name.endswith(".yaml")
    ]
    rules = _load_dir(texts)
    if user_dir is not None and user_dir.is_dir():
        user = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(user_dir.glob("*.yaml"))]
        rules.update(_load_dir(user))
    return rules


def rules_for(rules: dict[str, RepoRules], repo: str) -> RepoRules:
    return rules.get(repo.lower()) or RepoRules.empty(repo)


def load_packs() -> dict[str, StarterPack]:
    folder = files("issueradar.presets").joinpath("packs")
    packs: dict[str, StarterPack] = {}
    for entry in sorted(folder.iterdir(), key=lambda x: x.name):
        if entry.name.endswith(".yaml"):
            key = entry.name.removesuffix(".yaml")
            packs[key] = StarterPack.model_validate(yaml.safe_load(entry.read_text("utf-8")))
    return packs
