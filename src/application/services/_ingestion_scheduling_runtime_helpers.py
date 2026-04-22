"""Runtime helpers for ingestion execution, progress, and source locking."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities import ingestion_job, user_data_source

from ._ingestion_scheduling_shared_helpers import (
    normalize_datetime,
    with_failure_metadata,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.domain.services.ingestion import (
        IngestionProgressCallback,
        IngestionProgressEventType,
        IngestionProgressUpdate,
        IngestionRunContext,
        IngestionRunSummary,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)
MIN_POSITIONAL_PARAMETERS_WITH_CONTEXT = 2


class _IngestionSchedulingRuntimeHelpers:
    """Helpers for execution progress, failure handling, and source locks."""

    def _recover_stale_running_jobs(
        self: IngestionSchedulingService,
        *,
        source_id: UUID | None = None,
        as_of: datetime | None = None,
    ) -> int:
        reference = normalize_datetime(as_of or datetime.now(UTC))
        timeout_seconds = self._scheduler_stale_running_timeout_seconds
        if source_id is None:
            candidates = self._job_repository.find_running_jobs(limit=200)
        else:
            recent_jobs = self._job_repository.find_by_source(source_id, limit=50)
            candidates = [
                job
                for job in recent_jobs
                if job.status == ingestion_job.IngestionStatus.RUNNING
            ]

        stale_jobs = [
            job
            for job in candidates
            if self._is_stale_running_job(job=job, as_of=reference)
        ]
        for stale_job in stale_jobs:
            self._mark_running_job_as_timeout_failure(
                running=stale_job,
                timeout_seconds=timeout_seconds,
                timeout_scope="stale_running_recovery",
                timeout_message=(
                    "Ingestion job remained in RUNNING state beyond stale timeout "
                    "threshold and was recovered automatically"
                ),
                timed_out_at=reference,
            )
        return len(stale_jobs)

    def _is_stale_running_job(
        self: IngestionSchedulingService,
        *,
        job: ingestion_job.IngestionJob,
        as_of: datetime,
    ) -> bool:
        if job.status != ingestion_job.IngestionStatus.RUNNING:
            return False
        started_at = normalize_datetime(job.started_at or job.triggered_at)
        elapsed_seconds = (as_of - started_at).total_seconds()
        return elapsed_seconds >= self._scheduler_stale_running_timeout_seconds

    def _mark_running_job_as_timeout_failure(
        self: IngestionSchedulingService,
        *,
        running: ingestion_job.IngestionJob,
        timeout_seconds: int,
        timeout_scope: str,
        timeout_message: str,
        timed_out_at: datetime | None = None,
    ) -> None:
        failure_time = normalize_datetime(timed_out_at or datetime.now(UTC))
        failure_payload: JSONObject = {
            "error_type": "timeout",
            "timeout_seconds": timeout_seconds,
            "timeout_scope": timeout_scope,
            "timed_out_at": failure_time.isoformat(timespec="seconds"),
        }
        error = ingestion_job.IngestionError(
            error_type="timeout",
            error_message=(
                f"{timeout_message} (timeout_seconds={timeout_seconds}, "
                f"scope={timeout_scope})"
            ),
            error_details=failure_payload,
            record_id=None,
        )
        failure_metadata = with_failure_metadata(
            running.metadata,
            failure_payload=failure_payload,
        )
        if running.job_kind == ingestion_job.IngestionJobKind.PIPELINE_ORCHESTRATION:
            pipeline_raw = failure_metadata.get("pipeline_run")
            pipeline_payload = (
                {str(key): value for key, value in pipeline_raw.items()}
                if isinstance(pipeline_raw, dict)
                else {}
            )
            failure_timestamp = failure_time.isoformat(timespec="seconds")
            pipeline_payload["status"] = "failed"
            pipeline_payload["queue_status"] = "failed"
            pipeline_payload["updated_at"] = failure_timestamp
            pipeline_payload["completed_at"] = failure_timestamp
            pipeline_payload["last_error"] = error.error_message
            pipeline_payload["error_category"] = "timeout"
            failure_metadata["pipeline_run"] = pipeline_payload
        failed = running.model_copy(
            update={
                "metadata": failure_metadata,
            },
        ).fail(error)
        self._job_repository.save(failed)
        logger.warning(
            "Ingestion job marked as failed due to timeout",
            extra={
                "job_id": str(running.id),
                "source_id": str(running.source_id),
                "timeout_scope": timeout_scope,
                "timeout_seconds": timeout_seconds,
            },
        )

    def _handle_ingestion_failure(
        self: IngestionSchedulingService,
        *,
        running: ingestion_job.IngestionJob,
        source: user_data_source.UserDataSource,
        error_message: str,
    ) -> None:
        error = ingestion_job.IngestionError(
            error_type="scheduler_failure",
            error_message=error_message,
            record_id=None,
        )
        self._rollback_job_repository_session()
        failed = running.fail(error)
        try:
            self._job_repository.save(failed)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to persist ingestion failure state after rollback",
                extra={
                    "job_id": str(running.id),
                    "source_id": str(source.id),
                },
            )

    def _rollback_job_repository_session(self: IngestionSchedulingService) -> None:
        repository_session = getattr(self._job_repository, "session", None)
        if repository_session is None:
            return
        rollback = getattr(repository_session, "rollback", None)
        if callable(rollback):
            rollback()

    def _build_progress_callback_chain(
        self: IngestionSchedulingService,
        *,
        running: ingestion_job.IngestionJob,
        downstream_progress_callback: IngestionProgressCallback | None,
    ) -> tuple[
        IngestionProgressCallback,
        Callable[[], ingestion_job.IngestionJob],
    ]:
        running_state = running

        def _callback(update: IngestionProgressUpdate) -> None:
            nonlocal running_state
            try:
                running_state = self._persist_running_job_progress(
                    running=running_state,
                    update=update,
                )
            except Exception:  # noqa: BLE001
                self._rollback_job_repository_session()
                logger.warning(
                    "Failed to persist incremental ingestion job progress",
                    extra={
                        "job_id": str(running_state.id),
                        "source_id": str(running_state.source_id),
                        "event_type": update.event_type,
                    },
                    exc_info=True,
                )
            self._emit_progress_update(
                progress_callback=downstream_progress_callback,
                update=update,
            )

        def _get_running_state() -> ingestion_job.IngestionJob:
            return running_state

        return _callback, _get_running_state

    def _persist_running_job_progress(
        self: IngestionSchedulingService,
        *,
        running: ingestion_job.IngestionJob,
        update: IngestionProgressUpdate,
    ) -> ingestion_job.IngestionJob:
        payload = {str(key): value for key, value in dict(update.payload).items()}
        raw_runtime_progress = running.metadata.get("runtime_progress")
        runtime_progress = (
            {str(key): value for key, value in raw_runtime_progress.items()}
            if isinstance(raw_runtime_progress, dict)
            else {}
        )
        runtime_progress.update(
            {
                "event_type": update.event_type,
                "message": update.message,
                "occurred_at": update.occurred_at.isoformat(timespec="seconds"),
                "payload": payload,
            },
        )
        if update.ingestion_job_id is not None:
            runtime_progress["ingestion_job_id"] = str(update.ingestion_job_id)
        if update.event_type == "records_fetched":
            fetched_records = payload.get("fetched_records")
            if isinstance(fetched_records, int):
                runtime_progress["fetched_records"] = max(fetched_records, 0)
        if update.event_type == "source_documents_upserted":
            document_count = payload.get("document_count")
            if isinstance(document_count, int):
                runtime_progress["source_documents_upserted"] = max(document_count, 0)
        if update.event_type == "query_resolved":
            executed_query = payload.get("executed_query")
            if isinstance(executed_query, str) and executed_query.strip():
                runtime_progress["executed_query"] = executed_query.strip()
        if update.event_type == "kernel_ingestion_record_finished":
            record_index = payload.get("record_index")
            if isinstance(record_index, int):
                runtime_progress["kernel_records_finished"] = max(record_index, 0)

        metadata = dict(running.metadata)
        metadata["runtime_progress"] = runtime_progress
        updated_running = running.model_copy(update={"metadata": metadata})
        return self._job_repository.save(updated_running)

    def _acquire_source_lock(
        self: IngestionSchedulingService,
        source_id: UUID,
        *,
        force_recover_lock: bool = False,
    ) -> str | None:
        repository = self._source_lock_repository
        if repository is None:
            self._ensure_source_not_running(source_id)
            return None

        now = datetime.now(UTC)
        lock_token = uuid4().hex
        lease_expires_at = now + timedelta(seconds=self._source_lock_lease_ttl_seconds)
        lock = repository.try_acquire(
            source_id=source_id,
            lock_token=lock_token,
            lease_expires_at=lease_expires_at,
            heartbeat_at=now,
            acquired_by=self._source_lock_owner,
        )
        if (
            lock is None
            and force_recover_lock
            and not self._source_has_running_job(source_id)
        ):
            stale_lock = repository.get_by_source(source_id)
            if (
                stale_lock is not None
                and stale_lock.lease_expires_at.astimezone(UTC) <= now
                and repository.delete_by_source(source_id)
            ):
                logger.warning(
                    "Force-recovered source ingestion lock before retry",
                    extra={
                        "source_id": str(source_id),
                        "stale_lock_expires_at": stale_lock.lease_expires_at.isoformat(
                            timespec="seconds",
                        ),
                        "stale_lock_heartbeat_at": stale_lock.last_heartbeat_at.isoformat(
                            timespec="seconds",
                        ),
                    },
                )
                lock = repository.try_acquire(
                    source_id=source_id,
                    lock_token=lock_token,
                    lease_expires_at=lease_expires_at,
                    heartbeat_at=now,
                    acquired_by=self._source_lock_owner,
                )
        if lock is None:
            msg = f"Ingestion already running for source {source_id}"
            raise ValueError(msg)
        return lock_token

    def _start_source_lock_heartbeat(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
        lock_token: str | None,
    ) -> asyncio.Task[None] | None:
        if lock_token is None or self._source_lock_repository is None:
            return None
        return asyncio.create_task(
            self._run_source_lock_heartbeat(
                source_id=source_id,
                lock_token=lock_token,
            ),
            name=f"ingestion-source-lock-heartbeat-{source_id}",
        )

    async def _run_source_lock_heartbeat(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
        lock_token: str,
    ) -> None:
        repository = self._source_lock_repository
        if repository is None:
            return
        while True:
            await asyncio.sleep(self._source_lock_heartbeat_seconds)
            heartbeat_at = datetime.now(UTC)
            lease_expires_at = heartbeat_at + timedelta(
                seconds=self._source_lock_lease_ttl_seconds,
            )
            refreshed = repository.refresh_lease(
                source_id=source_id,
                lock_token=lock_token,
                lease_expires_at=lease_expires_at,
                heartbeat_at=heartbeat_at,
            )
            if refreshed is None:
                logger.warning(
                    "Lost source ingestion lock lease before run completed",
                    extra={"source_id": str(source_id)},
                )
                return

    def _release_source_lock(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
        lock_token: str,
    ) -> None:
        repository = self._source_lock_repository
        if repository is None:
            return
        released = repository.release(
            source_id=source_id,
            lock_token=lock_token,
        )
        if not released:
            logger.warning(
                "Source ingestion lock release skipped because ownership no longer matched",
                extra={"source_id": str(source_id)},
            )

    def _get_ingestion_service(
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
    ) -> Callable[..., Awaitable[IngestionRunSummary]]:
        service = self._ingestion_services.get(source.source_type)
        if service is None:
            msg = f"No ingestion service registered for {source.source_type}"
            raise ValueError(msg)
        return service

    def _assert_extraction_contract(
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
    ) -> None:
        if self._extraction_queue_service is None:
            msg = (
                "Extraction queue contract is required for all datasource ingestions "
                f"(missing for source type {source.source_type.value})"
            )
            raise ValueError(msg)
        runner = self._extraction_runner_service
        if runner is None:
            msg = (
                "Extraction processor contract is required for all datasource "
                f"ingestions (missing runner for source type {source.source_type.value})"
            )
            raise ValueError(msg)
        if not runner.has_processor_for_source_type(source.source_type.value):
            msg = (
                "No extraction processor contract registered for source type "
                f"{source.source_type.value}"
            )
            raise ValueError(msg)

    async def _invoke_ingestion_service(
        self: IngestionSchedulingService,
        *,
        service: Callable[..., Awaitable[IngestionRunSummary]],
        source: user_data_source.UserDataSource,
        context: IngestionRunContext | None,
    ) -> IngestionRunSummary:
        if context is not None and self._service_accepts_context(service):
            return await service(source, context=context)
        return await service(source)

    @staticmethod
    def _service_accepts_context(
        service: Callable[..., Awaitable[IngestionRunSummary]],
    ) -> bool:
        try:
            signature = inspect.signature(service)
        except (TypeError, ValueError):
            return False
        parameters = signature.parameters
        if "context" in parameters:
            return True
        positional_count = sum(
            1
            for parameter in parameters.values()
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        )
        return positional_count >= MIN_POSITIONAL_PARAMETERS_WITH_CONTEXT

    @staticmethod
    def _build_progress_update(
        *,
        event_type: IngestionProgressEventType,
        message: str,
        occurred_at: datetime | None = None,
        ingestion_job_id: UUID | None = None,
        payload: JSONObject | None = None,
    ) -> IngestionProgressUpdate:
        from src.domain.services.ingestion import IngestionProgressUpdate

        return IngestionProgressUpdate(
            event_type=event_type,
            message=message,
            occurred_at=occurred_at or datetime.now(UTC),
            ingestion_job_id=ingestion_job_id,
            payload=payload or {},
        )

    @staticmethod
    def _emit_progress_update(
        *,
        progress_callback: IngestionProgressCallback | None,
        update: IngestionProgressUpdate,
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(update)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            logger.warning(
                "Failed to emit ingestion progress update %s",
                update.event_type,
                exc_info=True,
            )
