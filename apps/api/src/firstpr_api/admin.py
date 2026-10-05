"""Admin pages: what the sync is doing, and the shared catalogue."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from firstpr_api.deps import Jobs, get_db, get_jobs, get_redis, require_admin, require_csrf
from firstpr_api.health import run_check
from firstpr_platform import plan
from firstpr_platform.db import (
    CatalogueRepo,
    FeatureInterest,
    IssueCard,
    RepoSync,
    WebhookEvent,
    utcnow,
)

# Must match BUDGET_PREFIX in apps/worker.
BUDGET_PREFIX = "firstpr:budget:"

router = APIRouter(dependencies=[Depends(require_admin)])


class RepoRow(BaseModel):
    full_name: str
    token: str
    watchers: int
    in_catalogue: bool
    status: str | None
    note: str | None
    open_issues: int | None
    synced_at: datetime | None


class SyncOverview(BaseModel):
    worker: str
    budgets: dict[str, dict[str, Any]]
    webhooks_last_hour: int
    webhooks_waiting: int
    issue_cards: int
    # "I want this" clicks per coming-soon feature.
    interest: dict[str, int]
    repos: list[RepoRow]


class CatalogueIn(BaseModel):
    repo: str


@router.get("/admin/sync", response_model=SyncOverview)
async def overview(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: Redis = Depends(get_redis),  # noqa: B008
) -> SyncOverview:
    sync_plan = await plan.build(db)
    catalogue = {n.lower() for n in await db.scalars(select(CatalogueRepo.full_name))}
    syncs = {s.full_name.lower(): s for s in await db.scalars(select(RepoSync))}
    names = sorted(sync_plan.app | {r for repos in sync_plan.by_user.values() for r in repos})
    rows = []
    for name in names:
        last = syncs.get(name.lower())
        rows.append(
            RepoRow(
                full_name=name,
                token=sync_plan.token_kind(name),
                watchers=sync_plan.watchers.get(name.lower(), 0),
                in_catalogue=name.lower() in catalogue,
                status=last.status if last else None,
                note=last.note if last else None,
                open_issues=last.open_issues if last else None,
                synced_at=last.synced_at if last else None,
            )
        )
    # Problems first, then never synced, then the rest by name.
    order = {"failed": 0, "paused": 1, None: 2}
    rows.sort(key=lambda r: (order.get(r.status, 3), r.full_name.lower()))

    budgets: dict[str, dict[str, Any]] = {}
    async for key in redis.scan_iter(match=f"{BUDGET_PREFIX}*"):
        raw = await redis.get(key)
        name = key.decode() if isinstance(key, bytes) else str(key)
        if raw:
            budgets[name.removeprefix(BUDGET_PREFIX)] = json.loads(raw)

    hour_ago = utcnow() - timedelta(hours=1)
    recent = await db.scalar(
        select(func.count()).select_from(WebhookEvent).where(WebhookEvent.received_at >= hour_ago)
    )
    waiting = await db.scalar(
        select(func.count()).select_from(WebhookEvent).where(WebhookEvent.processed_at.is_(None))
    )
    cards = await db.scalar(select(func.count()).select_from(IssueCard))
    grouped = await db.execute(
        select(FeatureInterest.feature, func.count()).group_by(FeatureInterest.feature)
    )
    interest = {feature: count for feature, count in grouped.all()}
    worker = await run_check(request.app.state.checks["worker"])
    return SyncOverview(
        worker=worker,
        budgets=budgets,
        webhooks_last_hour=recent or 0,
        webhooks_waiting=waiting or 0,
        issue_cards=cards or 0,
        interest=interest,
        repos=rows,
    )


@router.post("/admin/catalogue", status_code=201, dependencies=[Depends(require_csrf)])
async def add_to_catalogue(
    body: CatalogueIn,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    jobs: Jobs = Depends(get_jobs),  # noqa: B008
) -> dict[str, str]:
    name = plan.normalise_repo(body.repo)
    if name is None:
        raise HTTPException(422, "Use owner/name, for example pallets/flask.")
    if await db.get(CatalogueRepo, name) is None:
        db.add(CatalogueRepo(full_name=name, source="admin"))
        await db.commit()
        await jobs.enqueue_job("sync_catalogue", _job_id="sync-catalogue", _defer_by=5)
    return {"full_name": name}


@router.delete(
    "/admin/catalogue/{owner}/{name}", status_code=204, dependencies=[Depends(require_csrf)]
)
async def remove_from_catalogue(
    owner: str,
    name: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> None:
    await db.execute(
        delete(CatalogueRepo).where(
            func.lower(CatalogueRepo.full_name) == f"{owner}/{name}".lower()
        )
    )
    await db.commit()
