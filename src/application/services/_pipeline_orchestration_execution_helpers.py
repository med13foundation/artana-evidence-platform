"""Execution helpers for unified pipeline orchestration."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.services._pipeline_orchestration_enrichment_stage import (
    run_enrichment_stage,
)
from src.application.services._pipeline_orchestration_execution_finalization import (
    finalize_pipeline_run,
)
from src.application.services._pipeline_orchestration_execution_models import (
    PipelineExecutionContext,
    PipelineExecutionState,
)
from src.application.services._pipeline_orchestration_execution_runtime import (
    PipelineExecutionRuntime,
)
from src.application.services._pipeline_orchestration_extraction_stage import (
    run_extraction_stage,
)
from src.application.services._pipeline_orchestration_graph_stage_helpers import (
    _GraphStageInput,
    _PipelineOrchestrationGraphStageHelpers,
)
from src.application.services._pipeline_orchestration_ingestion_stage import (
    run_ingestion_stage,
)
from src.application.services._pipeline_orchestration_seed_helpers import (
    _PipelineOrchestrationContextSeedHelpers,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services._pipeline_orchestration_contracts import (
        PipelineRunSummary,
        PipelineStageName,
    )
    from src.application.services._pipeline_orchestration_execution_protocols import (
        _PipelineExecutionSelf,
    )

logger = logging.getLogger(__name__)


class _PipelineOrchestrationExecutionHelpers(
    _PipelineOrchestrationContextSeedHelpers,
    _PipelineOrchestrationGraphStageHelpers,
):
    """Execution-stage helpers for unified pipeline runs."""

    async def run_for_source(  # noqa: PLR0913
        self: _PipelineExecutionSelf,
        *,
        source_id: UUID,
        research_space_id: UUID,
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
    ) -> PipelineRunSummary:
        started_at = datetime.now(UTC)
        normalized_run_id = self._resolve_run_id(run_id)
        normalized_resume_stage = self._resolve_resume_stage(resume_from_stage)
        normalized_source_type = (
            source_type.strip() if isinstance(source_type, str) else None
        )
        explicit_graph_seed_entity_ids = self._normalize_graph_seed_entity_ids(
            graph_seed_entity_ids,
        )
        context = PipelineExecutionContext(
            source_id=source_id,
            research_space_id=research_space_id,
            run_id=normalized_run_id,
            resume_from_stage=normalized_resume_stage,
            source_type=source_type,
            normalized_source_type=normalized_source_type,
            model_id=model_id,
            shadow_mode=shadow_mode,
            enrichment_limit=enrichment_limit,
            extraction_limit=extraction_limit,
            force_recover_lock=force_recover_lock,
            explicit_graph_seed_entity_ids=explicit_graph_seed_entity_ids,
            graph_max_depth=graph_max_depth,
            graph_relation_types=graph_relation_types,
        )
        state = PipelineExecutionState(
            started_at=started_at,
            pipeline_run_job=self._start_or_resume_pipeline_run(
                source_id=source_id,
                research_space_id=research_space_id,
                run_id=normalized_run_id,
                resume_from_stage=normalized_resume_stage,
            ),
            run_cancelled=self._is_pipeline_run_cancelled(
                source_id=source_id,
                run_id=normalized_run_id,
            ),
            active_graph_seed_entity_ids=list(explicit_graph_seed_entity_ids),
            graph_seed_mode="explicit" if explicit_graph_seed_entity_ids else "none",
            graph_requested=len(explicit_graph_seed_entity_ids),
        )
        runtime = PipelineExecutionRuntime(
            helper=self,
            context=context,
            state=state,
        )
        logger.info(
            "Pipeline run started",
            extra={
                "run_id": normalized_run_id,
                "source_id": str(source_id),
                "research_space_id": str(research_space_id),
                "resume_from_stage": normalized_resume_stage,
                "source_type": source_type,
                "enrichment_limit": enrichment_limit,
                "extraction_limit": extraction_limit,
                "graph_max_depth": graph_max_depth,
                "graph_relation_types": graph_relation_types,
                "graph_seed_entity_ids_count": len(explicit_graph_seed_entity_ids),
            },
        )
        runtime.record_trace_event(
            event_type="run_started",
            scope_kind="run",
            message="Pipeline run execution started.",
            status="running",
            occurred_at=started_at,
            started_at=started_at,
            payload={
                "resume_from_stage": normalized_resume_stage,
                "source_type": source_type,
                "enrichment_limit": enrichment_limit,
                "extraction_limit": extraction_limit,
                "graph_max_depth": graph_max_depth,
                "graph_relation_types": graph_relation_types,
                "graph_seed_entity_ids": explicit_graph_seed_entity_ids,
            },
        )

        should_run_ingestion = self._should_run_stage(
            stage="ingestion",
            resume_from_stage=normalized_resume_stage,
        )
        should_run_enrichment = self._should_run_stage(
            stage="enrichment",
            resume_from_stage=normalized_resume_stage,
        )
        should_run_extraction = self._should_run_stage(
            stage="extraction",
            resume_from_stage=normalized_resume_stage,
        )
        should_run_graph = self._should_run_stage(
            stage="graph",
            resume_from_stage=normalized_resume_stage,
        )

        if should_run_ingestion and not state.run_cancelled:
            await run_ingestion_stage(
                self,
                context=context,
                state=state,
                runtime=runtime,
            )

        can_run_enrichment = state.ingestion_status == "completed" or (
            normalized_resume_stage in {"enrichment", "extraction", "graph"}
        )
        if should_run_enrichment and can_run_enrichment and not state.run_cancelled:
            await run_enrichment_stage(
                self,
                context=context,
                state=state,
                runtime=runtime,
            )

        can_run_extraction = state.enrichment_status == "completed" or (
            normalized_resume_stage in {"extraction", "graph"}
        )
        if should_run_extraction and can_run_extraction and not state.run_cancelled:
            await run_extraction_stage(
                self,
                context=context,
                state=state,
                runtime=runtime,
            )

        graph_stage_output = await self._run_graph_stage(
            graph_stage_input=_GraphStageInput(
                source_id=source_id,
                research_space_id=research_space_id,
                run_id=normalized_run_id,
                resume_from_stage=normalized_resume_stage,
                should_run_graph=should_run_graph,
                extraction_status=state.extraction_status,
                normalized_source_type=normalized_source_type,
                model_id=model_id,
                shadow_mode=shadow_mode,
                explicit_graph_seed_entity_ids=explicit_graph_seed_entity_ids,
                derived_graph_seed_entity_ids=state.derived_graph_seed_entity_ids,
                extraction_graph_fallback_relations=(
                    state.extraction_graph_fallback_relations
                ),
                extraction_processed=state.extraction_processed,
                extraction_extracted=state.extraction_extracted,
                extraction_failed=state.extraction_failed,
                extraction_persisted_relations=state.extraction_persisted_relations,
                extraction_concept_members_created=(
                    state.extraction_concept_members_created
                ),
                extraction_concept_aliases_created=(
                    state.extraction_concept_aliases_created
                ),
                extraction_concept_decisions_proposed=(
                    state.extraction_concept_decisions_proposed
                ),
                total_persisted_relations=state.total_persisted_relations,
                graph_status=state.graph_status,
                errors=state.errors,
                pipeline_error_category=state.pipeline_error_category,
                run_cancelled=state.run_cancelled,
                pipeline_run_job=state.pipeline_run_job,
                graph_relation_types=graph_relation_types,
                graph_max_depth=graph_max_depth,
            ),
        )
        state.inferred_graph_seed_entity_ids = (
            graph_stage_output.inferred_graph_seed_entity_ids
        )
        state.active_graph_seed_entity_ids = (
            graph_stage_output.active_graph_seed_entity_ids
        )
        state.graph_seed_mode = graph_stage_output.graph_seed_mode
        state.graph_seed_limit = graph_stage_output.graph_seed_limit
        state.graph_requested = graph_stage_output.graph_requested
        state.graph_processed = graph_stage_output.graph_processed
        state.graph_stage_persisted_relations = (
            graph_stage_output.graph_stage_persisted_relations
        )
        state.total_persisted_relations = graph_stage_output.total_persisted_relations
        state.graph_status = graph_stage_output.graph_status
        state.pipeline_error_category = graph_stage_output.pipeline_error_category
        state.run_cancelled = graph_stage_output.run_cancelled
        state.pipeline_run_job = graph_stage_output.pipeline_run_job

        return finalize_pipeline_run(
            self,
            context=context,
            state=state,
            runtime=runtime,
        )
