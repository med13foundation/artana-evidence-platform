"""Worker readiness and wake-up helpers for queued runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.process_health import read_heartbeat
from artana_evidence_api.queued_run.constants import (
    _WORKER_HEARTBEAT_PATH,
    _WORKER_MAX_AGE_SECONDS,
    LOGGER,
)
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.run_registry import HarnessRunRecord


def require_worker_ready(*, operation_name: str) -> None:
    """Raise when the background worker heartbeat is stale or missing."""
    worker = read_heartbeat(
        _WORKER_HEARTBEAT_PATH,
        max_age_seconds=_WORKER_MAX_AGE_SECONDS,
    )
    if worker.status == "healthy":
        return
    detail = f"{operation_name} worker unavailable."
    if worker.last_tick is not None:
        detail += f" Last heartbeat: {worker.last_tick}."
    failure_reason = None
    if isinstance(worker.detail, dict):
        raw_reason = worker.detail.get("failure_reason")
        if isinstance(raw_reason, str) and raw_reason != "":
            failure_reason = raw_reason
    if failure_reason == "process_not_running":
        detail += " Worker process is not running."
    elif failure_reason == "stale":
        detail += " Worker heartbeat is stale."
    elif failure_reason == "loop_error":
        detail += " Worker loop is erroring."
    elif worker.status == "unknown":
        detail += " No worker heartbeat is available."
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )


def should_require_worker_ready(*, execution_services: object) -> bool:
    """Return whether production worker readiness should be enforced."""
    return (
        hasattr(execution_services, "execution_override")
        and object.__getattribute__(execution_services, "execution_override") is None
    )


def wake_worker_for_queued_run(
    *,
    run: HarnessRunRecord,
    execution_services: object | None = None,
) -> None:
    """Best-effort wake-up signal for one queued run."""
    if execution_services is not None and not should_require_worker_ready(
        execution_services=execution_services,
    ):
        return
    try:
        from artana_evidence_api.worker_notifications import (
            notify_worker_run_available,
        )

        notified = notify_worker_run_available(
            run_id=run.id,
            space_id=run.space_id,
            harness_id=run.harness_id,
        )
        if not notified:
            LOGGER.warning(
                "Worker wake-up notification was not delivered for queued run %s",
                run.id,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning(
            "Worker wake-up notification failed for queued run %s",
            run.id,
            exc_info=exc,
        )


__all__ = [
    "require_worker_ready",
    "should_require_worker_ready",
    "wake_worker_for_queued_run",
]
