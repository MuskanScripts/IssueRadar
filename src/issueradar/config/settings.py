"""Settings schema and loader.

``defaults.yaml`` is always loaded first; a user file, if given, is merged on
top of it key by key. Validation errors are turned into short messages that
say which field is wrong and why.
"""

from __future__ import annotations

import math
from importlib.resources import files
from pathlib import Path
from typing import Any

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


class AvailabilitySettings(_Strict):
    stale_claim_days: int = Field(ge=1)
    maintainer_associations: list[str]
    claim_patterns: list[str]
    invitation_patterns: list[str]


class DifficultySettings(_Strict):
    beginner_max: int = Field(ge=0, le=100)
    intermediate_max: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> DifficultySettings:
        if not self.beginner_max < self.intermediate_max < 100:
            raise ValueError("need beginner_max < intermediate_max < 100")
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


class PullRequestSettings(_Strict):
    stale_days: int = Field(ge=1)


class DigestSettings(_Strict):
    top_n: int = Field(ge=1, le=50)


class Settings(_Strict):
    github: GitHubSettings
    storage: StorageSettings
    sync: SyncSettings
    availability: AvailabilitySettings
    difficulty: DifficultySettings
    health: HealthSettings
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
