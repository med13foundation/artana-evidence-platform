"""Extraction-stage execution helpers for unified pipeline orchestration."""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.application.services._pipeline_orchestration_execution_utils import (
    DEFAULT_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS,
    DEFAULT_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY,
    DEFAULT_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS,
    DEFAULT_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS,
    ENV_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS,
    ENV_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY,
    ENV_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS,
    ENV_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS,
    EXTRACTION_STAGE_TIMEOUT_OVERHEAD_SECONDS,
    first_matching_error,
    read_positive_int,
    read_positive_timeout_seconds,
    resolve_extraction_failure_ratio_threshold,
)
from src.application.services._pipeline_orchestration_extraction_change_events import (
    record_extraction_change_events,
)
from src.application.services._pipeline_orchestration_graph_fallback_helpers import (
    extract_graph_fallback_relations_from_extraction_summary,
)

if TYPE_CHECKING:
    from src.application.agents.services.entity_recognition_service import (
        EntityRecognitionRunSummary,
    )

    from ._pipeline_orchestration_execution_models import (
        PipelineExecutionContext,
        PipelineExecutionState,
    )
    from ._pipeline_orchestration_execution_protocols import _PipelineExecutionSelf
    from ._pipeline_orchestration_execution_runtime import PipelineExecutionRuntime

logger = logging.getLogger(__name__)


async def run_extraction_stage(
    helper: _PipelineExecutionSelf,
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
    runtime: PipelineExecutionRuntime,
) -> None:
    """Run extraction and mutate the shared pipeline execution state."""
    extraction_watchdog_timeout_seconds = _resolve_watchdog_timeout_seconds(
        extraction_limit=context.extraction_limit,
    )
    extraction_started_at = datetime.now(UTC)
    logger.info(
        "Pipeline stage started",
        extra={
            "run_id": context.run_id,
            "source_id": str(context.source_id),
            "stage": "extraction",
            "ingestion_job_id": (
                str(state.active_ingestion_job_id)
                if state.active_ingestion_job_id is not None
                else None
            ),
            "watchdog_timeout_seconds": extraction_watchdog_timeout_seconds,
        },
    )
    runtime.record_trace_event(
        event_type="stage_started",
        scope_kind="run",
        stage="extraction",
        message="Extraction stage started.",
        status="running",
        occurred_at=extraction_started_at,
        started_at=extraction_started_at,
        timeout_budget_ms=int(extraction_watchdog_timeout_seconds * 1000),
        payload={
            "ingestion_job_id": (
                str(state.active_ingestion_job_id)
                if state.active_ingestion_job_id is not None
                else None
            ),
            "watchdog_timeout_seconds": extraction_watchdog_timeout_seconds,
        },
    )
    extraction_stage_error: str | None = None
    extraction_error_category: str | None = None
    try:
        with runtime.track_direct_costs(default_stage="extraction"):
            extraction_summary = await asyncio.wait_for(
                _run_stage_with_compat(
                    helper=helper,
                    context=context,
                    state=state,
                ),
                timeout=extraction_watchdog_timeout_seconds,
            )
        _apply_extraction_summary(
            helper=helper,
            state=state,
            extraction_summary=extraction_summary,
        )
        record_extraction_change_events(
            runtime=runtime,
            extraction_summary=extraction_summary,
        )
        extraction_error_category = resolve_pipeline_error_category(
            extraction_summary.errors,
        )
        if extraction_error_category is not None:
            state.pipeline_error_category = extraction_error_category
        if extraction_error_category == "capacity" and state.extraction_failed > 0:
            state.extraction_status = "failed"
            extraction_stage_error = first_matching_error(
                extraction_summary.errors,
                category=extraction_error_category,
            )
        runtime.record_stage_warning_messages(
            stage="extraction",
            warnings=extraction_summary.errors,
            occurred_at=datetime.now(UTC),
            agent_kind="entity_recognition",
        )
        _apply_quality_gate(
            context=context,
            state=state,
            runtime=runtime,
            extraction_error_category=extraction_error_category,
        )
        if state.extraction_quality_gate_failed:
            extraction_stage_error = state.errors[-1]
    except TimeoutError:
        state.extraction_status = "failed"
        extraction_stage_error = (
            f"extraction:stage_timeout:{extraction_watchdog_timeout_seconds:.1f}s"
        )
        logger.exception(
            "Pipeline extraction stage timed out for run_id=%s source_id=%s",
            context.run_id,
            context.source_id,
        )
        state.errors.append(extraction_stage_error)
    except Exception as exc:  # noqa: BLE001
        state.extraction_status = "failed"
        extraction_stage_error = f"extraction:{exc!s}"
        state.errors.append(extraction_stage_error)
        extraction_error_category = resolve_pipeline_error_category(
            (extraction_stage_error,),
        )
        if extraction_error_category is not None:
            state.pipeline_error_category = extraction_error_category
    extraction_completed_at = datetime.now(UTC)
    extraction_duration_ms = int(
        (extraction_completed_at - extraction_started_at).total_seconds() * 1000,
    )
    logger.info(
        "Pipeline stage finished",
        extra={
            "run_id": context.run_id,
            "source_id": str(context.source_id),
            "stage": "extraction",
            "stage_status": state.extraction_status,
            "duration_ms": extraction_duration_ms,
            "extraction_processed": state.extraction_processed,
            "extraction_extracted": state.extraction_extracted,
            "extraction_failed": state.extraction_failed,
            "extraction_persisted_relations": state.extraction_persisted_relations,
            "extraction_failure_ratio": state.extraction_failure_ratio,
            "extraction_failure_ratio_threshold": (
                state.extraction_failure_ratio_threshold
            ),
            "extraction_quality_gate_failed": state.extraction_quality_gate_failed,
            "derived_graph_seed_entity_ids_count": len(
                state.derived_graph_seed_entity_ids,
            ),
            "watchdog_timeout_seconds": extraction_watchdog_timeout_seconds,
        },
    )
    runtime.persist_timing_summary(
        stage="extraction",
        status=state.extraction_status,
        stage_started_at=extraction_started_at,
        stage_completed_at=extraction_completed_at,
        duration_ms=extraction_duration_ms,
        timeout_budget_ms=int(extraction_watchdog_timeout_seconds * 1000),
    )
    runtime.record_trace_event(
        event_type="stage_finished",
        scope_kind="run",
        stage="extraction",
        message=(
            "Extraction stage completed successfully."
            if state.extraction_status == "completed"
            else "Extraction stage failed."
        ),
        level="error" if state.extraction_status == "failed" else "info",
        status=state.extraction_status,
        error_code=extraction_error_category,
        occurred_at=extraction_completed_at,
        started_at=extraction_started_at,
        completed_at=extraction_completed_at,
        duration_ms=extraction_duration_ms,
        timeout_budget_ms=int(extraction_watchdog_timeout_seconds * 1000),
        payload={
            "processed": state.extraction_processed,
            "extracted": state.extraction_extracted,
            "failed": state.extraction_failed,
            "relation_claims_count": state.extraction_relation_claims,
            "pending_review_relations_count": (
                state.extraction_pending_review_relations
            ),
            "undefined_relations_count": state.extraction_undefined_relations,
            "persisted_relations": state.extraction_persisted_relations,
            "concept_members_created": state.extraction_concept_members_created,
            "concept_aliases_created": state.extraction_concept_aliases_created,
            "concept_decisions_proposed": (state.extraction_concept_decisions_proposed),
            "failure_ratio": state.extraction_failure_ratio,
            "failure_ratio_threshold": state.extraction_failure_ratio_threshold,
            "quality_gate_failed": state.extraction_quality_gate_failed,
            "derived_graph_seed_entity_ids": list(
                state.derived_graph_seed_entity_ids,
            ),
        },
    )
    state.pipeline_run_job = helper._persist_pipeline_run_progress(
        run_job=state.pipeline_run_job,
        source_id=context.source_id,
        research_space_id=context.research_space_id,
        run_id=context.run_id,
        resume_from_stage=context.resume_from_stage,
        progress_key="extraction_run",
        progress_payload={
            "status": state.extraction_status,
            "processed": state.extraction_processed,
            "completed": state.extraction_extracted,
            "failed": state.extraction_failed,
            "relation_claims_count": state.extraction_relation_claims,
            "pending_review_relations_count": (
                state.extraction_pending_review_relations
            ),
            "undefined_relations_count": state.extraction_undefined_relations,
            "persisted_relations": state.extraction_persisted_relations,
            "concept_members_created": state.extraction_concept_members_created,
            "concept_aliases_created": state.extraction_concept_aliases_created,
            "concept_decisions_proposed": (state.extraction_concept_decisions_proposed),
            "quality_gate_failed": state.extraction_quality_gate_failed,
            "failure_ratio": state.extraction_failure_ratio,
            "failure_ratio_threshold": state.extraction_failure_ratio_threshold,
            "last_error": extraction_stage_error,
            "error_category": extraction_error_category,
        },
        overall_status="running",
    )
    state.pipeline_run_job = helper._persist_pipeline_stage_checkpoint(
        run_job=state.pipeline_run_job,
        source_id=context.source_id,
        research_space_id=context.research_space_id,
        run_id=context.run_id,
        resume_from_stage=context.resume_from_stage,
        stage="extraction",
        stage_status=state.extraction_status,
        overall_status="running",
        stage_error=extraction_stage_error,
    )
    state.run_cancelled = helper._is_pipeline_run_cancelled(
        source_id=context.source_id,
        run_id=context.run_id,
    )


def _resolve_watchdog_timeout_seconds(*, extraction_limit: int) -> float:
    configured_timeout = read_positive_timeout_seconds(
        ENV_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS,
        default_seconds=DEFAULT_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS,
    )
    raw_override = os.getenv(ENV_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS)
    has_override = False
    if isinstance(raw_override, str) and raw_override.strip():
        try:
            has_override = float(raw_override.strip()) > 0
        except ValueError:
            has_override = False
    entity_agent_timeout_seconds = read_positive_timeout_seconds(
        ENV_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS,
        default_seconds=DEFAULT_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS,
    )
    entity_extraction_timeout_seconds = read_positive_timeout_seconds(
        ENV_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS,
        default_seconds=DEFAULT_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS,
    )
    entity_batch_max_concurrency = read_positive_int(
        ENV_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY,
        default_value=DEFAULT_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY,
    )
    extraction_waves = max(
        (max(extraction_limit, 1) + entity_batch_max_concurrency - 1)
        // entity_batch_max_concurrency,
        1,
    )
    estimated_timeout = float(extraction_waves) * (
        entity_agent_timeout_seconds
        + entity_extraction_timeout_seconds
        + EXTRACTION_STAGE_TIMEOUT_OVERHEAD_SECONDS
    )
    return (
        configured_timeout
        if has_override
        else max(configured_timeout, estimated_timeout)
    )


async def _run_stage_with_compat(
    helper: _PipelineExecutionSelf,
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
) -> EntityRecognitionRunSummary:
    if helper._extraction_stage_runner is not None:
        return await helper._extraction_stage_runner(
            limit=max(context.extraction_limit, 1),
            source_id=context.source_id,
            ingestion_job_id=state.active_ingestion_job_id,
            research_space_id=context.research_space_id,
            source_type=context.normalized_source_type,
            model_id=context.model_id,
            shadow_mode=context.shadow_mode,
            pipeline_run_id=context.run_id,
        )
    try:
        return await helper._extraction.process_pending_documents(
            limit=max(context.extraction_limit, 1),
            source_id=context.source_id,
            ingestion_job_id=state.active_ingestion_job_id,
            research_space_id=context.research_space_id,
            source_type=context.normalized_source_type,
            model_id=context.model_id,
            shadow_mode=context.shadow_mode,
            pipeline_run_id=context.run_id,
        )
    except TypeError as exc:
        if "ingestion_job_id" not in str(exc):
            raise
        return await helper._extraction.process_pending_documents(
            limit=max(context.extraction_limit, 1),
            source_id=context.source_id,
            research_space_id=context.research_space_id,
            source_type=context.normalized_source_type,
            model_id=context.model_id,
            shadow_mode=context.shadow_mode,
            pipeline_run_id=context.run_id,
        )


def _apply_extraction_summary(
    helper: _PipelineExecutionSelf,
    *,
    state: PipelineExecutionState,
    extraction_summary: EntityRecognitionRunSummary,
) -> None:
    state.extraction_status = "completed"
    state.extraction_processed = extraction_summary.processed
    state.extraction_extracted = extraction_summary.extracted
    state.extraction_failed = extraction_summary.failed
    state.extraction_relation_claims = _summary_int(
        extraction_summary,
        "relation_claims_count",
    )
    state.extraction_pending_review_relations = _summary_int(
        extraction_summary,
        "pending_review_relations_count",
    )
    state.extraction_undefined_relations = _summary_int(
        extraction_summary,
        "undefined_relations_count",
    )
    state.extraction_persisted_relations = _summary_int(
        extraction_summary,
        "persisted_relations_count",
    )
    state.extraction_concept_members_created = _summary_int(
        extraction_summary,
        "concept_members_created_count",
    )
    state.extraction_concept_aliases_created = _summary_int(
        extraction_summary,
        "concept_aliases_created_count",
    )
    state.extraction_concept_decisions_proposed = _summary_int(
        extraction_summary,
        "concept_decisions_proposed_count",
    )
    state.total_persisted_relations = state.extraction_persisted_relations
    state.derived_graph_seed_entity_ids = (
        helper._extract_seed_entity_ids_from_extraction_summary(
            extraction_summary,
        )
    )
    state.extraction_graph_fallback_relations = (
        extract_graph_fallback_relations_from_extraction_summary(extraction_summary)
    )
    state.errors.extend(extraction_summary.errors)


def _apply_quality_gate(
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
    runtime: PipelineExecutionRuntime,
    extraction_error_category: str | None,
) -> None:
    if state.extraction_processed <= 0 or extraction_error_category == "capacity":
        return
    state.extraction_failure_ratio = (
        state.extraction_failed / state.extraction_processed
    )
    threshold = resolve_extraction_failure_ratio_threshold(
        context.normalized_source_type,
    )
    state.extraction_failure_ratio_threshold = threshold
    if state.extraction_failure_ratio <= threshold:
        return
    state.extraction_quality_gate_failed = True
    state.errors.append(
        "extraction:quality_gate_failed:"
        f"failed={state.extraction_failed}/processed={state.extraction_processed}:"
        f"ratio={state.extraction_failure_ratio:.3f}:threshold={threshold:.3f}",
    )
    logger.warning(
        "Extraction quality gate failed for pipeline run",
        extra={
            "run_id": context.run_id,
            "source_id": str(context.source_id),
            "source_type": context.normalized_source_type,
            "extraction_processed": state.extraction_processed,
            "extraction_failed": state.extraction_failed,
            "extraction_failure_ratio": state.extraction_failure_ratio,
            "extraction_failure_ratio_threshold": threshold,
        },
    )
    runtime.record_trace_event(
        event_type="quality_gate_failed",
        scope_kind="run",
        stage="extraction",
        message="Extraction quality gate failed.",
        level="warning",
        status="warning",
        error_code=extraction_error_category,
        occurred_at=datetime.now(UTC),
        payload={
            "processed": state.extraction_processed,
            "failed": state.extraction_failed,
            "failure_ratio": state.extraction_failure_ratio,
            "failure_ratio_threshold": threshold,
        },
    )


def _summary_int(summary: object, field_name: str) -> int:
    raw_value = getattr(summary, field_name, 0)
    return max(raw_value, 0) if isinstance(raw_value, int) else 0


__all__ = ["run_extraction_stage"]
