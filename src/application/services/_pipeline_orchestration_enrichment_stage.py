"""Enrichment-stage execution helpers for unified pipeline orchestration."""

# ruff: noqa: SLF001

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)

if TYPE_CHECKING:
    from src.application.agents.services._content_enrichment_types import (
        ContentEnrichmentRunSummary,
    )

    from ._pipeline_orchestration_execution_models import (
        PipelineExecutionContext,
        PipelineExecutionState,
    )
    from ._pipeline_orchestration_execution_protocols import _PipelineExecutionSelf
    from ._pipeline_orchestration_execution_runtime import PipelineExecutionRuntime

logger = logging.getLogger(__name__)


async def run_enrichment_stage(
    helper: _PipelineExecutionSelf,
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
    runtime: PipelineExecutionRuntime,
) -> None:
    """Run content enrichment and mutate the shared pipeline execution state."""
    enrichment_started_at = datetime.now(UTC)
    logger.info(
        "Pipeline stage started",
        extra={
            "run_id": context.run_id,
            "source_id": str(context.source_id),
            "stage": "enrichment",
            "ingestion_job_id": (
                str(state.active_ingestion_job_id)
                if state.active_ingestion_job_id is not None
                else None
            ),
        },
    )
    runtime.record_trace_event(
        event_type="stage_started",
        scope_kind="run",
        stage="enrichment",
        message="Content enrichment stage started.",
        status="running",
        occurred_at=enrichment_started_at,
        started_at=enrichment_started_at,
        payload={
            "ingestion_job_id": (
                str(state.active_ingestion_job_id)
                if state.active_ingestion_job_id is not None
                else None
            ),
        },
    )
    enrichment_error_category: str | None = None
    try:
        with runtime.track_direct_costs(default_stage="enrichment"):
            enrichment_summary = await _run_stage_with_compat(
                helper=helper,
                context=context,
                state=state,
            )
        _apply_enrichment_summary(
            state=state,
            enrichment_summary=enrichment_summary,
        )
        enrichment_error_category = resolve_pipeline_error_category(
            enrichment_summary.errors,
        )
        if enrichment_error_category is not None:
            state.pipeline_error_category = enrichment_error_category
        if enrichment_error_category == "capacity" and state.enrichment_failed > 0:
            state.enrichment_status = "failed"
        runtime.record_stage_warning_messages(
            stage="enrichment",
            warnings=enrichment_summary.errors,
            occurred_at=datetime.now(UTC),
            agent_kind="content_enrichment",
        )
    except Exception as exc:  # noqa: BLE001
        state.enrichment_status = "failed"
        enrichment_error = f"enrichment:{exc!s}"
        state.errors.append(enrichment_error)
        enrichment_error_category = resolve_pipeline_error_category((enrichment_error,))
        if enrichment_error_category is not None:
            state.pipeline_error_category = enrichment_error_category
    enrichment_completed_at = datetime.now(UTC)
    enrichment_duration_ms = int(
        (enrichment_completed_at - enrichment_started_at).total_seconds() * 1000,
    )
    logger.info(
        "Pipeline stage finished",
        extra={
            "run_id": context.run_id,
            "source_id": str(context.source_id),
            "stage": "enrichment",
            "stage_status": state.enrichment_status,
            "duration_ms": enrichment_duration_ms,
            "enrichment_processed": state.enrichment_processed,
            "enrichment_enriched": state.enrichment_enriched,
            "enrichment_failed": state.enrichment_failed,
        },
    )
    runtime.persist_timing_summary(
        stage="enrichment",
        status=state.enrichment_status,
        stage_started_at=enrichment_started_at,
        stage_completed_at=enrichment_completed_at,
        duration_ms=enrichment_duration_ms,
    )
    runtime.record_trace_event(
        event_type="stage_finished",
        scope_kind="run",
        stage="enrichment",
        message=(
            "Content enrichment stage completed successfully."
            if state.enrichment_status == "completed"
            else "Content enrichment stage failed."
        ),
        level="error" if state.enrichment_status == "failed" else "info",
        status=state.enrichment_status,
        error_code=(
            enrichment_error_category if state.enrichment_status == "failed" else None
        ),
        occurred_at=enrichment_completed_at,
        started_at=enrichment_started_at,
        completed_at=enrichment_completed_at,
        duration_ms=enrichment_duration_ms,
        payload={
            "processed": state.enrichment_processed,
            "enriched": state.enrichment_enriched,
            "failed": state.enrichment_failed,
            "ai_runs": state.enrichment_ai_runs,
            "deterministic_runs": state.enrichment_deterministic_runs,
        },
    )
    state.pipeline_run_job = helper._persist_pipeline_stage_checkpoint(
        run_job=state.pipeline_run_job,
        source_id=context.source_id,
        research_space_id=context.research_space_id,
        run_id=context.run_id,
        resume_from_stage=context.resume_from_stage,
        stage="enrichment",
        stage_status=state.enrichment_status,
        overall_status="running",
        stage_error=(
            state.errors[-1]
            if state.enrichment_status == "failed" and state.errors
            else None
        ),
    )
    state.run_cancelled = helper._is_pipeline_run_cancelled(
        source_id=context.source_id,
        run_id=context.run_id,
    )


async def _run_stage_with_compat(
    helper: _PipelineExecutionSelf,
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
) -> ContentEnrichmentRunSummary:
    if helper._enrichment_stage_runner is not None:
        return await helper._enrichment_stage_runner(
            limit=max(context.enrichment_limit, 1),
            source_id=context.source_id,
            ingestion_job_id=state.active_ingestion_job_id,
            research_space_id=context.research_space_id,
            source_type=context.normalized_source_type,
            model_id=context.model_id,
            pipeline_run_id=context.run_id,
        )
    try:
        return await helper._enrichment.process_pending_documents(
            limit=max(context.enrichment_limit, 1),
            source_id=context.source_id,
            ingestion_job_id=state.active_ingestion_job_id,
            research_space_id=context.research_space_id,
            source_type=context.normalized_source_type,
            model_id=context.model_id,
            pipeline_run_id=context.run_id,
        )
    except TypeError as exc:
        if "ingestion_job_id" not in str(exc):
            raise
        return await helper._enrichment.process_pending_documents(
            limit=max(context.enrichment_limit, 1),
            source_id=context.source_id,
            research_space_id=context.research_space_id,
            source_type=context.normalized_source_type,
            model_id=context.model_id,
            pipeline_run_id=context.run_id,
        )


def _apply_enrichment_summary(
    *,
    state: PipelineExecutionState,
    enrichment_summary: ContentEnrichmentRunSummary,
) -> None:
    state.enrichment_status = "completed"
    state.enrichment_processed = enrichment_summary.processed
    state.enrichment_enriched = enrichment_summary.enriched
    state.enrichment_failed = enrichment_summary.failed
    state.enrichment_ai_runs = (
        enrichment_summary.ai_runs
        if isinstance(getattr(enrichment_summary, "ai_runs", None), int)
        else 0
    )
    state.enrichment_deterministic_runs = (
        enrichment_summary.deterministic_runs
        if isinstance(getattr(enrichment_summary, "deterministic_runs", None), int)
        else 0
    )
    state.errors.extend(enrichment_summary.errors)


__all__ = ["run_enrichment_stage"]
