"""Settings schema and loader.

``defaults.yaml`` is always loaded first; a user file, if given, is merged on
top of it key by key. Validation errors are turned into short messages that
say which field is wrong and why.
"""

from __future__ import annotations

import math
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RestLimits(_Strict):
    authenticated_per_hour: int = Field(gt=0)
    unauthenticated_per_hour: int = Field(gt=0)
    actions_token_per_hour: int = Field(gt=0)
    per_page: int = Field(ge=1, le=100)


class GraphQLLimits(_Strict):
    points_per_hour: int = Field(gt=0)
    max_page_size: int = Field(ge=1, le=100)
    max_nodes_per_call: int = Field(gt=0)
    server_timeout_seconds: float = Field(gt=0)
    batch_size: int = Field(ge=1, le=100)


class SearchLimits(_Strict):
    requests_per_minute: int = Field(gt=0)
    code_requests_per_minute: int = Field(gt=0)
    unauthenticated_requests_per_minute: int = Field(gt=0)
    max_results_per_query: int = Field(gt=0)
    max_query_chars: int = Field(gt=0)
    max_boolean_operators: int = Field(ge=0)
    max_repositories_per_query: int = Field(gt=0)
    per_page: int = Field(ge=1, le=100)


class SecondaryLimits(_Strict):
    max_concurrent_requests: int = Field(gt=0)
    rest_points_per_minute: int = Field(gt=0)
    graphql_points_per_minute: int = Field(gt=0)
    cpu_seconds_per_minute: int = Field(gt=0)
    graphql_cpu_seconds_per_minute: int = Field(gt=0)


class Concurrency(_Strict):
    max_in_flight: int = Field(ge=1)


class RetryPolicy(_Strict):
    max_retries: int = Field(ge=0, le=10)
    min_secondary_wait_seconds: float = Field(ge=60)
    backoff_factor: float = Field(ge=1)
    max_wait_seconds: float = Field(gt=0)
    server_error_wait_seconds: float = Field(gt=0)


class Budget(_Strict):
    safety_margin: float = Field(ge=0, lt=1)


class GitHubSettings(_Strict):
    api_url: str
    graphql_url: str
    user_agent: str
    request_timeout_seconds: float = Field(gt=0)
    rest: RestLimits
    graphql: GraphQLLimits
    search: SearchLimits
    secondary: SecondaryLimits
    concurrency: Concurrency
    retry: RetryPolicy
    budget: Budget

    @model_validator(mode="after")
    def _concurrency_within_secondary(self) -> GitHubSettings:
        if self.concurrency.max_in_flight > self.secondary.max_concurrent_requests:
            raise ValueError(
                "concurrency.max_in_flight cannot exceed secondary.max_concurrent_requests"
            )
        return self


class StorageSettings(_Strict):
    url: str | None = None


class SyncSettings(_Strict):
    max_pages_per_list: int = Field(ge=1, le=10)
    scan_open_pull_requests: bool


class EnrichSettings(_Strict):
    max_issues_per_repo: int = Field(ge=0, le=500)
    fetch_timeline: bool
    linked_pr_search: bool
    repo_health: bool


class AvailabilitySettings(_Strict):
    stale_claim_days: int = Field(ge=1)
    maintainer_associations: list[str]
    claim_patterns: list[str]
    release_patterns: list[str]
    invitation_patterns: list[str]
    not_ready_labels: list[str]
    non_english_ascii_ratio: float = Field(ge=0, le=1)
    non_english_min_words: int = Field(ge=1)
    non_english_stopword_ratio: float = Field(ge=0, le=1)


Tier = Literal["beginner", "intermediate", "pro"]


class DifficultyAdjustments(_Strict):
    docs_or_typo: int
    tests_only: int
    code_or_repro: int
    names_a_file: int
    short_body: int
    long_body: int
    many_comments: int
    per_linked_issue: int
    max_linked_issues: int = Field(ge=0)
    discussion_first: int
    performance_or_concurrency: int
    security: int


class TimeBuckets(_Strict):
    under_an_hour: int = Field(ge=0, le=100)
    half_a_day: int = Field(ge=0, le=100)
    a_weekend: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> TimeBuckets:
        if not self.under_an_hour < self.half_a_day < self.a_weekend:
            raise ValueError("need under_an_hour < half_a_day < a_weekend")
        return self


class DifficultyKeywords(_Strict):
    docs_or_typo: list[str]
    tests_only: list[str]
    discussion_first: list[str]
    performance_or_concurrency: list[str]
    security: list[str]
    repro: list[str]


class DifficultySettings(_Strict):
    beginner_max: int = Field(ge=0, le=100)
    intermediate_max: int = Field(ge=0, le=100)
    base_score: int = Field(ge=0, le=100)
    tier_anchor: dict[Tier, int]
    label_tiers: dict[str, Tier]
    adjustments: DifficultyAdjustments
    short_body_chars: int = Field(ge=0)
    long_body_chars: int = Field(ge=0)
    many_comments: int = Field(ge=1)
    time_buckets: TimeBuckets
    keywords: DifficultyKeywords

    @model_validator(mode="after")
    def _ordered(self) -> DifficultySettings:
        if not self.beginner_max < self.intermediate_max < 100:
            raise ValueError("need beginner_max < intermediate_max < 100")
        if set(self.tier_anchor) != {"beginner", "intermediate", "pro"}:
            raise ValueError("tier_anchor needs beginner, intermediate and pro")
        return self


class HealthWeights(_Strict):
    first_response: float = Field(ge=0)
    outside_merge_rate: float = Field(ge=0)
    recent_commit: float = Field(ge=0)
    pr_backlog: float = Field(ge=0)
    contributor_docs: float = Field(ge=0)

    @model_validator(mode="after")
    def _sum_100(self) -> HealthWeights:
        total = sum(self.model_dump().values())
        if not math.isclose(total, 100):
            raise ValueError(f"health weights must add up to 100, got {total:g}")
        return self


class HealthSettings(_Strict):
    cache_hours: int = Field(ge=1)
    weights: HealthWeights
    response_days_good: float = Field(ge=0)
    response_days_bad: float = Field(gt=0)
    commit_days_good: float = Field(ge=0)
    commit_days_bad: float = Field(gt=0)
    backlog_good: int = Field(ge=0)
    backlog_bad: int = Field(gt=0)
    min_samples: int = Field(ge=1)
    closed_prs_sample: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def _ranges(self) -> HealthSettings:
        for good, bad in (
            ("response_days_good", "response_days_bad"),
            ("commit_days_good", "commit_days_bad"),
            ("backlog_good", "backlog_bad"),
        ):
            if getattr(self, good) >= getattr(self, bad):
                raise ValueError(f"{good} must be smaller than {bad}")
        return self


class StackSettings(_Strict):
    extensions: dict[str, str]
    frameworks: dict[str, list[str]]
    domains: dict[str, list[str]]
    manifests: list[str]


class RankingWeights(_Strict):
    tier_fit: float = Field(ge=0)
    repo_health: float = Field(ge=0)
    stack_fit: float = Field(ge=0)
    freshness: float = Field(ge=0)
    low_competition: float = Field(ge=0)

    @model_validator(mode="after")
    def _sum_1(self) -> RankingWeights:
        total = sum(self.model_dump().values())
        if not math.isclose(total, 1.0, abs_tol=1e-9):
            raise ValueError(f"ranking weights must add up to 1.0, got {total:g}")
        return self


class RankingSettings(_Strict):
    weights: RankingWeights
    freshness_half_life_days: float = Field(gt=0)
    competition_comments: int = Field(ge=1)


class PullRequestSettings(_Strict):
    stale_days: int = Field(ge=1)
    track_days: int = Field(ge=1)
    unreviewed_warning_at: int = Field(ge=1)


class MarkdownChannel(_Strict):
    enabled: bool


class RssChannel(_Strict):
    enabled: bool
    max_items: int = Field(ge=1, le=500)
    link: str


class EmailChannel(_Strict):
    enabled: bool
    smtp_host: str
    smtp_port: int = Field(ge=1, le=65535)
    starttls: bool
    username: str
    sender: str
    recipient: str
    password_env: str


class TelegramChannel(_Strict):
    enabled: bool
    chat_id: str
    token_env: str


class WebhookChannel(_Strict):
    enabled: bool
    webhook_env: str


class Channels(_Strict):
    markdown: MarkdownChannel
    rss: RssChannel
    email: EmailChannel
    telegram: TelegramChannel
    discord: WebhookChannel
    slack: WebhookChannel


class DigestSettings(_Strict):
    top_n: int = Field(ge=1, le=50)
    new_since_hours: int = Field(ge=1)
    quiet_repo_days: int = Field(ge=1)
    output_folder: str
    channels: Channels


class Settings(_Strict):
    github: GitHubSettings
    storage: StorageSettings
    sync: SyncSettings
    enrich: EnrichSettings
    availability: AvailabilitySettings
    difficulty: DifficultySettings
    health: HealthSettings
    stack: StackSettings
    ranking: RankingSettings
    pull_requests: PullRequestSettings
    digest: DigestSettings


class ConfigError(Exception):
    """A config file could not be read or did not pass validation."""


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(text: str, source: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{source}: not valid YAML ({exc})") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{source}: the top level must be a mapping of settings")
    return data


def default_config_text() -> str:
    return files("issueradar.config").joinpath("defaults.yaml").read_text(encoding="utf-8")


def load_settings(user_file: Path | None = None) -> Settings:
    """Load defaults, merge ``user_file`` on top, and validate."""
    data = _read_yaml(default_config_text(), "defaults.yaml")
    source = "defaults.yaml"
    if user_file is not None:
        try:
            text = user_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"{user_file}: cannot read file ({exc.strerror})") from exc
        data = _deep_merge(data, _read_yaml(text, str(user_file)))
        source = str(user_file)
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        lines = [f"{source}: {exc.error_count()} problem(s) in config"]
        for err in exc.errors():
            where = ".".join(str(part) for part in err["loc"]) or "(top level)"
            lines.append(f"  {where}: {err['msg']}")
        raise ConfigError("\n".join(lines)) from exc
