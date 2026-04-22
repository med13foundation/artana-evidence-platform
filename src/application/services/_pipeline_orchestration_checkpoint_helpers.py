"""Checkpoint helpers for unified pipeline orchestration."""

# mypy: disable-error-code="misc"

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.application.services._pipeline_orchestration_checkpoint_metadata import (
    build_pipeline_metadata,
    coerce_json_object,
)
from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionJobKind,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from src.domain.value_objects.provenance import DataSource, Provenance

if TYPE_CHECKING:
    from src.application.services._pipeline_orchestration_checkpoint_protocols import (
        PipelineCheckpointSelf,
    )
    from src.application.services._pipeline_orchestration_contracts import (
        PipelineStageName,
        PipelineStageStatus,
    )
    from src.type_definitions.common import JSONObject


class _PipelineOrchestrationCheckpointHelpers:
    """Checkpoint persistence helpers for unified pipeline runs."""

    def _resolve_persistable_run_job(
        self: PipelineCheckpointSelf,
        *,
        run_job: IngestionJob | None,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
    ) -> IngestionJob | None:
        resolved_run_job = self._refresh_pipeline_run_job(
            source_id=source_id,
            run_id=run_id,
            run_job=run_job,
        )
        if resolved_run_job is not None:
            return resolved_run_job
        started_run_job = self._start_or_resume_pipeline_run(
            source_id=source_id,
            research_space_id=research_space_id,
            run_id=run_id,
            resume_from_stage=resume_from_stage,
        )
        if started_run_job is None:
            return None
        refreshed_run_job = self._refresh_pipeline_run_job(
            source_id=source_id,
            run_id=run_id,
            run_job=started_run_job,
        )
        return refreshed_run_job if refreshed_run_job is not None else started_run_job

    def _refresh_pipeline_run_job(
        self: PipelineCheckpointSelf,
        *,
        source_id: UUID,
        run_id: str,
        run_job: IngestionJob | None,
    ) -> IngestionJob | None:
        latest = self._find_pipeline_run_job(source_id=source_id, run_id=run_id)
        if latest is not None:
            return latest
        return run_job

    def _resolve_persisted_overall_status(
        self: PipelineCheckpointSelf,
        *,
        run_job: IngestionJob | None,
        requested_status: Literal[
            "queued",
            "retrying",
            "running",
            "completed",
            "failed",
            "cancelled",
        ],
    ) -> Literal[
        "queued",
        "retrying",
        "running",
        "completed",
        "failed",
        "cancelled",
    ]:
        if run_job is not None and run_job.status == IngestionStatus.CANCELLED:
            return "cancelled"
        return requested_status

    def _start_or_resume_pipeline_run(
        self: PipelineCheckpointSelf,
        *,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
    ) -> IngestionJob | None:
        repository = self._pipeline_runs
        if repository is None:
            return None

        existing = self._find_pipeline_run_job(source_id=source_id, run_id=run_id)
        if existing is None:
            active_run = self._find_active_pipeline_run_job(
                source_id=source_id,
                exclude_run_id=run_id,
            )
            if active_run is not None:
                active_metadata = self._coerce_json_object(active_run.metadata)
                active_pipeline_payload = active_metadata.get("pipeline_run")
                active_run_id = None
                if isinstance(active_pipeline_payload, dict):
                    stored_run_id = active_pipeline_payload.get("run_id")
                    if isinstance(stored_run_id, str) and stored_run_id.strip():
                        active_run_id = stored_run_id.strip()
                active_identifier = active_run_id or str(active_run.id)
                msg = (
                    "An active pipeline run already exists for this source "
                    f"(run_id={active_identifier})"
                )
                raise ValueError(msg)
            created = IngestionJob(
                id=uuid4(),
                source_id=source_id,
                job_kind=IngestionJobKind.PIPELINE_ORCHESTRATION,
                trigger=IngestionTrigger.API,
                triggered_by=None,
                triggered_at=datetime.now(UTC),
                status=IngestionStatus.PENDING,
                started_at=None,
                completed_at=None,
                provenance=Provenance(
                    source=DataSource.COMPUTED,
                    source_version=None,
                    source_url=None,
                    acquired_by="pipeline_orchestration_service",
                    processing_steps=("pipeline_orchestration",),
                    quality_score=None,
                    metadata={"run_id": run_id},
                ),
                metadata=self._build_pipeline_metadata(
                    existing_metadata={},
                    run_id=run_id,
                    research_space_id=research_space_id,
                    resume_from_stage=resume_from_stage,
                    overall_status="running",
                    stage_updates={},
                ),
                source_config_snapshot={},
            )
            return repository.save(created.start_execution())

        resumed = (
            existing
            if existing.status in {IngestionStatus.RUNNING, IngestionStatus.CANCELLED}
            else existing.start_execution()
        )
        resumed_metadata = self._build_pipeline_metadata(
            existing_metadata=resumed.metadata,
            run_id=run_id,
            research_space_id=research_space_id,
            resume_from_stage=resume_from_stage,
            overall_status=self._resolve_persisted_overall_status(
                run_job=resumed,
                requested_status="running",
            ),
            stage_updates={},
        )
        return repository.save(
            resumed.model_copy(update={"metadata": resumed_metadata}),
        )

    def _persist_pipeline_stage_checkpoint(  # noqa: PLR0913
        self: PipelineCheckpointSelf,
        *,
        run_job: IngestionJob | None,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
        stage: PipelineStageName,
        stage_status: PipelineStageStatus,
        overall_status: Literal["running", "completed", "failed", "cancelled"],
        stage_error: str | None = None,
    ) -> IngestionJob | None:
        repository = self._pipeline_runs
        if repository is None:
            return run_job
        resolved_run_job = self._resolve_persistable_run_job(
            run_job=run_job,
            source_id=source_id,
            research_space_id=research_space_id,
            run_id=run_id,
            resume_from_stage=resume_from_stage,
        )
        if resolved_run_job is None:
            return None

        updated_metadata = self._build_pipeline_metadata(
            existing_metadata=resolved_run_job.metadata,
            run_id=run_id,
            research_space_id=research_space_id,
            resume_from_stage=resume_from_stage,
            overall_status=self._resolve_persisted_overall_status(
                run_job=resolved_run_job,
                requested_status=overall_status,
            ),
            stage_updates={stage: (stage_status, stage_error)},
        )
        return repository.save(
            resolved_run_job.model_copy(update={"metadata": updated_metadata}),
        )

    def _persist_pipeline_run_progress(  # noqa: PLR0913
        self: PipelineCheckpointSelf,
        *,
        run_job: IngestionJob | None,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
        progress_key: str,
        progress_payload: JSONObject,
        overall_status: Literal[
            "queued",
            "retrying",
            "running",
            "completed",
            "failed",
            "cancelled",
        ] = "running",
    ) -> IngestionJob | None:
        repository = self._pipeline_runs
        if repository is None:
            return run_job
        resolved_run_job = self._resolve_persistable_run_job(
            run_job=run_job,
            source_id=source_id,
            research_space_id=research_space_id,
            run_id=run_id,
            resume_from_stage=resume_from_stage,
        )
        if resolved_run_job is None:
            return None

        updated_metadata = self._build_pipeline_metadata(
            existing_metadata=resolved_run_job.metadata,
            run_id=run_id,
            research_space_id=research_space_id,
            resume_from_stage=resume_from_stage,
            overall_status=self._resolve_persisted_overall_status(
                run_job=resolved_run_job,
                requested_status=overall_status,
            ),
            stage_updates={},
        )
        pipeline_raw = updated_metadata.get("pipeline_run")
        pipeline_payload = (
            self._coerce_json_object(pipeline_raw)
            if isinstance(pipeline_raw, dict)
            else {}
        )
        pipeline_payload[progress_key] = self._coerce_json_object(progress_payload)
        if overall_status in {"completed", "cancelled"}:
            pipeline_payload["last_error"] = None
            pipeline_payload["error_category"] = None
        pipeline_payload["updated_at"] = datetime.now(UTC).isoformat(
            timespec="seconds",
        )
        updated_metadata["pipeline_run"] = pipeline_payload
        return repository.save(
            resolved_run_job.model_copy(update={"metadata": updated_metadata}),
        )

    def _finalize_pipeline_run_checkpoint(  # noqa: PLR0913
        self: PipelineCheckpointSelf,
        *,
        run_job: IngestionJob | None,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
        run_status: Literal["completed", "failed", "cancelled"],
        errors: tuple[str, ...],
        created_publications: int,
        updated_publications: int,
        extraction_extracted: int,
        graph_persisted_relations: int,
    ) -> IngestionJob | None:
        repository = self._pipeline_runs
        if repository is None:
            return run_job
        resolved_run_job = self._resolve_persistable_run_job(
            run_job=run_job,
            source_id=source_id,
            research_space_id=research_space_id,
            run_id=run_id,
            resume_from_stage=resume_from_stage,
        )
        if resolved_run_job is None:
            return None

        updated_metadata = self._build_pipeline_metadata(
            existing_metadata=resolved_run_job.metadata,
            run_id=run_id,
            research_space_id=research_space_id,
            resume_from_stage=resume_from_stage,
            overall_status=self._resolve_persisted_overall_status(
                run_job=resolved_run_job,
                requested_status=run_status,
            ),
            stage_updates={},
        )
        pipeline_raw = updated_metadata.get("pipeline_run")
        pipeline_payload = (
            self._coerce_json_object(pipeline_raw)
            if isinstance(pipeline_raw, dict)
            else {}
        )
        if run_status == "failed" and errors:
            pipeline_payload["last_error"] = errors[-1]
        else:
            pipeline_payload["last_error"] = None
        error_category = resolve_pipeline_error_category(errors)
        if run_status == "failed" and error_category is not None:
            pipeline_payload["error_category"] = error_category
        else:
            pipeline_payload["error_category"] = None
        updated_metadata["pipeline_run"] = pipeline_payload
        working = resolved_run_job.model_copy(update={"metadata": updated_metadata})
        metrics = JobMetrics(
            records_processed=max(
                created_publications
                + updated_publications
                + extraction_extracted
                + graph_persisted_relations,
                0,
            ),
            records_failed=0 if run_status == "completed" else len(errors),
            records_skipped=0,
            bytes_processed=0,
            api_calls_made=0,
            duration_seconds=None,
            records_per_second=None,
        )

        if run_status == "completed":
            return repository.save(working.complete_successfully(metrics))
        if run_status == "cancelled":
            cancelled = working.cancel()
            return repository.save(cancelled.model_copy(update={"metrics": metrics}))

        failed = working.fail(
            IngestionError(
                error_type="pipeline_failed",
                error_message="Unified pipeline run completed with failures",
                error_details={"errors": list(errors)},
                record_id=None,
            ),
        )
        return repository.save(failed.model_copy(update={"metrics": metrics}))

    def _cancel_pipeline_run(
        self: PipelineCheckpointSelf,
        *,
        source_id: UUID,
        run_id: str,
    ) -> IngestionJob | None:
        repository = self._pipeline_runs
        if repository is None:
            return None
        existing = self._find_pipeline_run_job(source_id=source_id, run_id=run_id)
        if existing is None:
            return None
        if existing.status in {
            IngestionStatus.COMPLETED,
            IngestionStatus.FAILED,
            IngestionStatus.CANCELLED,
            IngestionStatus.PARTIAL,
        }:
            return existing
        cancelled = repository.cancel_job(existing.id)
        if cancelled is None:
            return None
        updated_metadata = self._coerce_json_object(cancelled.metadata)
        pipeline_raw = updated_metadata.get("pipeline_run")
        pipeline_payload = (
            self._coerce_json_object(pipeline_raw)
            if isinstance(pipeline_raw, dict)
            else {}
        )
        pipeline_payload["run_id"] = run_id
        pipeline_payload["status"] = "cancelled"
        pipeline_payload["queue_status"] = "cancelled"
        pipeline_payload["updated_at"] = datetime.now(UTC).isoformat(
            timespec="seconds",
        )
        updated_metadata["pipeline_run"] = pipeline_payload
        return repository.save(
            cancelled.model_copy(update={"metadata": updated_metadata}),
        )

    def _is_pipeline_run_cancelled(
        self: PipelineCheckpointSelf,
        *,
        source_id: UUID,
        run_id: str,
    ) -> bool:
        existing = self._find_pipeline_run_job(source_id=source_id, run_id=run_id)
        if existing is None:
            return False
        return existing.status == IngestionStatus.CANCELLED

    def _find_pipeline_run_job(
        self: PipelineCheckpointSelf,
        *,
        source_id: UUID,
        run_id: str,
    ) -> IngestionJob | None:
        repository = self._pipeline_runs
        if repository is None:
            return None
        for candidate in repository.find_latest_by_source_and_kind(
            source_id=source_id,
            job_kind=IngestionJobKind.PIPELINE_ORCHESTRATION,
            limit=200,
        ):
            metadata = self._coerce_json_object(candidate.metadata)
            pipeline_payload = metadata.get("pipeline_run")
            if not isinstance(pipeline_payload, dict):
                continue
            stored_run_id = pipeline_payload.get("run_id")
            if isinstance(stored_run_id, str) and stored_run_id.strip() == run_id:
                return candidate
        return None

    def _find_active_pipeline_run_job(
        self: PipelineCheckpointSelf,
        *,
        source_id: UUID,
        exclude_run_id: str | None = None,
    ) -> IngestionJob | None:
        repository = self._pipeline_runs
        if repository is None:
            return None
        return repository.find_active_pipeline_job_for_source(
            source_id=source_id,
            exclude_run_id=exclude_run_id,
        )

    def _build_pipeline_metadata(  # noqa: PLR0913
        self: PipelineCheckpointSelf,
        *,
        existing_metadata: object,
        run_id: str,
        research_space_id: UUID,
        resume_from_stage: PipelineStageName | None,
        overall_status: Literal[
            "queued",
            "retrying",
            "running",
            "completed",
            "failed",
            "cancelled",
        ],
        stage_updates: dict[PipelineStageName, tuple[PipelineStageStatus, str | None]],
    ) -> JSONObject:
        return build_pipeline_metadata(
            existing_metadata=existing_metadata,
            run_id=run_id,
            research_space_id=research_space_id,
            resume_from_stage=resume_from_stage,
            overall_status=overall_status,
            stage_updates=stage_updates,
        )

    @staticmethod
    def _coerce_json_object(raw_value: object) -> JSONObject:
        return coerce_json_object(raw_value)
