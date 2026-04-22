"""Protocols shared by pipeline orchestration checkpoint helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services._pipeline_orchestration_contracts import (
        PipelineStageName,
        PipelineStageStatus,
    )
    from src.domain.entities.ingestion_job import IngestionJob
    from src.domain.repositories.ingestion_job_repository import IngestionJobRepository
    from src.type_definitions.common import JSONObject


class PipelineCheckpointSelf(Protocol):
    """Structural contract expected by the checkpoint helper mixin."""

    _pipeline_runs: IngestionJobRepository | None

    def _resolve_persistable_run_job(
        self,
        *,
        run_job: IngestionJob | None,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
    ) -> IngestionJob | None: ...

    def _start_or_resume_pipeline_run(
        self,
        *,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
    ) -> IngestionJob | None: ...

    def _find_pipeline_run_job(
        self,
        *,
        source_id: UUID,
        run_id: str,
    ) -> IngestionJob | None: ...

    def _find_active_pipeline_run_job(
        self,
        *,
        source_id: UUID,
        exclude_run_id: str | None = None,
    ) -> IngestionJob | None: ...

    def _cancel_pipeline_run(
        self,
        *,
        source_id: UUID,
        run_id: str,
    ) -> IngestionJob | None: ...

    def _is_pipeline_run_cancelled(
        self,
        *,
        source_id: UUID,
        run_id: str,
    ) -> bool: ...

    def _build_pipeline_metadata(  # noqa: PLR0913
        self,
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
    ) -> JSONObject: ...

    @staticmethod
    def _coerce_json_object(raw_value: object) -> JSONObject: ...

    def _refresh_pipeline_run_job(
        self,
        *,
        source_id: UUID,
        run_id: str,
        run_job: IngestionJob | None,
    ) -> IngestionJob | None: ...

    def _resolve_persisted_overall_status(
        self,
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
    ]: ...


__all__ = ["PipelineCheckpointSelf"]
