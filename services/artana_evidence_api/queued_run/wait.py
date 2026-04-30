"""Sync wait helpers for queued harness runs."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.config import get_settings
from artana_evidence_api.queued_run.constants import (
    _ACTIVE_RUN_STATUSES,
    _TERMINAL_RUN_STATUSES,
    _TEST_WORKER_ID,
)
from artana_evidence_api.queued_run.models import QueuedRunWaitOutcome
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry


async def maybe_execute_test_worker_run(
    *,
    run: HarnessRunRecord,
    services: object,
) -> None:
    """Drive one in-process worker execution only for test-injected services."""
    if not hasattr(services, "execution_override"):
        return
    execution_override = object.__getattribute__(services, "execution_override")
    if execution_override is None:
        return
    if not hasattr(services, "runtime"):
        return
    from artana_evidence_api.worker import execute_worker_run

    typed_services = cast("HarnessExecutionServices", services)
    try:
        await execute_worker_run(
            run=run,
            runtime=cast(
                "GraphHarnessKernelRuntime",
                object.__getattribute__(services, "runtime"),
            ),
            services=typed_services,
            worker_id=_TEST_WORKER_ID,
            lease_ttl_seconds=get_settings().worker_lease_ttl_seconds,
        )
    except Exception:  # noqa: BLE001
        # Tests should observe the same durable failed-run state that production
        # routes see after the background worker persists the failure payload.
        return


async def wait_for_terminal_run(
    *,
    space_id: UUID | str,
    run_id: UUID | str,
    run_registry: HarnessRunRegistry,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> QueuedRunWaitOutcome:
    """Poll the durable run record until it reaches a terminal status or times out."""
    if timeout_seconds <= 0:
        return QueuedRunWaitOutcome(run=None, timed_out=True)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    normalized_space_id = str(space_id)
    normalized_run_id = str(run_id)
    while True:
        run = run_registry.get_run(
            space_id=normalized_space_id,
            run_id=normalized_run_id,
        )
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' was not found in space '{space_id}'.",
            )
        if (
            run.status in _TERMINAL_RUN_STATUSES
            or run.status not in _ACTIVE_RUN_STATUSES
        ):
            return QueuedRunWaitOutcome(run=run, timed_out=False)
        remaining = deadline - loop.time()
        if remaining <= 0:
            return QueuedRunWaitOutcome(run=None, timed_out=True)
        await asyncio.sleep(min(poll_interval_seconds, remaining))


__all__ = [
    "maybe_execute_test_worker_run",
    "wait_for_terminal_run",
]
