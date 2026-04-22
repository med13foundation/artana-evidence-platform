"""Core scheduling helpers for ingestion execution orchestration."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING

from src.domain.entities import ingestion_job, user_data_source

from ._ingestion_scheduling_observability_helpers import (
    _IngestionSchedulingObservabilityHelpers,
)
from ._ingestion_scheduling_runtime_helpers import (
    _IngestionSchedulingRuntimeHelpers,
)
from ._ingestion_scheduling_state_helpers import _IngestionSchedulingStateHelpers

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.application.services.ports.scheduler_port import ScheduledJob
    from src.domain.services.ingestion import (
        IngestionProgressCallback,
        IngestionRunSummary,
    )

logger = logging.getLogger(__name__)
ALREADY_RUNNING_ERROR_FRAGMENT = "already running"


class _IngestionSchedulingCoreHelpers(
    _IngestionSchedulingObservabilityHelpers,
    _IngestionSchedulingRuntimeHelpers,
    _IngestionSchedulingStateHelpers,
):
    """Helpers for orchestrating ingestion execution and summary metadata."""

    async def _execute_job(
        self: IngestionSchedulingService,
        scheduled_job: ScheduledJob,
    ) -> None:
        source = self._get_source(scheduled_job.source_id)
        if source.status != user_data_source.SourceStatus.ACTIVE:
            return
        if (
            source.ingestion_schedule.frequency
            == user_data_source.ScheduleFrequency.MANUAL
        ):
            return
        try:
            await self._run_ingestion_for_source(
                source,
                trigger=ingestion_job.IngestionTrigger.SCHEDULED,
            )
        except ValueError as exc:
            if ALREADY_RUNNING_ERROR_FRAGMENT in str(exc).lower():
                logger.info(
                    "Skipping scheduled ingestion because source lock is held",
                    extra={"source_id": str(source.id)},
                )
                return
            raise

    async def _run_ingestion_for_source(  # noqa: PLR0913,PLR0915
        self: IngestionSchedulingService,
        source: user_data_source.UserDataSource,
        *,
        trigger: ingestion_job.IngestionTrigger = ingestion_job.IngestionTrigger.SCHEDULED,
        skip_post_ingestion_hook: bool = False,
        skip_legacy_extraction_queue: bool = False,
        force_recover_lock: bool = False,
        pipeline_run_id: str | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> IngestionRunSummary:
        self._recover_stale_running_jobs(source_id=source.id)
        self._assert_extraction_contract(source)
        service = self._get_ingestion_service(source)
        lock_token = self._acquire_source_lock(
            source.id,
            force_recover_lock=force_recover_lock,
        )
        lock_heartbeat_task = self._start_source_lock_heartbeat(
            source_id=source.id,
            lock_token=lock_token,
        )

        try:
            job = self._job_repository.save(
                self._create_ingestion_job(source, trigger=trigger),
            )
            running = self._job_repository.save(job.start_execution())
            sync_state_before = self._prepare_sync_state_for_attempt(source)
            callback_chain, get_running_state = self._build_progress_callback_chain(
                running=running,
                downstream_progress_callback=progress_callback,
            )
            run_context = self._build_run_context(
                source=source,
                ingestion_job_id=running.id,
                sync_state=sync_state_before,
                pipeline_run_id=pipeline_run_id,
                progress_callback=callback_chain,
            )
            self._emit_progress_update(
                progress_callback=callback_chain,
                update=self._build_progress_update(
                    event_type="ingestion_job_started",
                    message="Nested ingestion job started.",
                    ingestion_job_id=running.id,
                    payload={
                        "trigger": trigger.value,
                        "pipeline_run_id": pipeline_run_id,
                    },
                ),
            )
            try:
                summary = await asyncio.wait_for(
                    self._invoke_ingestion_service(
                        service=service,
                        source=source,
                        context=run_context,
                    ),
                    timeout=self._ingestion_job_hard_timeout_seconds,
                )
                self._emit_dedup_telemetry(source_id=source.id, summary=summary)
                self._emit_query_generation_telemetry(
                    source_id=source.id,
                    summary=summary,
                )
                if not skip_post_ingestion_hook:
                    await self._run_post_ingestion_hook(
                        source=source,
                        summary=summary,
                    )
                sync_state_after = self._persist_sync_state_on_success(
                    sync_state=sync_state_before,
                    ingestion_job_id=running.id,
                    summary=summary,
                )
                skipped_records = self._int_summary_field(
                    summary,
                    "skipped_records",
                ) + self._int_summary_field(summary, "unchanged_records")
                metrics = ingestion_job.JobMetrics(
                    records_processed=summary.created_publications
                    + summary.updated_publications,
                    records_failed=0,
                    records_skipped=skipped_records,
                    bytes_processed=0,
                    api_calls_made=0,
                    duration_seconds=None,
                    records_per_second=None,
                )
                metadata = self._build_source_metadata(
                    running=running,
                    source=source,
                    summary=summary,
                    sync_state_before=sync_state_before,
                    sync_state_after=sync_state_after,
                )

                if not skip_legacy_extraction_queue:
                    extraction_metadata = self._enqueue_extraction(
                        source=source,
                        ingestion_job_id=running.id,
                        summary=summary,
                    )
                    if extraction_metadata:
                        metadata = metadata.model_copy(
                            update={"extraction_queue": extraction_metadata},
                        )
                        extraction_run = await self._run_extraction(
                            source=source,
                            ingestion_job_id=running.id,
                            queued_count=extraction_metadata.queued,
                        )
                        if extraction_run:
                            metadata = metadata.model_copy(
                                update={"extraction_run": extraction_run},
                            )

                latest_running_state = get_running_state()
                completed_metadata = dict(latest_running_state.metadata)
                completed_metadata.update(metadata.to_json_object())
                completed = latest_running_state.model_copy(
                    update={"metadata": completed_metadata},
                ).complete_successfully(metrics)
            except TimeoutError:
                latest_running_state = get_running_state()
                self._mark_running_job_as_timeout_failure(
                    running=latest_running_state,
                    timeout_seconds=self._ingestion_job_hard_timeout_seconds,
                    timeout_scope="ingestion_job_hard_timeout",
                    timeout_message=(
                        "Ingestion invocation exceeded the hard timeout window"
                    ),
                )
                raise
            except Exception as exc:
                latest_running_state = get_running_state()
                self._handle_ingestion_failure(
                    running=latest_running_state,
                    source=source,
                    error_message=str(exc),
                )
                raise
            else:
                self._job_repository.save(completed)
                updated_source = (
                    self._source_repository.record_ingestion(source.id) or source
                )
                self._update_schedule_after_run(updated_source)
                return summary
        finally:
            if lock_heartbeat_task is not None:
                lock_heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await lock_heartbeat_task
            if lock_token is not None:
                self._release_source_lock(source_id=source.id, lock_token=lock_token)

    async def _run_post_ingestion_hook(
        self: IngestionSchedulingService,
        *,
        source: user_data_source.UserDataSource,
        summary: IngestionRunSummary,
    ) -> None:
        hook = self._post_ingestion_hook
        if hook is None:
            return
        try:
            await asyncio.wait_for(
                hook(source, summary),
                timeout=self._post_ingestion_hook_timeout_seconds,
            )
        except TimeoutError as exc:
            logger.exception(
                "Post-ingestion hook timed out",
                extra={
                    "source_id": str(source.id),
                    "timeout_seconds": self._post_ingestion_hook_timeout_seconds,
                },
            )
            msg = (
                "Post-ingestion hook timed out after "
                f"{self._post_ingestion_hook_timeout_seconds}s for source {source.id}"
            )
            raise RuntimeError(msg) from exc
        except Exception as exc:
            logger.exception(
                "Post-ingestion hook failed",
                extra={"source_id": str(source.id)},
            )
            msg = f"Post-ingestion hook failed for source {source.id}: {exc!s}"
            raise RuntimeError(msg) from exc

    def _source_has_running_job(
        self: IngestionSchedulingService,
        source_id: UUID,
    ) -> bool:
        recent_jobs = self._job_repository.find_by_source(source_id, limit=10)
        return any(
            job.status == ingestion_job.IngestionStatus.RUNNING for job in recent_jobs
        )

    def _ensure_source_not_running(
        self: IngestionSchedulingService,
        source_id: UUID,
    ) -> None:
        if self._source_has_running_job(source_id):
            msg = f"Ingestion already running for source {source_id}"
            raise ValueError(msg)
