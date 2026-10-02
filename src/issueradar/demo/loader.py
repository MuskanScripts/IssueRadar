"""Load and validate the bundled demo dataset.

Demo data is synthetic: repositories are named ``sample/...`` and do not exist
on GitHub. It must never be presented as real (ADR 0008).
"""

from __future__ import annotations

import json
from datetime import datetime
from importlib.resources import files

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from issueradar.brand import BRAND
from issueradar.models import Availability, IssueType, PullRequestStatus, Tier, TimeBucket

SAMPLE_OWNER = "sample/"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DemoHealth(_Strict):
    score: int = Field(ge=0, le=100)
    reasons: list[str]


class DemoRepo(_Strict):
    full_name: str
    description: str
    language: str
    topics: list[str]
    stars: int = Field(ge=0)
    health: DemoHealth

    @field_validator("full_name")
    @classmethod
    def _is_sample(cls, value: str) -> str:
        if not value.startswith(SAMPLE_OWNER):
            raise ValueError(f"demo repos must be named {SAMPLE_OWNER}..., got {value!r}")
        return value


class DemoIssue(_Strict):
    repo: str
    number: int = Field(gt=0)
    title: str
    labels: list[str]
    language: str
    domain: str
    issue_type: IssueType
    tier: Tier
    difficulty_score: int = Field(ge=0, le=100)
    time_bucket: TimeBucket
    availability: Availability
    comments: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
    why_here: str
    why_available: list[str] = Field(min_length=1)
    why_tier: list[str] = Field(min_length=1)


class DemoPullRequest(_Strict):
    repo: str
    number: int = Field(gt=0)
    title: str
    status: PullRequestStatus
    opened_at: datetime
    last_activity_at: datetime
    needs_you: str


class DemoDataset(_Strict):
    label: str
    note: str
    as_of: datetime
    repos: list[DemoRepo]
    issues: list[DemoIssue]
    pull_requests: list[DemoPullRequest]

    @field_validator("label")
    @classmethod
    def _labelled(cls, value: str) -> str:
        if value != BRAND.demo_label:
            raise ValueError(f"demo dataset must be labelled {BRAND.demo_label!r}")
        return value

    @model_validator(mode="after")
    def _references_exist(self) -> DemoDataset:
        names = {repo.full_name for repo in self.repos}
        refs = [(i.repo, i.number) for i in self.issues]
        refs += [(p.repo, p.number) for p in self.pull_requests]
        for repo, number in refs:
            if repo not in names:
                raise ValueError(f"{repo}#{number} points at an unknown repo")
        return self

    def repo(self, full_name: str) -> DemoRepo:
        return next(r for r in self.repos if r.full_name == full_name)


def load_demo() -> DemoDataset:
    raw = files("issueradar.demo").joinpath("fixtures/demo.json").read_text(encoding="utf-8")
    return DemoDataset.model_validate(json.loads(raw))
