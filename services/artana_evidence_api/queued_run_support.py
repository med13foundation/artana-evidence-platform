"""Shared helpers for queue-first harness execution and sync wait fallback."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.config import get_settings
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.process_health import read_heartbeat
from artana_evidence_api.response_serialization import serialize_run_record
from artana_evidence_api.types.common import JSONObject
from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

LOGGER = logging.getLogger(__name__)
_WORKER_HEARTBEAT_PATH = "logs/artana-evidence-api-worker-heartbeat.json"
_WORKER_MAX_AGE_SECONDS = 120.0
_ACTIVE_RUN_STATUSES = frozenset({"queued", "running"})
_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "paused"})
_TEST_WORKER_ID = "queue-wait-test-worker"
_PRIMARY_RESULT_WORKSPACE_KEY = "primary_result_key"
_RESULT_KEYS_WORKSPACE_KEY = "result_keys"
_RESPOND_ASYNC_PREFER_TOKEN = "respond-async"


class HarnessAcceptedRunResponse(BaseModel):
    """Generic accepted response when the sync wait budget expires."""

    model_config = ConfigDict(strict=True)

    run: JSONObject
    progress_url: str = Field(..., min_length=1)
    events_url: str = Field(..., min_length=1)
    workspace_url: str = Field(..., min_length=1)
    artifacts_url: str = Field(..., min_length=1)
    stream_url: str | None = None
    session: JSONObject | None = None


@dataclass(frozen=True, slots=True)
class QueuedRunWaitOutcome:
    """Result of waiting on a queued worker-owned run."""

    run: HarnessRunRecord | None
    timed_out: bool


def _normalized_result_keys(
    *,
    primary_result_key: str,
    result_keys: list[str] | tuple[str, ...],
) -> list[str]:
    normalized_keys: list[str] = []
    for key in (primary_result_key, *result_keys):
        if not isinstance(key, str):
            continue
        trimmed = key.strip()
        if trimmed == "" or trimmed in normalized_keys:
            continue
        normalized_keys.append(trimmed)
    return normalized_keys


def prefers_respond_async(prefer: str | None) -> bool:
    """Return whether the request explicitly prefers async acceptance."""
    if not isinstance(prefer, str):
        return False
    for directive in prefer.split(","):
        token = directive.strip()
        if token == "":
            continue
        token_name = token.split(";", 1)[0].strip().lower()
        if token_name == _RESPOND_ASYNC_PREFER_TOKEN:
            return True
    return False


def progress_url(*, space_id: UUID | str, run_id: UUID | str) -> str:
    """Return the relative progress URL for one run."""
    return f"/v1/spaces/{space_id}/runs/{run_id}/progress"


def events_url(*, space_id: UUID | str, run_id: UUID | str) -> str:
    """Return the relative events URL for one run."""
    return f"/v1/spaces/{space_id}/runs/{run_id}/events"


def workspace_url(*, space_id: UUID | str, run_id: UUID | str) -> str:
    """Return the relative workspace URL for one run."""
    return f"/v1/spaces/{space_id}/runs/{run_id}/workspace"


def artifacts_url(*, space_id: UUID | str, run_id: UUID | str) -> str:
    """Return the relative artifacts URL for one run."""
    return f"/v1/spaces/{space_id}/runs/{run_id}/artifacts"


def build_accepted_run_response(
    *,
    run: HarnessRunRecord,
    run_registry: HarnessRunRegistry | None = None,
    stream_url: str | None = None,
    session: JSONObject | None = None,
) -> HarnessAcceptedRunResponse:
    """Build the generic accepted response for one queued run."""
    current_run = (
        run_registry.get_run(space_id=run.space_id, run_id=run.id)
        if run_registry is not None
        else None
    )
    response_run = current_run or run
    return HarnessAcceptedRunResponse(
        run=serialize_run_record(run=response_run),
        progress_url=progress_url(
            space_id=response_run.space_id,
            run_id=response_run.id,
        ),
        events_url=events_url(space_id=response_run.space_id, run_id=response_run.id),
        workspace_url=workspace_url(
            space_id=response_run.space_id,
            run_id=response_run.id,
        ),
        artifacts_url=artifacts_url(
            space_id=response_run.space_id,
            run_id=response_run.id,
        ),
        stream_url=stream_url,
        session=session,
    )


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


def store_primary_result_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID | str,
    run_id: UUID | str,
    artifact_key: str,
    content: JSONObject,
    status_value: str,
    result_keys: list[str] | tuple[str, ...] = (),
    workspace_patch: JSONObject | None = None,
) -> None:
    """Store one primary result artifact and record standardized workspace keys."""
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=artifact_key,
        media_type="application/json",
        content=content,
    )
    patch: JSONObject = {
        "status": status_value,
        _PRIMARY_RESULT_WORKSPACE_KEY: artifact_key,
        _RESULT_KEYS_WORKSPACE_KEY: _normalized_result_keys(
            primary_result_key=artifact_key,
            result_keys=result_keys,
        ),
        "error": None,
    }
    if workspace_patch is not None:
        patch.update(workspace_patch)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch=patch,
    )


def load_primary_result_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID | str,
    run_id: UUID | str,
) -> JSONObject:
    """Load the standardized primary result artifact content for one run."""
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace for run '{run_id}' was not found.",
        )
    primary_result_key = workspace.snapshot.get(_PRIMARY_RESULT_WORKSPACE_KEY)
    if not isinstance(primary_result_key, str) or primary_result_key.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' does not expose a primary result artifact yet.",
        )
    artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=primary_result_key,
    )
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Primary result artifact '{primary_result_key}' for run '{run_id}' "
                "is missing."
            ),
        )
    return artifact.content


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


def raise_for_failed_run(
    *,
    run: HarnessRunRecord,
    artifact_store: HarnessArtifactStore,
) -> None:
    """Raise an HTTPException based on the stored worker failure details."""
    worker_error = artifact_store.get_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="worker_error",
    )
    if worker_error is not None:
        status_code = worker_error.content.get("status_code")
        detail = worker_error.content.get("detail") or worker_error.content.get("error")
        if isinstance(status_code, int) and isinstance(detail, str):
            raise HTTPException(status_code=status_code, detail=detail)
        if isinstance(detail, str):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=detail,
            )
    workspace = artifact_store.get_workspace(space_id=run.space_id, run_id=run.id)
    if workspace is not None:
        raw_error = workspace.snapshot.get("error")
        raw_status_code = workspace.snapshot.get("error_status_code")
        if isinstance(raw_error, str) and raw_error.strip() != "":
            if isinstance(raw_status_code, int):
                raise HTTPException(
                    status_code=raw_status_code,
                    detail=raw_error,
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=raw_error,
            )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Run '{run.id}' failed without a persisted error payload.",
    )


def worker_failure_payload(*, exc: Exception) -> JSONObject:
    """Return a structured persisted worker failure payload."""
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return {
            "error": detail,
            "detail": detail,
            "status_code": exc.status_code,
            "error_type": type(exc).__name__,
        }
    if isinstance(exc, GraphServiceClientError):
        detail = exc.detail or str(exc)
        return {
            "error": detail,
            "detail": detail,
            "status_code": exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
            "error_type": type(exc).__name__,
        }
    status_code = _specialized_worker_failure_status_code(exc=exc)
    if status_code is not None:
        detail = str(exc)
        return {
            "error": detail,
            "detail": detail,
            "status_code": status_code,
            "error_type": type(exc).__name__,
        }
    return {
        "error": str(exc),
        "detail": str(exc),
        "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "error_type": type(exc).__name__,
    }


def _specialized_worker_failure_status_code(*, exc: Exception) -> int | None:
    """Return legacy route semantics for domain-specific worker failures."""
    from artana_evidence_api.chat_graph_write_workflow import (
        ChatGraphWriteArtifactError,
        ChatGraphWriteCandidateError,
        ChatGraphWriteVerificationError,
    )
    from artana_evidence_api.claim_curation_workflow import (
        ClaimCurationNoEligibleProposalsError,
    )
    from artana_evidence_api.research_onboarding_agent_runtime import (
        OnboardingAgentExecutionError,
    )
    from artana_evidence_api.run_budget import HarnessRunBudgetExceededError

    if isinstance(exc, OnboardingAgentExecutionError):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if isinstance(exc, HarnessRunBudgetExceededError):
        return status.HTTP_409_CONFLICT
    if isinstance(exc, ClaimCurationNoEligibleProposalsError):
        return status.HTTP_409_CONFLICT
    if isinstance(exc, ChatGraphWriteCandidateError):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(exc, ChatGraphWriteArtifactError | ChatGraphWriteVerificationError):
        return status.HTTP_409_CONFLICT
    return None


__all__ = [
    "HarnessAcceptedRunResponse",
    "QueuedRunWaitOutcome",
    "artifacts_url",
    "build_accepted_run_response",
    "events_url",
    "load_primary_result_artifact",
    "maybe_execute_test_worker_run",
    "prefers_respond_async",
    "progress_url",
    "raise_for_failed_run",
    "require_worker_ready",
    "should_require_worker_ready",
    "store_primary_result_artifact",
    "wait_for_terminal_run",
    "wake_worker_for_queued_run",
    "worker_failure_payload",
    "workspace_url",
]
