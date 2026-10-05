"""Ranking (brief 5.7). Only free and likely-free issues are ranked.

rank = w_tier * tier_fit + w_health * health/100 + w_stack * stack_fit
     + w_fresh * freshness + w_comp * low_competition

* tier_fit: 1 when the issue's tier is the user's target, 0.5 one tier away, 0 otherwise
  (0.5 when there is no skills.yaml).
* freshness: 0.5 ** (days since last update / half-life).
* low_competition: 1 - min(comments / competition_comments, 1); a likely-free
  issue (stale claim) loses another half.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from issueradar.config.settings import RankingSettings
from issueradar.models import Availability, Tier


@dataclass
class RankInputs:
    availability: Availability
    tier: Tier
    tier_fit: float
    health: int
    stack_fit: float
    updated_at: datetime | None
    comments: int


@dataclass
class RankResult:
    score: float
    parts: dict[str, float]
    why: str


def freshness(updated_at: datetime | None, now: datetime, half_life_days: float) -> float:
    if updated_at is None:
        return 0.5
    days = max((now - updated_at).total_seconds() / 86400, 0.0)
    return float(0.5 ** (days / half_life_days))


def score(inputs: RankInputs, settings: RankingSettings, now: datetime) -> RankResult | None:
    if not inputs.availability.rankable:
        return None
    competition = 1 - min(inputs.comments / settings.competition_comments, 1.0)
    if inputs.availability is Availability.LIKELY_FREE:
        competition *= 0.5
    parts = {
        "tier_fit": inputs.tier_fit,
        "repo_health": inputs.health / 100,
        "stack_fit": inputs.stack_fit,
        "freshness": freshness(inputs.updated_at, now, settings.freshness_half_life_days),
        "low_competition": competition,
    }
    weights = settings.weights.model_dump()
    total = sum(weights[k] * v for k, v in parts.items())
    return RankResult(round(total, 4), parts, _why(inputs, parts))


def _why(inputs: RankInputs, parts: dict[str, float]) -> str:
    bits = []
    if parts["tier_fit"] >= 1:
        bits.append(f"{inputs.tier.label} matches your level")
    elif parts["tier_fit"] == 0.5 and inputs.tier_fit != 0.5:
        bits.append(f"{inputs.tier.label}, one step from your level")
    if inputs.health >= 70:
        bits.append(f"healthy repo ({inputs.health})")
    elif inputs.health < 40:
        bits.append(f"slow repo ({inputs.health})")
    if parts["stack_fit"] >= 0.7:
        bits.append("in your stack")
    if parts["freshness"] >= 0.8:
        bits.append("active this week")
    if inputs.comments == 0:
        bits.append("nobody has commented yet")
    if inputs.availability is Availability.LIKELY_FREE:
        bits.append("old claim went quiet")
    return "; ".join(bits).capitalize() if bits else "Free and open"
