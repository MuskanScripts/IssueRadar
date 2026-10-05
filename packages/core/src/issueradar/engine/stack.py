"""Stack matching: does this issue use technologies the user knows? (brief 5.6)

The issue's technologies come from three places:
* languages: the repo's language breakdown, plus file extensions named in the issue;
* frameworks: dependencies found in the repo's manifest files;
* domains: the repo's GitHub topics.

The user's ``skills.yaml`` gives each technology a level. Default target:
Beginner issues where the user is learning or medium, Intermediate where
strong. ``stretch: true`` moves every target up one tier.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from issueradar.config.settings import StackSettings
from issueradar.engine.types import Reason
from issueradar.models import Tier

Level = Literal["learning", "medium", "strong"]
LEVEL_FIT: dict[str, float] = {"strong": 1.0, "medium": 0.7, "learning": 0.4}
TARGET: dict[str, Tier] = {
    "learning": Tier.BEGINNER,
    "medium": Tier.BEGINNER,
    "strong": Tier.INTERMEDIATE,
}
ORDER = [Tier.BEGINNER, Tier.INTERMEDIATE, Tier.PRO]


class SkillProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stretch: bool = False
    languages: dict[str, Level] = Field(default_factory=dict)
    frameworks: dict[str, Level] = Field(default_factory=dict)
    domains: dict[str, Level] = Field(default_factory=dict)
    prefer_issue_types: list[str] = Field(default_factory=list)

    def level(self, kind: str, name: str) -> Level | None:
        table: dict[str, Level] = getattr(self, kind)
        return {k.lower(): v for k, v in table.items()}.get(name.lower())


def load_profile(path: Path) -> SkillProfile:
    return SkillProfile.model_validate(yaml.safe_load(path.read_text("utf-8")) or {})


@dataclass
class RepoStack:
    languages: list[str] = field(default_factory=list)  # biggest first
    frameworks: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)


@dataclass
class StackResult:
    fit: float
    target_tier: Tier | None
    reasons: list[Reason] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)


def languages_from_breakdown(breakdown: dict[str, int], limit: int = 3) -> list[str]:
    ranked = sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    return [name.lower() for name, _ in ranked[:limit]]


def domains_from_topics(topics: list[str], settings: StackSettings) -> list[str]:
    lowered = {t.lower() for t in topics}
    return [d for d, tags in settings.domains.items() if lowered & {t.lower() for t in tags}]


_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9_.\-]+)")
_GRADLE = re.compile(r"""['"]([\w.\-]+):([\w.\-]+)(?::[\w.\-]+)?['"]""")
_GO_REQ = re.compile(r"^\s*(?:require\s+)?([\w.\-]+/[\w.\-/]+)\s+v", re.MULTILINE)
_POM_ARTIFACT = re.compile(r"<(groupId|artifactId)>\s*([^<\s]+)\s*</\1>")


def dependency_names(filename: str, text: str) -> set[str]:
    """Dependency names from one manifest file. Unknown formats give an empty set."""
    names: set[str] = set()
    try:
        if filename == "package.json":
            data = json.loads(text)
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                names.update((data.get(key) or {}).keys())
        elif filename == "pyproject.toml":
            data = tomllib.loads(text)
            deps = list(data.get("project", {}).get("dependencies", []))
            for group in data.get("project", {}).get("optional-dependencies", {}).values():
                deps.extend(group)
            deps.extend(data.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys())
            for dep in deps:
                match = _REQ_NAME.match(dep)
                if match:
                    names.add(match.group(1))
        elif filename == "requirements.txt":
            for line in text.splitlines():
                if line.strip() and not line.lstrip().startswith(("#", "-")):
                    match = _REQ_NAME.match(line)
                    if match:
                        names.add(match.group(1))
        elif filename == "pom.xml":
            names.update(value for _, value in _POM_ARTIFACT.findall(text))
        elif filename in ("build.gradle", "build.gradle.kts"):
            for group, artifact in _GRADLE.findall(text):
                names.update({group, artifact})
        elif filename == "go.mod":
            names.update(_GO_REQ.findall(text))
        elif filename == "Cargo.toml":
            data = tomllib.loads(text)
            names.update(data.get("dependencies", {}).keys())
            names.update(data.get("dev-dependencies", {}).keys())
    except (ValueError, tomllib.TOMLDecodeError):
        return set()
    return {n.lower().replace("_", "-") for n in names}


def frameworks_from_dependencies(names: set[str], settings: StackSettings) -> list[str]:
    found = []
    for framework, deps in settings.frameworks.items():
        wanted = {d.lower() for d in deps}
        if names & wanted or any(n.startswith(tuple(w + "." for w in wanted)) for n in names):
            found.append(framework)
    return found


def languages_from_paths(paths: list[str], settings: StackSettings) -> list[str]:
    found: list[str] = []
    for path in paths:
        suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        language = settings.extensions.get(suffix)
        if language and language not in found:
            found.append(language)
    return found


def shift(tier: Tier, steps: int) -> Tier:
    index = max(0, min(len(ORDER) - 1, ORDER.index(tier) + steps))
    return ORDER[index]


def match(
    repo: RepoStack, issue_paths: list[str], profile: SkillProfile | None, settings: StackSettings
) -> StackResult:
    if profile is None:
        return StackResult(0.5, None, [Reason("No skills.yaml, so stack fit is neutral")])

    issue_langs = languages_from_paths(issue_paths, settings)
    languages = issue_langs or repo.languages[:1]
    candidates: list[tuple[str, str, Level]] = []
    for kind, names in (
        ("languages", languages),
        ("frameworks", repo.frameworks),
        ("domains", repo.domains),
    ):
        for name in names:
            level = profile.level(kind, name)
            if level is not None:
                candidates.append((kind, name, level))

    if not candidates:
        stack = ", ".join([*languages, *repo.frameworks]) or "unknown"
        return StackResult(0.0, None, [Reason(f"Not in your skills ({stack})")])

    best = max(candidates, key=lambda c: LEVEL_FIT[c[2]])
    fit = sum(LEVEL_FIT[c[2]] for c in candidates) / len(candidates)
    fit = round((fit + LEVEL_FIT[best[2]]) / 2, 3)  # reward the best match, keep breadth
    language_level = next((c[2] for c in candidates if c[0] == "languages"), best[2])
    target = TARGET[language_level]
    if profile.stretch:
        target = shift(target, 1)
    reasons = [Reason(f"You are {level} in {name}") for _, name, level in candidates]
    where = "named files" if issue_langs else "the repo's main language"
    reasons.append(
        Reason(
            f"Target level {target.label} (from your {language_level} level in "
            f"{languages[0] if languages else best[1]}, via {where}"
            + (", stretch on" if profile.stretch else "")
            + ")"
        )
    )
    return StackResult(fit, target, reasons, [name for _, name, _ in candidates])


def tier_fit(tier: Tier, target: Tier | None) -> float:
    if target is None:
        return 0.5
    gap = abs(ORDER.index(tier) - ORDER.index(target))
    return {0: 1.0, 1: 0.5}.get(gap, 0.0)
