import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

from issueradar.brand import BRAND
from issueradar.config import load_settings
from issueradar.demo import DemoDataset, load_demo
from issueradar.models import Availability, Tier


def _raw() -> dict:  # type: ignore[type-arg]
    text = files("issueradar.demo").joinpath("fixtures/demo.json").read_text(encoding="utf-8")
    return json.loads(text)  # type: ignore[no-any-return]


def test_demo_loads_and_is_labelled() -> None:
    data = load_demo()
    assert data.label == BRAND.demo_label
    assert data.repos and data.issues and data.pull_requests


def test_demo_covers_every_tier_and_some_unavailable_states() -> None:
    data = load_demo()
    assert {i.tier for i in data.issues} == set(Tier)
    states = {i.availability for i in data.issues}
    assert Availability.FREE in states
    assert states - {Availability.FREE, Availability.LIKELY_FREE}, "demo should show filtering"


def test_demo_scores_match_configured_tier_bands() -> None:
    bands = load_settings().difficulty
    for issue in load_demo().issues:
        if issue.difficulty_score <= bands.beginner_max:
            expected = Tier.BEGINNER
        elif issue.difficulty_score <= bands.intermediate_max:
            expected = Tier.INTERMEDIATE
        else:
            expected = Tier.PRO
        assert issue.tier is expected, f"{issue.repo}#{issue.number}"


def test_unlabelled_demo_data_is_rejected() -> None:
    raw = _raw()
    raw["label"] = "Real data"
    with pytest.raises(ValidationError, match="must be labelled"):
        DemoDataset.model_validate(raw)


def test_demo_repos_must_be_sample_repos() -> None:
    raw = _raw()
    raw["repos"][0]["full_name"] = "octocat/hello-world"
    with pytest.raises(ValidationError, match="sample/"):
        DemoDataset.model_validate(raw)
