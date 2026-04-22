"""Protocols for unified pipeline orchestration execution helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from src.application.agents.services._content_enrichment_types import (
        ContentEnrichmentRunSummary,
    )
    from src.application.agents.services.content_enrichment_service import (
        ContentEnrichmentService,
    )
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionRunSummary,
        EntityRecognitionService,
    )
    from src.application.agents.services.graph_connection_service import (
        GraphConnectionOutcome,
    )
    from src.application.services._pipeline_orchestration_contracts import (
        PipelineStageName,
        PipelineStageStatus,
    )
    from src.application.services._pipeline_orchestration_graph_stage_helpers import (
        _GraphStageInput,
        _GraphStageOutput,
    )
    from src.application.services._pipeline_orchestration_queue_types import (
        GraphConnectionExecutor,
        GraphSearchExecutor,
    )
    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.application.services.pipeline_run_trace_service import (
        PipelineRunTraceService,
    )
    from src.domain.entities.ingestion_job import IngestionJob
    from src.domain.repositories.research_space_repository import (
        ResearchSpaceRepository,
    )
    from src.type_definitions.common import JSONObject


class _PipelineExecutionSelf(Protocol):
    _ingestion: IngestionSchedulingService
    _enrichment: ContentEnrichmentService
    _extraction: EntityRecognitionService
    _enrichment_stage_runner: (
        Callable[..., Awaitable[ContentEnrichmentRunSummary]] | None
    )
    _extraction_stage_runner: (
        Callable[..., Awaitable[EntityRecognitionRunSummary]] | None
    )
    _graph: GraphConnectionExecutor | None
    _graph_seed_runner: Callable[..., Awaitable[GraphConnectionOutcome]] | None
    _graph_search: GraphSearchExecutor | None
    _research_spaces: ResearchSpaceRepository | None
    _pipeline_trace: PipelineRunTraceService | None

    def _start_or_resume_pipeline_run(
        self,
        *,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
    ) -> IngestionJob | None: ...

    def _persist_pipeline_stage_checkpoint(  # noqa: PLR0913
        self,
        *,
        run_job: IngestionJob | None,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
        stage: PipelineStageName,
        stage_status: PipelineStageStatus,
        overall_status: Literal["running", "completed", "failed"],
        stage_error: str | None = None,
    ) -> IngestionJob | None: ...

    def _persist_pipeline_run_progress(  # noqa: PLR0913
        self,
        *,
        run_job: IngestionJob | None,
        source_id: UUID,
        research_space_id: UUID,
        run_id: str,
        resume_from_stage: PipelineStageName | None,
        progress_key: str,
        progress_payload: JSONObject,
        overall_status: Literal[
            "running",
            "completed",
            "failed",
            "cancelled",
        ] = "running",
    ) -> IngestionJob | None: ...

    async def _run_graph_stage(
        self,
        *,
        graph_stage_input: _GraphStageInput,
    ) -> _GraphStageOutput: ...

    def _finalize_pipeline_run_checkpoint(  # noqa: PLR0913
        self,
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
    ) -> IngestionJob | None: ...

    def _is_pipeline_run_cancelled(
        self,
        *,
        source_id: UUID,
        run_id: str,
    ) -> bool: ...

    @staticmethod
    def _resolve_run_id(raw_run_id: str | None) -> str: ...

    @staticmethod
    def _resolve_resume_stage(
        resume_from_stage: PipelineStageName | None,
    ) -> PipelineStageName | None: ...

    @staticmethod
    def _should_run_stage(
        *,
        stage: PipelineStageName,
        resume_from_stage: PipelineStageName | None,
    ) -> bool: ...

    @classmethod
    def _normalize_graph_seed_entity_ids(
        cls,
        seed_entity_ids: list[str] | None,
    ) -> list[str]: ...

    @classmethod
    def _extract_seed_entity_ids_from_extraction_summary(
        cls,
        extraction_summary: object,
    ) -> list[str]: ...

    async def _infer_seed_entity_ids_with_context(
        self,
        *,
        source_id: UUID,
        research_space_id: UUID,
        source_type: str | None,
        model_id: str | None,
    ) -> list[str]: ...

    def _build_seed_inference_prompt(
        self,
        *,
        source_id: UUID,
        research_space_id: UUID,
        source_type: str | None,
    ) -> str: ...

    @classmethod
    def _extract_seed_entity_ids_from_graph_search(
        cls,
        search_contract: object,
    ) -> list[str]: ...

    def _resolve_research_space_summary(
        self,
        *,
        research_space_id: UUID,
    ) -> str: ...

    def _resolve_recent_run_query_hints(
        self,
        *,
        source_id: UUID,
    ) -> tuple[str, ...]: ...

    @staticmethod
    def _extract_job_query_hint(
        *,
        metadata: object,
    ) -> str | None: ...


__all__ = ["_PipelineExecutionSelf"]
