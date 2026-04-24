"""Worker-driven execution for queued graph-harness runs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from artana_evidence_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from artana_evidence_api.composition import (
    GraphHarnessKernelRuntime,
    get_graph_harness_kernel_runtime,
)
from artana_evidence_api.config import get_settings
from artana_evidence_api.database import SessionLocal, set_session_rls_context
from artana_evidence_api.dependencies import get_document_binary_store
from artana_evidence_api.graph_chat_runtime import HarnessGraphChatRunner
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRunner,
)
from artana_evidence_api.graph_integration.context import (
    GraphCallContext,
    make_graph_transport_bundle_factory,
)
from artana_evidence_api.graph_search_runtime import HarnessGraphSearchRunner
from artana_evidence_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
    execute_harness_run,
)
from artana_evidence_api.models import HarnessRunModel
from artana_evidence_api.queued_run_support import worker_failure_payload
from artana_evidence_api.research_onboarding_agent_runtime import (
    HarnessResearchOnboardingRunner,
)
from artana_evidence_api.run_registry import HarnessRunRecord
from artana_evidence_api.sqlalchemy_stores import (
    SqlAlchemyHarnessApprovalStore,
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessDocumentStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessProposalStore,
    SqlAlchemyHarnessResearchStateStore,
    SqlAlchemyHarnessScheduleStore,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from artana_evidence_api.worker_notifications import (
    WorkerQueueNotificationListener,
    open_worker_queue_notification_listener,
)
from fastapi import HTTPException
from sqlalchemy import select

if TYPE_CHECKING:
    from collections.abc import Iterator

    from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
    from artana_evidence_api.run_registry import HarnessRunRegistry
    from sqlalchemy.orm import Session

LOGGER = logging.getLogger(__name__)
_DEFAULT_WORKER_ID = "artana-evidence-api-worker"
_DEFAULT_LEASE_TTL_SECONDS = 300
_WORKER_FAILURE_ARTIFACT_KEY = "worker_error"
_WORKER_HEARTBEAT_PATH = "logs/artana-evidence-api-worker-heartbeat.json"
_WORKER_HEARTBEAT_KEEPALIVE_SECONDS = 15.0
_WORKER_EXECUTABLE_HARNESSES = (
    "full-ai-orchestrator",
    "research-init",
    "research-bootstrap",
    "research-onboarding",
    "graph-chat",
    "graph-connections",
    "graph-search",
    "hypotheses",
    "continuous-learning",
    "mechanism-discovery",
    "claim-curation",
    "supervisor",
)


@dataclass(frozen=True, slots=True)
class WorkerRunResult:
    """One run processed or skipped by the worker."""

    run_id: str
    space_id: str
    harness_id: str
    outcome: str
    message: str | None


@dataclass(frozen=True, slots=True)
class WorkerTickResult:
    """Summary of one worker tick."""

    started_at: datetime
    completed_at: datetime
    scanned_run_count: int
    leased_run_count: int
    executed_run_count: int
    completed_run_count: int
    failed_run_count: int
    skipped_run_count: int
    results: tuple[WorkerRunResult, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ServiceWorkerTickContext:
    """Prepared durable dependencies for one service worker tick.

    Built by the sync ``_service_worker_tick_context`` context manager and
    consumed by the async ``run_worker_tick``.  The context holds a live
    SQLAlchemy session, so it must stay open for the duration of the tick.
    """

    candidate_runs: list[HarnessRunRecord]
    runtime: GraphHarnessKernelRuntime
    services: HarnessExecutionServices


def _build_worker_services(
    *,
    session: Session,
    execution_override: WorkerExecutionCallable | None = None,
) -> tuple[GraphHarnessKernelRuntime, HarnessExecutionServices]:
    """Build one durable worker-owned service bundle for the active session."""
    runtime = get_graph_harness_kernel_runtime()
    services = HarnessExecutionServices(
        runtime=runtime,
        run_registry=ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime),
        artifact_store=ArtanaBackedHarnessArtifactStore(runtime=runtime),
        chat_session_store=SqlAlchemyHarnessChatSessionStore(session),
        document_store=SqlAlchemyHarnessDocumentStore(session),
        proposal_store=SqlAlchemyHarnessProposalStore(session),
        approval_store=SqlAlchemyHarnessApprovalStore(session),
        research_state_store=SqlAlchemyHarnessResearchStateStore(session),
        graph_snapshot_store=SqlAlchemyHarnessGraphSnapshotStore(session),
        schedule_store=SqlAlchemyHarnessScheduleStore(session),
        graph_connection_runner=HarnessGraphConnectionRunner(),
        graph_search_runner=HarnessGraphSearchRunner(),
        graph_chat_runner=HarnessGraphChatRunner(),
        research_onboarding_runner=HarnessResearchOnboardingRunner(),
        graph_api_gateway_factory=make_graph_transport_bundle_factory(
            # Queued worker runs execute after the request-response cycle, so
            # there is no live caller identity to bind to graph transport.
            # Use an explicit service-owned admin context for background graph
            # reads/writes after the run has already been scoped to one
            # authorized harness space.
            call_context=GraphCallContext.service(graph_admin=True),
        ),
        pubmed_discovery_service_factory=lambda: _pubmed_discovery_service_context(),
        document_binary_store=get_document_binary_store(),
        execution_override=execution_override,
    )
    return runtime, services


WorkerExecutionCallable = Callable[
    [HarnessRunRecord, HarnessExecutionServices],
    Awaitable[HarnessExecutionResult],
]


def _worker_error_message(run: HarnessRunRecord, exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return f"run:{run.id}:{detail}"
    return f"run:{run.id}:{exc}"


def _run_result_message(*, exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return str(exc)


def _result_from_run(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
    message: str | None = None,
) -> WorkerRunResult:
    refreshed = (
        services.run_registry.get_run(space_id=run.space_id, run_id=run.id) or run
    )
    return WorkerRunResult(
        run_id=refreshed.id,
        space_id=refreshed.space_id,
        harness_id=refreshed.harness_id,
        outcome=refreshed.status,
        message=message,
    )


def _require_queued_run(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessRunRecord:
    current_run = services.run_registry.get_run(
        space_id=run.space_id,
        run_id=run.id,
    )
    if current_run is None or current_run.status != "queued":
        msg = f"Run '{run.id}' is no longer queued."
        raise RuntimeError(msg)
    return current_run


_MAX_RETRIES = 3
_RETRY_BACKOFF_MINUTES = [5, 15, 45]


def _resolved_worker_failure_payload(
    *,
    error_message: str,
    exc: Exception | None,
    retry_count: int,
) -> tuple[dict[str, object], int | None]:
    payload = (
        dict(worker_failure_payload(exc=exc))
        if exc is not None
        else {
            "error": error_message,
            "detail": error_message,
            "status_code": 500,
            "error_type": "RuntimeError",
        }
    )
    if not isinstance(payload.get("error"), str) or payload["error"] == "":
        payload["error"] = error_message
    if not isinstance(payload.get("detail"), str) or payload["detail"] == "":
        payload["detail"] = error_message
    payload["retry_count"] = retry_count
    raw_status_code = payload.get("status_code")
    status_code = raw_status_code if isinstance(raw_status_code, int) else None
    return cast("dict[str, object]", payload), status_code


def _persist_worker_failure_metadata(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
    error_message: str,
    exc: Exception | None,
    retry_count: int,
    preserve_existing_error: bool,
) -> None:
    payload, status_code = _resolved_worker_failure_payload(
        error_message=error_message,
        exc=exc,
        retry_count=retry_count,
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key=_WORKER_FAILURE_ARTIFACT_KEY,
        media_type="application/json",
        content=cast("JSONObject", payload),
    )
    workspace = services.artifact_store.get_workspace(
        space_id=run.space_id,
        run_id=run.id,
    )
    workspace_error = workspace.snapshot.get("error") if workspace is not None else None
    patch: JSONObject = {
        "status": "failed",
        "error_status_code": status_code,
        "last_error_key": _WORKER_FAILURE_ARTIFACT_KEY,
        "_retry_count": retry_count,
    }
    if (
        not preserve_existing_error
        or not isinstance(workspace_error, str)
        or workspace_error.strip() == ""
    ):
        patch["error"] = error_message
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch=patch,
    )


def _mark_failed_run_after_worker_exception(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
    error_message: str,
    exc: Exception | None = None,
) -> HarnessRunRecord:
    current_run = services.run_registry.get_run(space_id=run.space_id, run_id=run.id)
    if current_run is None:
        return run
    current_status = current_run.status.strip().lower()
    if current_status not in {"queued", "running"}:
        if current_status == "failed":
            workspace = services.artifact_store.get_workspace(
                space_id=run.space_id,
                run_id=run.id,
            )
            retry_count = 0
            if workspace is not None:
                raw_retry_count = workspace.snapshot.get("_retry_count")
                if isinstance(raw_retry_count, int):
                    retry_count = raw_retry_count
            _persist_worker_failure_metadata(
                run=run,
                services=services,
                error_message=error_message,
                exc=exc,
                retry_count=retry_count,
                preserve_existing_error=True,
            )
        return current_run

    # --- Retry logic: only retry scheduled runs (have schedule_id) ---
    workspace = services.artifact_store.get_workspace(
        space_id=run.space_id,
        run_id=run.id,
    )
    retry_count = 0
    is_scheduled_run = False
    if workspace and isinstance(workspace.snapshot, dict):
        retry_count_value = workspace.snapshot.get("_retry_count", 0)
        retry_count = retry_count_value if type(retry_count_value) is int else 0
        is_scheduled_run = bool(workspace.snapshot.get("schedule_id"))
    # Also check input_payload for schedule_id
    if not is_scheduled_run and isinstance(run.input_payload, dict):
        is_scheduled_run = bool(run.input_payload.get("schedule_id"))

    if is_scheduled_run and retry_count < _MAX_RETRIES:
        backoff_minutes = _RETRY_BACKOFF_MINUTES[
            min(retry_count, len(_RETRY_BACKOFF_MINUTES) - 1)
        ]
        retry_count += 1
        LOGGER.warning(
            "Run %s failed (attempt %d/%d), re-queuing with %dm backoff: %s",
            run.id,
            retry_count,
            _MAX_RETRIES,
            backoff_minutes,
            error_message,
        )
        services.artifact_store.patch_workspace(
            space_id=run.space_id,
            run_id=run.id,
            patch={
                "_retry_count": retry_count,
                "_retry_not_before": (
                    datetime.now(UTC)
                    + __import__("datetime").timedelta(minutes=backoff_minutes)
                ).isoformat(),
                "_last_error": error_message,
            },
        )
        services.run_registry.set_run_status(
            space_id=run.space_id,
            run_id=run.id,
            status="queued",
        )
        return (
            services.run_registry.get_run(space_id=run.space_id, run_id=run.id)
            or current_run
        )

    # --- Permanent failure after max retries ---
    LOGGER.error(
        "Run %s failed permanently after %d attempts: %s",
        run.id,
        retry_count,
        error_message,
    )
    current_progress = services.run_registry.get_progress(
        space_id=run.space_id,
        run_id=run.id,
    )
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="failed",
        existing_progress=current_progress,
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="failed",
        message=error_message,
        progress_percent=(
            current_progress.progress_percent if current_progress is not None else 0.0
        ),
        completed_steps=(
            current_progress.completed_steps if current_progress is not None else 0
        ),
        total_steps=(
            current_progress.total_steps if current_progress is not None else None
        ),
        clear_resume_point=True,
        metadata={"error": error_message, "retry_count": retry_count},
    )
    _persist_worker_failure_metadata(
        run=run,
        services=services,
        error_message=error_message,
        exc=exc,
        retry_count=retry_count,
        preserve_existing_error=False,
    )
    return (
        services.run_registry.get_run(space_id=run.space_id, run_id=run.id)
        or current_run
    )


async def _default_execute_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    return await execute_harness_run(run=run, services=services)


@contextmanager
def _service_worker_tick_context() -> Iterator[_ServiceWorkerTickContext]:
    """Build worker services and keep their session alive for one async tick.

    This is a **sync** context manager.  ``run_service_worker_tick`` calls it
    inside ``asyncio.to_thread`` so the blocking SQLAlchemy I/O (session
    creation, ``list_queued_worker_runs``) does not stall the event loop.
    """
    with SessionLocal() as session:
        set_session_rls_context(session, bypass_rls=False)
        runtime, services = _build_worker_services(session=session)
        candidate_runs = list_queued_worker_runs(
            session=session,
            run_registry=services.run_registry,
        )
        yield _ServiceWorkerTickContext(
            candidate_runs=candidate_runs,
            runtime=runtime,
            services=services,
        )


def list_queued_worker_runs(
    *,
    session: Session,
    run_registry: HarnessRunRegistry,
) -> list[HarnessRunRecord]:
    """Return queued runs eligible for worker execution."""
    del run_registry
    stmt = (
        select(HarnessRunModel)
        .where(HarnessRunModel.harness_id.in_(_WORKER_EXECUTABLE_HARNESSES))
        .where(HarnessRunModel.status == "queued")
        .order_by(HarnessRunModel.created_at.asc())
    )
    models = session.execute(stmt).scalars().all()
    return [
        HarnessRunRecord(
            id=model.id,
            space_id=model.space_id,
            harness_id=model.harness_id,
            title=model.title,
            status=model.status,
            input_payload=(
                model.input_payload if isinstance(model.input_payload, dict) else {}
            ),
            graph_service_status=model.graph_service_status,
            graph_service_version=model.graph_service_version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        for model in models
    ]


async def execute_worker_run(  # noqa: PLR0913
    *,
    run: HarnessRunRecord,
    runtime: GraphHarnessKernelRuntime,
    services: HarnessExecutionServices,
    worker_id: str = _DEFAULT_WORKER_ID,
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_SECONDS,
    execute_run: WorkerExecutionCallable = _default_execute_run,
) -> HarnessExecutionResult:
    """Execute one queued run after acquiring the Artana worker lease."""
    resolved_execute_run = services.execution_override or execute_run
    acquired = runtime.acquire_run_lease(
        run_id=run.id,
        tenant_id=run.space_id,
        worker_id=worker_id,
        ttl_seconds=lease_ttl_seconds,
    )
    if not acquired:
        msg = f"Lease already held for run '{run.id}'."
        raise RuntimeError(msg)
    try:
        current_run = _require_queued_run(run=run, services=services)
        return await resolved_execute_run(current_run, services)
    except Exception as exc:
        _mark_failed_run_after_worker_exception(
            run=run,
            services=services,
            error_message=_run_result_message(exc=exc),
            exc=exc,
        )
        raise
    finally:
        runtime.release_run_lease(
            run_id=run.id,
            tenant_id=run.space_id,
            worker_id=worker_id,
        )


async def run_worker_tick(  # noqa: PLR0913
    *,
    candidate_runs: list[HarnessRunRecord],
    runtime: GraphHarnessKernelRuntime,
    services: HarnessExecutionServices,
    worker_id: str = _DEFAULT_WORKER_ID,
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_SECONDS,
    execute_run: WorkerExecutionCallable = _default_execute_run,
) -> WorkerTickResult:
    """Execute queued runs after acquiring an Artana worker lease."""
    started_at = datetime.now(UTC)
    resolved_execute_run = services.execution_override or execute_run
    leased_run_count = 0
    executed_run_count = 0
    completed_run_count = 0
    failed_run_count = 0
    skipped_run_count = 0
    results: list[WorkerRunResult] = []
    errors: list[str] = []

    for run in candidate_runs:
        try:
            acquired = runtime.acquire_run_lease(
                run_id=run.id,
                tenant_id=run.space_id,
                worker_id=worker_id,
                ttl_seconds=lease_ttl_seconds,
            )
        except (TimeoutError, ValueError):
            try:
                runtime.ensure_run(run_id=run.id, tenant_id=run.space_id)
                acquired = runtime.acquire_run_lease(
                    run_id=run.id,
                    tenant_id=run.space_id,
                    worker_id=worker_id,
                    ttl_seconds=lease_ttl_seconds,
                )
            except (TimeoutError, ValueError):
                skipped_run_count += 1
                results.append(
                    WorkerRunResult(
                        run_id=run.id,
                        space_id=run.space_id,
                        harness_id=run.harness_id,
                        outcome="lease_skipped",
                        message=(
                            "Timed out acquiring the Artana run lease; "
                            "leaving the run queued for a later retry."
                        ),
                    ),
                )
                continue
        if not acquired:
            skipped_run_count += 1
            results.append(
                WorkerRunResult(
                    run_id=run.id,
                    space_id=run.space_id,
                    harness_id=run.harness_id,
                    outcome="lease_skipped",
                    message="Lease already held by another worker.",
                ),
            )
            continue
        leased_run_count += 1
        try:
            current_run = services.run_registry.get_run(
                space_id=run.space_id,
                run_id=run.id,
            )
            if current_run is None or current_run.status != "queued":
                skipped_run_count += 1
                results.append(
                    WorkerRunResult(
                        run_id=run.id,
                        space_id=run.space_id,
                        harness_id=run.harness_id,
                        outcome="skipped",
                        message="Run is no longer queued.",
                    ),
                )
                continue
            executed_run_count += 1
            await resolved_execute_run(current_run, services)
            worker_result = _result_from_run(run=current_run, services=services)
            if worker_result.outcome == "completed":
                completed_run_count += 1
            elif worker_result.outcome == "failed":
                failed_run_count += 1
            results.append(worker_result)
        except Exception as exc:  # noqa: BLE001
            failed_run_count += 1
            errors.append(_worker_error_message(run, exc))
            _mark_failed_run_after_worker_exception(
                run=run,
                services=services,
                error_message=_run_result_message(exc=exc),
                exc=exc,
            )
            results.append(
                _result_from_run(
                    run=run,
                    services=services,
                    message=_run_result_message(exc=exc),
                ),
            )
        finally:
            runtime.release_run_lease(
                run_id=run.id,
                tenant_id=run.space_id,
                worker_id=worker_id,
            )

    return WorkerTickResult(
        started_at=started_at,
        completed_at=datetime.now(UTC),
        scanned_run_count=len(candidate_runs),
        leased_run_count=leased_run_count,
        executed_run_count=executed_run_count,
        completed_run_count=completed_run_count,
        failed_run_count=failed_run_count,
        skipped_run_count=skipped_run_count,
        results=tuple(results),
        errors=tuple(errors),
    )


async def run_service_worker_tick(
    *,
    worker_id: str = _DEFAULT_WORKER_ID,
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_SECONDS,
) -> WorkerTickResult:
    """Run one worker tick against the service's durable stores.

    The sync ``_service_worker_tick_context`` (SQLAlchemy session creation and
    ``list_queued_worker_runs``) is offloaded to a thread so it never blocks
    the caller's event loop.  The async ``run_worker_tick`` then executes on
    the caller's loop, reusing the same long-lived loop across ticks.
    """
    ctx_manager = _service_worker_tick_context()
    context: _ServiceWorkerTickContext = await asyncio.to_thread(
        ctx_manager.__enter__,
    )
    try:
        result = await run_worker_tick(
            candidate_runs=context.candidate_runs,
            runtime=context.runtime,
            services=context.services,
            worker_id=worker_id,
            lease_ttl_seconds=lease_ttl_seconds,
        )
    except BaseException:
        await asyncio.to_thread(ctx_manager.__exit__, *sys.exc_info())
        raise
    await asyncio.to_thread(ctx_manager.__exit__, None, None, None)
    return result


@contextmanager
def _pubmed_discovery_service_context() -> Iterator[PubMedDiscoveryService]:
    from artana_evidence_api.dependencies import get_pubmed_discovery_service

    generator = get_pubmed_discovery_service()
    service = next(generator)
    try:
        yield service
    finally:
        generator.close()


def _write_heartbeat(path: str, last_result: JSONObject) -> None:
    """Write a heartbeat JSON file for health monitoring."""
    heartbeat_path = Path(path)
    try:
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        with heartbeat_path.open("w") as f:
            json.dump(
                {
                    "last_tick_at": datetime.now(UTC).isoformat(),
                    "pid": os.getpid(),
                    "last_result": last_result,
                },
                f,
            )
    except OSError:
        pass


def _success_heartbeat_payload(result: WorkerTickResult) -> JSONObject:
    return {
        "loop_status": "ok",
        "scanned": result.scanned_run_count,
        "executed": result.executed_run_count,
        "completed": result.completed_run_count,
        "failed": result.failed_run_count,
        "errors": len(result.errors),
    }


def _error_heartbeat_payload(exc: Exception) -> JSONObject:
    return {
        "loop_status": "error",
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _working_heartbeat_payload(*, worker_id: str) -> JSONObject:
    return {
        "loop_status": "working",
        "worker_id": worker_id,
    }


@asynccontextmanager
async def _heartbeat_keepalive(
    *,
    path: str,
    interval_seconds: float,
    payload_factory: Callable[[], JSONObject],
) -> AsyncIterator[None]:
    stop_event = asyncio.Event()

    async def _keepalive() -> None:
        while True:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                if stop_event.is_set():
                    break
                _write_heartbeat(path, payload_factory())
                continue
            break

    task = asyncio.create_task(_keepalive())
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def _wait_for_next_worker_tick(
    *,
    listener: WorkerQueueNotificationListener | None,
    poll_seconds: float,
) -> WorkerQueueNotificationListener | None:
    if listener is None:
        await asyncio.sleep(poll_seconds)
        return None
    try:
        await asyncio.to_thread(listener.wait, poll_seconds)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning(
            "Harness worker queue listener failed; falling back to poll sleep",
            exc_info=exc,
        )
        await asyncio.to_thread(listener.close)
        await asyncio.sleep(poll_seconds)
        return None
    else:
        return listener


async def run_worker_loop(
    *,
    poll_seconds: float,
    run_once: bool,
    worker_id: str = _DEFAULT_WORKER_ID,
    lease_ttl_seconds: int = _DEFAULT_LEASE_TTL_SECONDS,
) -> None:
    """Run the worker loop until stopped or after one tick."""
    if poll_seconds <= 0:
        msg = "poll_seconds must be greater than zero"
        raise ValueError(msg)
    listener: WorkerQueueNotificationListener | None = None
    try:
        while True:
            if listener is None:
                listener = await asyncio.to_thread(
                    open_worker_queue_notification_listener,
                )
            _write_heartbeat(
                _WORKER_HEARTBEAT_PATH,
                _working_heartbeat_payload(worker_id=worker_id),
            )
            try:
                async with _heartbeat_keepalive(
                    path=_WORKER_HEARTBEAT_PATH,
                    interval_seconds=_WORKER_HEARTBEAT_KEEPALIVE_SECONDS,
                    payload_factory=lambda: _working_heartbeat_payload(
                        worker_id=worker_id,
                    ),
                ):
                    result = await run_service_worker_tick(
                        worker_id=worker_id,
                        lease_ttl_seconds=lease_ttl_seconds,
                    )
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception(
                    "Harness worker tick failed",
                    extra={
                        "worker_id": worker_id,
                        "lease_ttl_seconds": lease_ttl_seconds,
                    },
                )
                _write_heartbeat(
                    _WORKER_HEARTBEAT_PATH,
                    _error_heartbeat_payload(exc),
                )
                if run_once:
                    return
                listener = await _wait_for_next_worker_tick(
                    listener=listener,
                    poll_seconds=poll_seconds,
                )
                continue
            LOGGER.info(
                "Harness worker tick completed: scanned=%s leased=%s executed=%s completed=%s failed=%s skipped=%s errors=%s",
                result.scanned_run_count,
                result.leased_run_count,
                result.executed_run_count,
                result.completed_run_count,
                result.failed_run_count,
                result.skipped_run_count,
                len(result.errors),
            )
            _write_heartbeat(
                _WORKER_HEARTBEAT_PATH,
                _success_heartbeat_payload(result),
            )
            if run_once:
                return
            listener = await _wait_for_next_worker_tick(
                listener=listener,
                poll_seconds=poll_seconds,
            )
    finally:
        if listener is not None:
            await asyncio.to_thread(listener.close)


def main() -> None:
    """Start the queued-run worker loop."""
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    try:
        asyncio.run(
            run_worker_loop(
                poll_seconds=settings.worker_poll_seconds,
                run_once=settings.worker_run_once,
                worker_id=settings.worker_id,
                lease_ttl_seconds=settings.worker_lease_ttl_seconds,
            ),
        )
    except Exception:
        LOGGER.exception("Harness worker exited unexpectedly")
        raise


if __name__ == "__main__":
    main()


__all__ = [
    "WorkerRunResult",
    "WorkerTickResult",
    "execute_worker_run",
    "list_queued_worker_runs",
    "main",
    "run_service_worker_tick",
    "run_worker_loop",
    "run_worker_tick",
]
