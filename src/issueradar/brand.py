"""The product's user-facing name and identifiers, loaded from ``brand.json``.

Renaming the product means editing ``brand.json`` and the matching lines in
``pyproject.toml``. A test checks that they agree. See ADR 0002.
"""

from __future__ import annotations

import json
from importlib.resources import files

from pydantic import BaseModel, ConfigDict


class Brand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    cli: str
    distribution: str
    env_prefix: str
    tagline: str
    demo_label: str
    repository: str

    def env(self, suffix: str) -> str:
        """Name of an environment variable, for example ``FIRSTPR_GITHUB_TOKEN``."""
        return f"{self.env_prefix}_{suffix}"


def load_brand() -> Brand:
    raw = files("issueradar").joinpath("brand.json").read_text(encoding="utf-8")
    return Brand.model_validate(json.loads(raw))


BRAND = load_brand()
