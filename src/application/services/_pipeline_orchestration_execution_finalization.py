"""Finalization helpers for unified pipeline orchestration execution."""

# ruff: noqa: SLF001

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.application.services._pipeline_orchestration_execution_models import (
    build_pipeline_run_summary,
)

if TYPE_CHECKING:
    from src.application.services._pipeline_orchestration_contracts import (
        PipelineRunSummary,
    )
    from src.application.services._pipeline_orchestration_execution_models import (
        PipelineExecutionContext,
        PipelineExecutionState,
    )
    from src.application.services._pipeline_orchestration_execution_protocols import (
        _PipelineExecutionSelf,
    )
    from src.application.services._pipeline_orchestration_execution_runtime import (
        PipelineExecutionRuntime,
    )

logger = logging.getLogger(__name__)


def finalize_pipeline_run(
    helper: _PipelineExecutionSelf,
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
    runtime: PipelineExecutionRuntime,
) -> PipelineRunSummary:
    """Finalize checkpoints, persist cost/timing, and build the run summary."""
    if state.run_cancelled and "pipeline:cancelled" not in state.errors:
        state.errors.append("pipeline:cancelled")

    completed_at = datetime.now(UTC)
    state.pipeline_error_category = (
        resolve_pipeline_error_category(state.errors) or state.pipeline_error_category
    )
    run_status: Literal["completed", "failed", "cancelled"] = _resolve_run_status(
        state=state,
    )
    state.pipeline_run_job = helper._finalize_pipeline_run_checkpoint(
        run_job=state.pipeline_run_job,
        source_id=context.source_id,
        research_space_id=context.research_space_id,
        run_id=context.run_id,
        resume_from_stage=context.resume_from_stage,
        run_status=run_status,
        errors=tuple(state.errors),
        created_publications=state.created_publications,
        updated_publications=state.updated_publications,
        extraction_extracted=state.extraction_extracted,
        graph_persisted_relations=state.total_persisted_relations,
    )
    total_duration_ms = int((completed_at - state.started_at).total_seconds() * 1000)
    runtime.persist_timing_summary(
        stage="run",
        status=run_status,
        stage_started_at=state.started_at,
        stage_completed_at=completed_at,
        duration_ms=total_duration_ms,
        total_duration_ms=total_duration_ms,
    )
    _persist_cost_summary(
        helper=helper,
        context=context,
        state=state,
        runtime=runtime,
        run_status=run_status,
    )
    runtime.record_trace_event(
        event_type="run_finished",
        scope_kind="run",
        message=_build_run_finished_message(run_status=run_status),
        level="error" if run_status == "failed" else "info",
        status=run_status,
        error_code=state.pipeline_error_category,
        occurred_at=completed_at,
        started_at=state.started_at,
        completed_at=completed_at,
        duration_ms=total_duration_ms,
        payload={
            "ingestion_status": state.ingestion_status,
            "enrichment_status": state.enrichment_status,
            "extraction_status": state.extraction_status,
            "graph_status": state.graph_status,
            "fetched_records": state.fetched_records,
            "parsed_publications": state.parsed_publications,
            "created_publications": state.created_publications,
            "updated_publications": state.updated_publications,
            "enrichment_processed": state.enrichment_processed,
            "enrichment_enriched": state.enrichment_enriched,
            "enrichment_failed": state.enrichment_failed,
            "extraction_processed": state.extraction_processed,
            "extraction_extracted": state.extraction_extracted,
            "extraction_failed": state.extraction_failed,
            "persisted_relations": state.total_persisted_relations,
            "error_count": len(state.errors),
        },
    )
    logger.info(
        "Pipeline run finished",
        extra={
            "run_id": context.run_id,
            "source_id": str(context.source_id),
            "research_space_id": str(context.research_space_id),
            "run_status": run_status,
            "duration_ms": total_duration_ms,
            "ingestion_status": state.ingestion_status,
            "enrichment_status": state.enrichment_status,
            "extraction_status": state.extraction_status,
            "graph_status": state.graph_status,
            "extraction_quality_gate_failed": state.extraction_quality_gate_failed,
            "extraction_failure_ratio": state.extraction_failure_ratio,
            "extraction_failure_ratio_threshold": (
                state.extraction_failure_ratio_threshold
            ),
            "error_count": len(state.errors),
        },
    )
    return build_pipeline_run_summary(
        context=context,
        state=state,
        completed_at=completed_at,
        run_status=run_status,
    )


def _resolve_run_status(
    *,
    state: PipelineExecutionState,
) -> Literal["completed", "failed", "cancelled"]:
    if state.run_cancelled:
        return "cancelled"
    if (
        any(
            stage == "failed"
            for stage in (
                state.ingestion_status,
                state.enrichment_status,
                state.extraction_status,
                state.graph_status,
            )
        )
        or state.extraction_quality_gate_failed
    ):
        return "failed"
    return "completed"


def _persist_cost_summary(
    helper: _PipelineExecutionSelf,
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
    runtime: PipelineExecutionRuntime,
    run_status: Literal["completed", "failed", "cancelled"],
) -> None:
    trace_service = helper._pipeline_trace
    if trace_service is None:
        return
    try:
        cost_summary = trace_service.record_cost_event_if_available(
            research_space_id=context.research_space_id,
            source_id=context.source_id,
            pipeline_run_id=context.run_id,
            additional_stage_costs_usd=runtime.build_direct_cost_summary().stage_costs_usd,
        )
        state.pipeline_run_job = helper._persist_pipeline_run_progress(
            run_job=state.pipeline_run_job,
            source_id=context.source_id,
            research_space_id=context.research_space_id,
            run_id=context.run_id,
            resume_from_stage=context.resume_from_stage,
            progress_key="cost_summary",
            progress_payload=cost_summary.to_json_object(),
            overall_status=run_status,
        )
    except (
        RuntimeError,
        TypeError,
        ValueError,
        ValidationError,
        SQLAlchemyError,
    ):
        logger.warning(
            "Failed to persist pipeline cost summary for run_id=%s",
            context.run_id,
            exc_info=True,
        )


def _build_run_finished_message(
    *,
    run_status: Literal["completed", "failed", "cancelled"],
) -> str:
    if run_status == "completed":
        return "Pipeline run completed successfully."
    if run_status == "cancelled":
        return "Pipeline run was cancelled."
    return "Pipeline run failed."


__all__ = ["finalize_pipeline_run"]
