"""Long syncs: scheduled runs get their real time limits and never overlap."""

from __future__ import annotations

from typing import Any

from firstpr_worker import jobs
from firstpr_worker.main import WorkerSettings


def test_scheduled_runs_get_the_same_time_limit_as_queued_ones() -> None:
    # arq does not carry func(timeout=...) over to cron(); a missing timeout there
    # meant every scheduled catalogue sync was stopped after 5 minutes.
    limits = {f.name: f.timeout_s for f in WorkerSettings.functions if hasattr(f, "timeout_s")}
    for job in WorkerSettings.cron_jobs:
        name = job.coroutine.__name__
        if limits.get(name) is not None:
            assert job.timeout_s == limits[name], name


def test_a_sync_stops_well_before_its_job_is_stopped(ctx: dict[str, Any]) -> None:
    limits = {f.name: f.timeout_s for f in WorkerSettings.functions if hasattr(f, "timeout_s")}
    budget = ctx["settings"].sync_time_budget_seconds
    assert limits["sync_catalogue"] is not None
    assert budget <= limits["sync_catalogue"] - 5 * 60


async def test_the_catalogue_sync_gets_a_time_budget(ctx: dict[str, Any]) -> None:
    await jobs.sync_catalogue(ctx)
    assert ctx["catalogue"].time_budgets == [ctx["settings"].sync_time_budget_seconds]


async def test_a_second_catalogue_sync_waits_for_the_first(ctx: dict[str, Any]) -> None:
    await ctx["redis"].set(jobs.SYNC_LOCK_PREFIX + "app", "1")
    assert await jobs.sync_catalogue(ctx) == "skipped: a catalogue sync is already running"
    assert ctx["catalogue"].calls == []

    await ctx["redis"].delete(jobs.SYNC_LOCK_PREFIX + "app")
    assert (await jobs.sync_catalogue(ctx)).startswith("completed")
    # The lock is let go afterwards, so the next run is not blocked.
    assert await ctx["redis"].get(jobs.SYNC_LOCK_PREFIX + "app") is None
