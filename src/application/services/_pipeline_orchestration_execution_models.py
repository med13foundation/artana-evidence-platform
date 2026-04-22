"""Execution context and state models for unified pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from src.application.services._pipeline_orchestration_contracts import (
    PipelineRunSummary,
    PipelineStageName,
    PipelineStageStatus,
)

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from src.domain.agents.contracts.graph_connection import ProposedRelation
    from src.domain.entities.ingestion_job import IngestionJob


@dataclass(frozen=True)
class PipelineExecutionContext:
    """Immutable execution settings for one pipeline run."""

    source_id: UUID
    research_space_id: UUID
    run_id: str
    resume_from_stage: PipelineStageName | None
    source_type: str | None
    normalized_source_type: str | None
    model_id: str | None
    shadow_mode: bool | None
    enrichment_limit: int
    extraction_limit: int
    force_recover_lock: bool
    explicit_graph_seed_entity_ids: list[str]
    graph_max_depth: int
    graph_relation_types: list[str] | None


@dataclass
class PipelineExecutionState:
    """Mutable state accumulated across pipeline stages."""

    started_at: datetime
    pipeline_run_job: IngestionJob | None = None
    errors: list[str] = field(default_factory=list)
    pipeline_error_category: str | None = None
    run_cancelled: bool = False
    active_ingestion_job_id: UUID | None = None

    ingestion_status: PipelineStageStatus = "skipped"
    enrichment_status: PipelineStageStatus = "skipped"
    extraction_status: PipelineStageStatus = "skipped"
    graph_status: PipelineStageStatus = "skipped"

    fetched_records: int = 0
    parsed_publications: int = 0
    created_publications: int = 0
    updated_publications: int = 0
    executed_query: str | None = None
    query_generation_decision: str | None = None
    query_generation_confidence: float | None = None
    query_generation_run_id: str | None = None
    query_generation_execution_mode: str | None = None
    query_generation_fallback_reason: str | None = None
    query_signature: str | None = None
    direct_stage_costs_usd: dict[str, float] = field(default_factory=dict)

    enrichment_processed: int = 0
    enrichment_enriched: int = 0
    enrichment_failed: int = 0
    enrichment_ai_runs: int = 0
    enrichment_deterministic_runs: int = 0

    extraction_processed: int = 0
    extraction_extracted: int = 0
    extraction_failed: int = 0
    extraction_relation_claims: int = 0
    extraction_pending_review_relations: int = 0
    extraction_undefined_relations: int = 0
    extraction_persisted_relations: int = 0
    extraction_concept_members_created: int = 0
    extraction_concept_aliases_created: int = 0
    extraction_concept_decisions_proposed: int = 0
    extraction_failure_ratio: float = 0.0
    extraction_failure_ratio_threshold: float | None = None
    extraction_quality_gate_failed: bool = False

    derived_graph_seed_entity_ids: list[str] = field(default_factory=list)
    extraction_graph_fallback_relations: dict[str, tuple[ProposedRelation, ...]] = (
        field(default_factory=dict)
    )
    inferred_graph_seed_entity_ids: list[str] = field(default_factory=list)
    active_graph_seed_entity_ids: list[str] = field(default_factory=list)
    graph_seed_mode: str = "none"
    graph_seed_limit: int | None = None
    graph_requested: int = 0
    graph_processed: int = 0
    graph_stage_persisted_relations: int = 0
    total_persisted_relations: int = 0


def build_pipeline_run_summary(
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
    completed_at: datetime,
    run_status: Literal["completed", "failed", "cancelled"],
) -> PipelineRunSummary:
    """Build the public run summary payload from context and state."""
    return PipelineRunSummary(
        run_id=context.run_id,
        resume_from_stage=context.resume_from_stage,
        source_id=context.source_id,
        research_space_id=context.research_space_id,
        started_at=state.started_at,
        completed_at=completed_at,
        status=run_status,
        ingestion_status=state.ingestion_status,
        enrichment_status=state.enrichment_status,
        extraction_status=state.extraction_status,
        graph_status=state.graph_status,
        fetched_records=state.fetched_records,
        parsed_publications=state.parsed_publications,
        created_publications=state.created_publications,
        updated_publications=state.updated_publications,
        enrichment_processed=state.enrichment_processed,
        enrichment_enriched=state.enrichment_enriched,
        enrichment_failed=state.enrichment_failed,
        extraction_processed=state.extraction_processed,
        extraction_extracted=state.extraction_extracted,
        extraction_failed=state.extraction_failed,
        graph_requested=state.graph_requested,
        graph_processed=state.graph_processed,
        graph_persisted_relations=state.total_persisted_relations,
        executed_query=state.executed_query,
        errors=tuple(state.errors),
        metadata={
            "run_id": context.run_id,
            "resume_from_stage": context.resume_from_stage,
            "pipeline_run_checkpoint_id": (
                str(state.pipeline_run_job.id)
                if state.pipeline_run_job is not None
                else None
            ),
            "query_generation_run_id": state.query_generation_run_id,
            "query_generation_decision": state.query_generation_decision,
            "query_generation_confidence": state.query_generation_confidence,
            "query_generation_execution_mode": (state.query_generation_execution_mode),
            "query_generation_fallback_reason": (
                state.query_generation_fallback_reason
            ),
            "ingestion_job_id": (
                str(state.active_ingestion_job_id)
                if state.active_ingestion_job_id is not None
                else None
            ),
            "enrichment_ai_runs": state.enrichment_ai_runs,
            "enrichment_deterministic_runs": state.enrichment_deterministic_runs,
            "ingestion_status": state.ingestion_status,
            "enrichment_status": state.enrichment_status,
            "extraction_status": state.extraction_status,
            "extraction_relation_claims": state.extraction_relation_claims,
            "extraction_pending_review_relations": (
                state.extraction_pending_review_relations
            ),
            "extraction_undefined_relations": state.extraction_undefined_relations,
            "graph_status": state.graph_status,
            "extraction_persisted_relations": state.extraction_persisted_relations,
            "extraction_concept_members_created": (
                state.extraction_concept_members_created
            ),
            "extraction_concept_aliases_created": (
                state.extraction_concept_aliases_created
            ),
            "extraction_concept_decisions_proposed": (
                state.extraction_concept_decisions_proposed
            ),
            "graph_stage_persisted_relations": state.graph_stage_persisted_relations,
            "total_persisted_relations": state.total_persisted_relations,
            "extraction_quality_gate_failed": state.extraction_quality_gate_failed,
            "extraction_failure_ratio": state.extraction_failure_ratio,
            "extraction_failure_ratio_threshold": (
                state.extraction_failure_ratio_threshold
            ),
            "error_category": state.pipeline_error_category,
            "graph_seed_mode": state.graph_seed_mode,
            "graph_explicit_seed_count": len(context.explicit_graph_seed_entity_ids),
            "graph_derived_seed_count": len(state.derived_graph_seed_entity_ids),
            "graph_inferred_seed_count": len(state.inferred_graph_seed_entity_ids),
            "graph_active_seed_ids": list(state.active_graph_seed_entity_ids),
            "graph_seed_limit": state.graph_seed_limit,
            "graph_extraction_fallback_seed_count": len(
                state.extraction_graph_fallback_relations,
            ),
            "graph_extraction_fallback_relation_count": sum(
                len(relations)
                for relations in state.extraction_graph_fallback_relations.values()
            ),
        },
    )


__all__ = [
    "PipelineExecutionContext",
    "PipelineExecutionState",
    "build_pipeline_run_summary",
]
