"""Which token syncs which repo.

- Repos in the shared catalogue, and repos two or more people watch, are synced
  once with the app's own installation token and shared.
- A repo only one person watches is synced with that person's own token, on
  their behalf, so it costs nobody else's rate limit.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_platform.db import CatalogueRepo, Watch

APP = "app"
USER = "user"

_REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_URL = re.compile(r"^https?://github\.com/([^/\s]+/[^/\s#?]+?)(?:\.git)?/?$")


def normalise_repo(value: str) -> str | None:
    """`owner/name` from `owner/name` or a github.com link; None if it is neither."""
    text = value.strip()
    match = _URL.match(text)
    if match:
        text = match.group(1)
    return text if _REPO.match(text) else None


@dataclass
class SyncPlan:
    app: set[str] = field(default_factory=set)
    by_user: dict[int, set[str]] = field(default_factory=lambda: defaultdict(set))
    watchers: dict[str, int] = field(default_factory=dict)

    def token_kind(self, full_name: str) -> str:
        return APP if full_name.lower() in {r.lower() for r in self.app} else USER


async def opted_out(db: AsyncSession) -> set[str]:
    """Lower-case names of repos whose maintainers opted out of FirstPR."""
    names = await db.scalars(
        select(CatalogueRepo.full_name).where(CatalogueRepo.opted_out_at.is_not(None))
    )
    return {n.lower() for n in names}


async def build(db: AsyncSession) -> SyncPlan:
    plan = SyncPlan()
    excluded = await opted_out(db)
    catalogue = {
        name.lower(): name
        for name in await db.scalars(select(CatalogueRepo.full_name))
        if name.lower() not in excluded
    }
    counts = await db.execute(
        select(func.lower(Watch.repo_full_name), func.count(Watch.id)).group_by(
            func.lower(Watch.repo_full_name)
        )
    )
    plan.watchers = {name: n for name, n in counts.all()}
    plan.app = set(catalogue.values())
    for watch in await db.scalars(select(Watch).order_by(Watch.id)):
        key = watch.repo_full_name.lower()
        if key in catalogue or key in excluded:
            continue
        if plan.watchers.get(key, 0) >= 2:
            plan.app.add(watch.repo_full_name)
        else:
            plan.by_user[watch.user_id].add(watch.repo_full_name)
    return plan
