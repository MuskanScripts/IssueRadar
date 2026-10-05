"""API budgeter: tracks every rate-limit bucket from response headers.

GitHub reports the state of the bucket a request counted against in the
``x-ratelimit-*`` headers. We record the latest values per resource (``core``,
``search``, ``graphql``) and refuse to start new requests once the remaining
budget falls inside the configured safety margin, so a run stops cleanly
instead of hammering a limited API.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field

from issueradar.github.errors import QuotaExhausted


@dataclass
class ResourceState:
    limit: int | None = None
    remaining: int | None = None
    used: int | None = None
    reset_at: float | None = None


def _int(headers: Mapping[str, str], name: str) -> int | None:
    value = headers.get(name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


@dataclass
class BudgetSummary:
    requests: dict[str, int]
    not_modified: int
    graphql_cost: int
    resources: dict[str, ResourceState]

    @property
    def total_requests(self) -> int:
        return sum(self.requests.values())

    def line(self) -> str:
        parts = [f"API budget used: {self.total_requests} requests"]
        if self.not_modified:
            parts.append(f"{self.not_modified} answered by cache (304)")
        if self.graphql_cost:
            parts.append(f"{self.graphql_cost} GraphQL points")
        text = ", ".join(parts)
        remaining = [
            f"{name} {state.remaining}/{state.limit}"
            for name, state in sorted(self.resources.items())
            if state.remaining is not None and state.limit is not None
        ]
        if remaining:
            text += ". Remaining: " + ", ".join(remaining)
        return text + "."


@dataclass
class ApiBudget:
    """Shared by every request made with one token."""

    safety_margin: float
    states: dict[str, ResourceState] = field(default_factory=dict)
    requests: Counter[str] = field(default_factory=Counter)
    not_modified: int = 0
    graphql_cost: int = 0

    def check(self, resource: str) -> None:
        """Raise ``QuotaExhausted`` if starting a request now would eat into the margin."""
        state = self.states.get(resource)
        if state is None or state.remaining is None or state.limit is None:
            return  # nothing known yet; the first response will tell us
        floor = int(state.limit * self.safety_margin)
        if state.remaining <= floor:
            raise QuotaExhausted(resource, state.reset_at)

    def observe(self, resource: str, headers: Mapping[str, str], *, not_modified: bool) -> str:
        """Record one response. Returns the resource GitHub says it counted against."""
        actual = headers.get("x-ratelimit-resource") or resource
        self.requests[actual] += 1
        if not_modified:
            self.not_modified += 1
        state = self.states.setdefault(actual, ResourceState())
        limit = _int(headers, "x-ratelimit-limit")
        remaining = _int(headers, "x-ratelimit-remaining")
        if limit is not None:
            state.limit = limit
        if remaining is not None:
            state.remaining = remaining
        used = _int(headers, "x-ratelimit-used")
        if used is not None:
            state.used = used
        reset = _int(headers, "x-ratelimit-reset")
        if reset is not None:
            state.reset_at = float(reset)
        return actual

    def add_graphql_cost(self, cost: int) -> None:
        self.graphql_cost += cost

    def summary(self) -> BudgetSummary:
        return BudgetSummary(
            requests=dict(self.requests),
            not_modified=self.not_modified,
            graphql_cost=self.graphql_cost,
            resources={k: ResourceState(**vars(v)) for k, v in self.states.items()},
        )
