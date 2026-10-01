"""Example files in examples/ must stay valid as the schema changes."""

from pathlib import Path

import yaml

from issueradar.config import load_settings

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_example_config_is_valid() -> None:
    load_settings(EXAMPLES / "firstpr.yaml")


def test_example_skills_uses_known_levels() -> None:
    data = yaml.safe_load((EXAMPLES / "skills.yaml").read_text(encoding="utf-8"))
    levels = {"learning", "medium", "strong"}
    for section in ("languages", "frameworks", "domains"):
        assert set(data[section].values()) <= levels, section
