from pathlib import Path

import pytest

from issueradar.config import ConfigError, load_settings


def test_defaults_are_valid() -> None:
    settings = load_settings()
    # Values documented in docs/github-api-notes.md.
    assert settings.github.rest.authenticated_per_hour == 5000
    assert settings.github.search.requests_per_minute == 30
    assert settings.github.search.max_query_chars == 256
    assert settings.github.graphql.max_page_size == 100
    assert settings.github.concurrency.max_in_flight == 1
    assert settings.availability.stale_claim_days == 14
    assert settings.pull_requests.stale_days == 7


def test_user_file_overrides_one_value(tmp_path: Path) -> None:
    user = tmp_path / "firstpr.yaml"
    user.write_text("digest:\n  top_n: 8\n", encoding="utf-8")
    settings = load_settings(user)
    assert settings.digest.top_n == 8
    assert settings.github.rest.authenticated_per_hour == 5000  # untouched


def test_ranking_weights_must_sum_to_one(tmp_path: Path) -> None:
    user = tmp_path / "bad.yaml"
    user.write_text("ranking:\n  weights:\n    tier_fit: 0.9\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"ranking\.weights"):
        load_settings(user)


def test_unknown_key_is_reported_with_its_path(tmp_path: Path) -> None:
    user = tmp_path / "typo.yaml"
    user.write_text("digest:\n  topn: 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"digest\.topn"):
        load_settings(user)


def test_retry_wait_cannot_go_below_one_minute(tmp_path: Path) -> None:
    user = tmp_path / "fast.yaml"
    user.write_text("github:\n  retry:\n    min_secondary_wait_seconds: 5\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="min_secondary_wait_seconds"):
        load_settings(user)


def test_invalid_yaml_is_a_config_error(tmp_path: Path) -> None:
    user = tmp_path / "broken.yaml"
    user.write_text("digest: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_settings(user)


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read file"):
        load_settings(tmp_path / "nope.yaml")
