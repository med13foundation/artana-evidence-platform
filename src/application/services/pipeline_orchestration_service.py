"""Unified orchestration service for end-to-end source pipeline execution."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.application.services._pipeline_orchestration_checkpoint_helpers import (
    _PipelineOrchestrationCheckpointHelpers,
)
from src.application.services._pipeline_orchestration_contracts import (
    PipelineRunSummary,
    PipelineStageName,
    PipelineStageStatus,
)
from src.application.services._pipeline_orchestration_execution_helpers import (
    _PipelineOrchestrationExecutionHelpers,
)
from src.application.services._pipeline_orchestration_queue_metadata import (
    build_requested_args_payload,
    resolve_pipeline_attempt_count,
    resolve_pipeline_run_id_from_job,
    resolve_queued_request,
    update_pipeline_metadata_fields,
)
from src.application.services._pipeline_orchestration_queue_types import (
    DEFAULT_PIPELINE_QUEUE_MAX_SIZE,
    DEFAULT_PIPELINE_QUEUE_RETRY_AFTER_SECONDS,
    DEFAULT_PIPELINE_RETRY_BASE_DELAY_SECONDS,
    DEFAULT_PIPELINE_RETRY_MAX_ATTEMPTS,
    ENV_PIPELINE_QUEUE_MAX_SIZE,
    ENV_PIPELINE_QUEUE_RETRY_AFTER_SECONDS,
    ENV_PIPELINE_RETRY_BASE_DELAY_SECONDS,
    ENV_PIPELINE_RETRY_MAX_ATTEMPTS,
    ActivePipelineRunExistsError,
    PipelineOrchestrationDependencies,
    PipelineQueueFullError,
    PipelineRunEnqueueResult,
    QueuedPipelineRunRequest,
    read_positive_int_env,
)
from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionJobKind,
    IngestionStatus,
    IngestionTrigger,
)
from src.domain.value_objects.provenance import DataSource, Provenance
from src.type_definitions.data_sources import (
    PipelineRunCostMetadata,
    PipelineRunTimingMetadata,
)

if TYPE_CHECKING:
    from src.domain.repositories.ingestion_job_repository import IngestionJobRepository

logger = logging.getLogger(__name__)


class PipelineOrchestrationService(
    _PipelineOrchestrationExecutionHelpers,
    _PipelineOrchestrationCheckpointHelpers,
):
    """Run ingestion -> enrichment -> extraction -> graph stages with one run id."""

    def __init__(self, dependencies: PipelineOrchestrationDependencies) -> None:
        self._ingestion = dependencies.ingestion_scheduling_service
        self._enrichment = dependencies.content_enrichment_service
        self._extraction = dependencies.entity_recognition_service
        self._enrichment_stage_runner = dependencies.content_enrichment_stage_runner
        self._extraction_stage_runner = dependencies.entity_recognition_stage_runner
        self._graph = dependencies.graph_connection_service
        self._graph_seed_runner = dependencies.graph_connection_seed_runner
        self._graph_search = dependencies.graph_search_service
        self._research_spaces = dependencies.research_space_repository
        self._pipeline_runs = dependencies.pipeline_run_repository
        self._pipeline_trace = dependencies.pipeline_trace_service

    def enqueue_run(  # noqa: PLR0913
        self,
        *,
        source_id: UUID,
        research_space_id: UUID,
        triggered_by_user_id: UUID | None = None,
        run_id: str | None = None,
        resume_from_stage: PipelineStageName | None = None,
        enrichment_limit: int = 25,
        extraction_limit: int = 25,
        source_type: str | None = None,
        model_id: str | None = None,
        shadow_mode: bool | None = None,
        force_recover_lock: bool = False,
        graph_seed_entity_ids: list[str] | None = None,
        graph_max_depth: int = 2,
        graph_relation_types: list[str] | None = None,
    ) -> PipelineRunEnqueueResult:
        repository = self._require_pipeline_repository()
        normalized_run_id = self._resolve_run_id(run_id)
        active_job = repository.find_active_pipeline_job_for_source(
            source_id=source_id,
        )
        if active_job is not None:
            active_run_id = resolve_pipeline_run_id_from_job(active_job)
            raise ActivePipelineRunExistsError(run_id=active_run_id)

        queue_max_size = read_positive_int_env(
            ENV_PIPELINE_QUEUE_MAX_SIZE,
            default_value=DEFAULT_PIPELINE_QUEUE_MAX_SIZE,
        )
        if repository.count_active_pipeline_queue_jobs() >= queue_max_size:
            raise PipelineQueueFullError(
                retry_after_seconds=read_positive_int_env(
                    ENV_PIPELINE_QUEUE_RETRY_AFTER_SECONDS,
                    default_value=DEFAULT_PIPELINE_QUEUE_RETRY_AFTER_SECONDS,
                ),
            )

        normalized_resume_stage = self._resolve_resume_stage(resume_from_stage)
        accepted_at = datetime.now(UTC)
        requested_args = build_requested_args_payload(
            resume_from_stage=normalized_resume_stage,
            enrichment_limit=enrichment_limit,
            extraction_limit=extraction_limit,
            source_type=source_type,
            model_id=model_id,
            shadow_mode=shadow_mode,
            force_recover_lock=force_recover_lock,
            graph_seed_entity_ids=graph_seed_entity_ids,
            graph_max_depth=graph_max_depth,
            graph_relation_types=graph_relation_types,
        )
        metadata = self._build_pipeline_metadata(
            existing_metadata={},
            run_id=normalized_run_id,
            research_space_id=research_space_id,
            resume_from_stage=normalized_resume_stage,
            overall_status="queued",
            stage_updates={},
        )
        metadata = update_pipeline_metadata_fields(
            existing_metadata=metadata,
            requested_args=requested_args,
            accepted_at=accepted_at.isoformat(timespec="seconds"),
            attempt_count=0,
            next_attempt_at=None,
            worker_id=None,
            last_error=None,
            error_category=None,
        )
        if self._pipeline_trace is not None:
            owner_summary = self._pipeline_trace.resolve_run_owner(
                source_id=source_id,
                triggered_by_user_id=triggered_by_user_id,
            )
            metadata = update_pipeline_metadata_fields(
                existing_metadata=metadata,
                owner=owner_summary.to_json_object(),
                timing_summary=PipelineRunTimingMetadata().to_json_object(),
                cost_summary=PipelineRunCostMetadata().to_json_object(),
            )
        job = IngestionJob(
            id=uuid4(),
            source_id=source_id,
            job_kind=IngestionJobKind.PIPELINE_ORCHESTRATION,
            trigger=IngestionTrigger.API,
            triggered_by=triggered_by_user_id,
            triggered_at=accepted_at,
            status=IngestionStatus.PENDING,
            started_at=None,
            completed_at=None,
            provenance=Provenance(
                source=DataSource.COMPUTED,
                source_version=None,
                source_url=None,
                acquired_by="pipeline_orchestration_service",
                processing_steps=("pipeline_orchestration", "queued_execution"),
                quality_score=None,
                metadata={"run_id": normalized_run_id},
            ),
            metadata=metadata,
            source_config_snapshot={},
        )
        saved_job = repository.save(job)
        if self._pipeline_trace is not None:
            self._pipeline_trace.record_event(
                research_space_id=research_space_id,
                source_id=source_id,
                pipeline_run_id=normalized_run_id,
                event_type="run_queued",
                scope_kind="run",
                message="Pipeline run accepted and queued for execution.",
                status="queued",
                payload={
                    "accepted_at": accepted_at.isoformat(timespec="seconds"),
                    "resume_from_stage": normalized_resume_stage,
                    "triggered_by_user_id": (
                        str(triggered_by_user_id)
                        if triggered_by_user_id is not None
                        else None
                    ),
                },
            )
        return PipelineRunEnqueueResult(
            run_id=normalized_run_id,
            source_id=saved_job.source_id,
            research_space_id=research_space_id,
            status="queued",
            accepted_at=accepted_at,
        )

    def claim_next_queued_run(
        self,
        *,
        worker_id: str,
        as_of: datetime | None = None,
    ) -> IngestionJob | None:
        repository = self._require_pipeline_repository()
        claimed_at = as_of or datetime.now(UTC)
        claimed_job = repository.claim_next_pipeline_job(
            worker_id=worker_id,
            as_of=claimed_at,
        )
        if claimed_job is None or self._pipeline_trace is None:
            return claimed_job
        try:
            queued_request = self._resolve_queued_request(claimed_job)
            queue_wait_ms = max(
                int((claimed_at - claimed_job.triggered_at).total_seconds() * 1000),
                0,
            )
            self._pipeline_trace.record_event(
                research_space_id=queued_request.research_space_id,
                source_id=claimed_job.source_id,
                pipeline_run_id=queued_request.run_id,
                event_type="run_claimed",
                stage="ingestion",
                scope_kind="run",
                message="Worker claimed queued pipeline run for execution.",
                status="claimed",
                occurred_at=claimed_at,
                started_at=claimed_at,
                queue_wait_ms=queue_wait_ms,
                payload={
                    "worker_id": worker_id,
                    "accepted_at": claimed_job.triggered_at.isoformat(
                        timespec="seconds",
                    ),
                    "claimed_at": claimed_at.isoformat(timespec="seconds"),
                },
            )
        except (AttributeError, RuntimeError, TypeError, ValueError, SQLAlchemyError):
            logger.warning(
                "Failed to record pipeline run claim event for job_id=%s worker_id=%s",
                claimed_job.id,
                worker_id,
                exc_info=True,
            )
        return claimed_job

    def heartbeat_claimed_run(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        heartbeat_at: datetime | None = None,
    ) -> IngestionJob | None:
        repository = self._require_pipeline_repository()
        return repository.heartbeat_pipeline_job(
            job_id=job_id,
            worker_id=worker_id,
            heartbeat_at=heartbeat_at or datetime.now(UTC),
        )

    async def run_next_queued_job(
        self,
        *,
        worker_id: str,
    ) -> bool:
        claimed_job = self.claim_next_queued_run(
            worker_id=worker_id,
            as_of=datetime.now(UTC),
        )
        if claimed_job is None:
            return False
        await self.execute_claimed_run(claimed_job=claimed_job, worker_id=worker_id)
        return True

    async def execute_claimed_run(
        self,
        *,
        claimed_job: IngestionJob,
        worker_id: str,
    ) -> None:
        repository = self._require_pipeline_repository()

        queued_request = self._resolve_queued_request(claimed_job)
        try:
            summary = await self.run_for_source(
                source_id=claimed_job.source_id,
                research_space_id=queued_request.research_space_id,
                run_id=queued_request.run_id,
                resume_from_stage=queued_request.resume_from_stage,
                enrichment_limit=queued_request.enrichment_limit,
                extraction_limit=queued_request.extraction_limit,
                source_type=queued_request.source_type,
                model_id=queued_request.model_id,
                shadow_mode=queued_request.shadow_mode,
                force_recover_lock=queued_request.force_recover_lock,
                graph_seed_entity_ids=queued_request.graph_seed_entity_ids,
                graph_max_depth=queued_request.graph_max_depth,
                graph_relation_types=queued_request.graph_relation_types,
            )
        except Exception as exc:  # noqa: BLE001 - worker must settle queue state
            error_message = str(exc).strip() or exc.__class__.__name__
            error_category = resolve_pipeline_error_category((error_message,))
            if error_category == "capacity" and self._should_retry_job(claimed_job):
                self._mark_job_retryable(
                    job_id=claimed_job.id,
                    worker_id=worker_id,
                    attempt_count=resolve_pipeline_attempt_count(claimed_job),
                    last_error=error_message,
                    error_category=error_category,
                )
            else:
                self._mark_claimed_job_failed(
                    claimed_job=claimed_job,
                    worker_id=worker_id,
                    error_message=error_message,
                    error_category=error_category,
                )
            return

        error_category = resolve_pipeline_error_category(summary.errors)
        if summary.status == "failed" and error_category == "capacity":
            current_job = repository.find_by_id(claimed_job.id) or claimed_job
            if self._should_retry_job(current_job):
                self._mark_job_retryable(
                    job_id=claimed_job.id,
                    worker_id=worker_id,
                    attempt_count=resolve_pipeline_attempt_count(current_job),
                    last_error=summary.errors[-1] if summary.errors else "capacity",
                    error_category=error_category,
                )
        return

    def cancel_run(
        self,
        *,
        source_id: UUID,
        run_id: str,
    ) -> IngestionJob | None:
        normalized_run_id = run_id.strip()
        if not normalized_run_id:
            return None
        return self._cancel_pipeline_run(
            source_id=source_id,
            run_id=normalized_run_id,
        )

    def _require_pipeline_repository(self) -> IngestionJobRepository:
        if self._pipeline_runs is None:
            msg = "Pipeline run repository is not configured"
            raise RuntimeError(msg)
        return self._pipeline_runs

    def _mark_job_retryable(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        attempt_count: int,
        last_error: str,
        error_category: str | None,
    ) -> IngestionJob | None:
        retry_delay_seconds = read_positive_int_env(
            ENV_PIPELINE_RETRY_BASE_DELAY_SECONDS,
            default_value=DEFAULT_PIPELINE_RETRY_BASE_DELAY_SECONDS,
        ) * (2 ** max(attempt_count, 0))
        return self._require_pipeline_repository().mark_pipeline_job_retryable(
            job_id=job_id,
            worker_id=worker_id,
            next_attempt_at=datetime.now(UTC) + timedelta(seconds=retry_delay_seconds),
            last_error=last_error,
            error_category=error_category,
        )

    def _mark_claimed_job_failed(
        self,
        *,
        claimed_job: IngestionJob,
        worker_id: str,
        error_message: str,
        error_category: str | None,
    ) -> IngestionJob:
        repository = self._require_pipeline_repository()
        current_job = repository.find_by_id(claimed_job.id) or claimed_job
        failed_job = current_job.fail(
            IngestionError(
                error_type="pipeline_worker_failed",
                error_message=error_message,
                error_details={
                    "worker_id": worker_id,
                    "error_category": error_category,
                },
                record_id=None,
            ),
        )
        updated_metadata = update_pipeline_metadata_fields(
            existing_metadata=failed_job.metadata,
            status="failed",
            queue_status="failed",
            worker_id=worker_id,
            last_error=error_message,
            error_category=error_category,
            completed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        return repository.save(
            failed_job.model_copy(update={"metadata": updated_metadata}),
        )

    def _should_retry_job(self, job: IngestionJob) -> bool:
        max_attempts = read_positive_int_env(
            ENV_PIPELINE_RETRY_MAX_ATTEMPTS,
            default_value=DEFAULT_PIPELINE_RETRY_MAX_ATTEMPTS,
        )
        return resolve_pipeline_attempt_count(job) < max_attempts

    def _resolve_queued_request(self, job: IngestionJob) -> QueuedPipelineRunRequest:
        return resolve_queued_request(
            job=job,
            resolve_resume_stage=self._resolve_resume_stage,
            request_type=QueuedPipelineRunRequest,
        )


__all__ = [
    "ActivePipelineRunExistsError",
    "PipelineOrchestrationDependencies",
    "PipelineQueueFullError",
    "PipelineRunEnqueueResult",
    "PipelineOrchestrationService",
    "PipelineRunSummary",
    "PipelineStageName",
    "PipelineStageStatus",
]
