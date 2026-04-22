"""Ingestion-stage execution helpers for unified pipeline orchestration."""

# ruff: noqa: SLF001

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.application.services._pipeline_orchestration_checkpoint_metadata import (
    coerce_json_object,
)
from src.application.services._pipeline_orchestration_execution_utils import (
    coerce_optional_uuid,
)
from src.application.services._pipeline_orchestration_graph_fallback_helpers import (
    resolve_latest_ingestion_job_id,
)

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject

    from ._pipeline_orchestration_execution_models import (
        PipelineExecutionContext,
        PipelineExecutionState,
    )
    from ._pipeline_orchestration_execution_protocols import _PipelineExecutionSelf
    from ._pipeline_orchestration_execution_runtime import PipelineExecutionRuntime

logger = logging.getLogger(__name__)


async def run_ingestion_stage(
    helper: _PipelineExecutionSelf,
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
    runtime: PipelineExecutionRuntime,
) -> None:
    """Run ingestion and mutate the shared pipeline execution state."""
    ingestion_started_at = datetime.now(UTC)
    logger.info(
        "Pipeline stage started",
        extra={
            "run_id": context.run_id,
            "source_id": str(context.source_id),
            "stage": "ingestion",
        },
    )
    runtime.record_trace_event(
        event_type="stage_started",
        scope_kind="run",
        stage="ingestion",
        message="Ingestion stage started.",
        status="running",
        occurred_at=ingestion_started_at,
        started_at=ingestion_started_at,
    )
    try:
        with runtime.track_direct_costs(default_stage="ingestion"):
            try:
                ingestion_summary = await helper._ingestion.trigger_ingestion(
                    context.source_id,
                    skip_post_ingestion_hook=True,
                    skip_legacy_extraction_queue=True,
                    force_recover_lock=context.force_recover_lock,
                    pipeline_run_id=context.run_id,
                    progress_callback=runtime.handle_ingestion_progress,
                )
            except TypeError as exc:
                if not _is_compat_ingestion_type_error(exc):
                    raise
                ingestion_summary = await helper._ingestion.trigger_ingestion(
                    context.source_id,
                )
        _apply_ingestion_summary(
            helper=helper,
            context=context,
            state=state,
            runtime=runtime,
            ingestion_summary=ingestion_summary,
        )
        state.ingestion_status = "completed"
    except Exception as exc:  # noqa: BLE001
        state.ingestion_status = "failed"
        error_message = str(exc).strip() or exc.__class__.__name__
        state.errors.append(f"ingestion:{error_message}")
        state.pipeline_error_category = resolve_pipeline_error_category(state.errors)
    ingestion_completed_at = datetime.now(UTC)
    ingestion_duration_ms = int(
        (ingestion_completed_at - ingestion_started_at).total_seconds() * 1000,
    )
    logger.info(
        "Pipeline stage finished",
        extra={
            "run_id": context.run_id,
            "source_id": str(context.source_id),
            "stage": "ingestion",
            "stage_status": state.ingestion_status,
            "duration_ms": ingestion_duration_ms,
            "fetched_records": state.fetched_records,
            "parsed_publications": state.parsed_publications,
            "created_publications": state.created_publications,
            "updated_publications": state.updated_publications,
            "ingestion_job_id": (
                str(state.active_ingestion_job_id)
                if state.active_ingestion_job_id is not None
                else None
            ),
        },
    )
    runtime.persist_timing_summary(
        stage="ingestion",
        status=state.ingestion_status,
        stage_started_at=ingestion_started_at,
        stage_completed_at=ingestion_completed_at,
        duration_ms=ingestion_duration_ms,
    )
    runtime.record_trace_event(
        event_type="stage_finished",
        scope_kind="run",
        stage="ingestion",
        message=(
            "Ingestion stage completed successfully."
            if state.ingestion_status == "completed"
            else "Ingestion stage failed."
        ),
        level="error" if state.ingestion_status == "failed" else "info",
        status=state.ingestion_status,
        error_code=(
            state.pipeline_error_category
            if state.ingestion_status == "failed"
            else None
        ),
        occurred_at=ingestion_completed_at,
        started_at=ingestion_started_at,
        completed_at=ingestion_completed_at,
        duration_ms=ingestion_duration_ms,
        payload={
            "fetched_records": state.fetched_records,
            "parsed_publications": state.parsed_publications,
            "created_publications": state.created_publications,
            "updated_publications": state.updated_publications,
            "executed_query": state.executed_query,
            "query_signature": state.query_signature,
            "query_generation_decision": state.query_generation_decision,
            "query_generation_confidence": state.query_generation_confidence,
            "query_generation_execution_mode": state.query_generation_execution_mode,
            "query_generation_fallback_reason": (
                state.query_generation_fallback_reason
            ),
        },
    )
    state.pipeline_run_job = helper._persist_pipeline_stage_checkpoint(
        run_job=state.pipeline_run_job,
        source_id=context.source_id,
        research_space_id=context.research_space_id,
        run_id=context.run_id,
        resume_from_stage=context.resume_from_stage,
        stage="ingestion",
        stage_status=state.ingestion_status,
        overall_status="running",
        stage_error=(
            state.errors[-1]
            if state.ingestion_status == "failed" and state.errors
            else None
        ),
    )
    state.run_cancelled = helper._is_pipeline_run_cancelled(
        source_id=context.source_id,
        run_id=context.run_id,
    )


def _is_compat_ingestion_type_error(exc: TypeError) -> bool:
    error_text = str(exc)
    return any(
        token in error_text
        for token in (
            "skip_post_ingestion_hook",
            "force_recover_lock",
            "skip_legacy_extraction_queue",
            "pipeline_run_id",
            "progress_callback",
        )
    )


def _apply_ingestion_summary(
    helper: _PipelineExecutionSelf,
    *,
    context: PipelineExecutionContext,
    state: PipelineExecutionState,
    runtime: PipelineExecutionRuntime,
    ingestion_summary: object,
) -> None:
    state.fetched_records = int(getattr(ingestion_summary, "fetched_records", 0))
    state.parsed_publications = int(
        getattr(ingestion_summary, "parsed_publications", 0),
    )
    state.created_publications = int(
        getattr(ingestion_summary, "created_publications", 0),
    )
    state.updated_publications = int(
        getattr(ingestion_summary, "updated_publications", 0),
    )
    state.executed_query = getattr(ingestion_summary, "executed_query", None)
    state.query_generation_decision = _normalized_string(
        getattr(ingestion_summary, "query_generation_decision", None),
    )
    state.query_generation_confidence = _float_or_none(
        getattr(ingestion_summary, "query_generation_confidence", None),
    )
    state.query_generation_run_id = _normalized_string(
        getattr(ingestion_summary, "query_generation_run_id", None),
    )
    state.query_generation_execution_mode = _normalized_string(
        getattr(ingestion_summary, "query_generation_execution_mode", None),
    )
    state.query_generation_fallback_reason = _normalized_string(
        getattr(ingestion_summary, "query_generation_fallback_reason", None),
    )
    summary_query_signature = _normalized_string(
        getattr(ingestion_summary, "query_signature", None),
    )
    state.query_signature = summary_query_signature or state.query_signature
    state.active_ingestion_job_id = coerce_optional_uuid(
        getattr(ingestion_summary, "ingestion_job_id", None),
    )
    if state.active_ingestion_job_id is None:
        state.active_ingestion_job_id = resolve_latest_ingestion_job_id(
            ingestion_service=helper._ingestion,
            source_id=context.source_id,
        )
    if state.active_ingestion_job_id is None:
        logger.warning(
            "Pipeline ingestion completed but no ingestion job id was resolved",
            extra={
                "run_id": context.run_id,
                "source_id": str(context.source_id),
            },
        )
    else:
        state.pipeline_run_job = helper._persist_pipeline_run_progress(
            run_job=state.pipeline_run_job,
            source_id=context.source_id,
            research_space_id=context.research_space_id,
            run_id=context.run_id,
            resume_from_stage=context.resume_from_stage,
            progress_key="run_scope",
            progress_payload={
                "ingestion_job_id": str(state.active_ingestion_job_id),
            },
            overall_status="running",
        )
    runtime.persist_query_progress(
        payload={
            "executed_query": state.executed_query,
            "query_signature": state.query_signature,
            "query_generation_decision": state.query_generation_decision,
            "query_generation_confidence": state.query_generation_confidence,
            "query_generation_run_id": state.query_generation_run_id,
            "query_generation_execution_mode": state.query_generation_execution_mode,
            "query_generation_fallback_reason": (
                state.query_generation_fallback_reason
            ),
        },
    )
    runtime.record_trace_event(
        event_type="query_generated",
        scope_kind="query",
        stage="ingestion",
        scope_id=state.query_signature or state.query_generation_run_id,
        message="Resolved source query for PubMed ingestion.",
        level=(
            "warning" if state.query_generation_fallback_reason is not None else "info"
        ),
        status=(
            "fallback"
            if state.query_generation_fallback_reason is not None
            else state.query_generation_decision or state.ingestion_status
        ),
        agent_kind="query_generation",
        agent_run_id=state.query_generation_run_id,
        payload={
            "executed_query": state.executed_query,
            "query_signature": state.query_signature,
            "decision": state.query_generation_decision,
            "confidence": state.query_generation_confidence,
            "execution_mode": state.query_generation_execution_mode,
            "fallback_reason": state.query_generation_fallback_reason,
            "fetched_records": state.fetched_records,
            "processed_records": state.parsed_publications,
        },
    )
    runtime.record_trace_event(
        event_type="papers_fetched",
        scope_kind="query",
        stage="ingestion",
        message=(
            "PubMed ingestion fetched candidate papers "
            f"({state.fetched_records} records)."
        ),
        status="completed",
        payload={
            "fetched_records": state.fetched_records,
            "parsed_publications": state.parsed_publications,
            "created_publications": state.created_publications,
            "updated_publications": state.updated_publications,
            "ingestion_job_id": (
                str(state.active_ingestion_job_id)
                if state.active_ingestion_job_id is not None
                else None
            ),
        },
    )
    extraction_targets = tuple(getattr(ingestion_summary, "extraction_targets", ()))
    for target in extraction_targets:
        _record_document_found(runtime=runtime, target=target)


def _record_document_found(
    *,
    runtime: PipelineExecutionRuntime,
    target: object,
) -> None:
    target_metadata = coerce_json_object(getattr(target, "metadata", None))
    raw_record = coerce_json_object(target_metadata.get("raw_record"))
    target_source_record_id = getattr(target, "source_record_id", None)
    target_pubmed_id = getattr(target, "pubmed_id", None)
    document_scope_id = (
        target_source_record_id.strip()
        if isinstance(target_source_record_id, str) and target_source_record_id.strip()
        else (
            target_pubmed_id.strip()
            if isinstance(target_pubmed_id, str) and target_pubmed_id.strip()
            else None
        )
    )
    title = _resolve_title(raw_record)
    publication_date = raw_record.get("publication_date")
    journal = raw_record.get("journal")
    runtime.record_trace_event(
        event_type="document_found",
        scope_kind="document",
        stage="ingestion",
        scope_id=document_scope_id,
        message=(
            f"Discovered candidate paper {document_scope_id}."
            if document_scope_id is not None
            else "Discovered candidate paper."
        ),
        status="discovered",
        payload={
            "source_record_id": document_scope_id,
            "pubmed_id": (
                target_pubmed_id.strip()
                if isinstance(target_pubmed_id, str) and target_pubmed_id.strip()
                else None
            ),
            "title": title,
            "journal": journal if isinstance(journal, str) else None,
            "publication_date": (
                publication_date if isinstance(publication_date, str) else None
            ),
            "payload_ref": getattr(target, "payload_ref", None),
            "raw_storage_key": getattr(target, "raw_storage_key", None),
        },
    )


def _resolve_title(raw_record: JSONObject) -> str | None:
    for title_key in ("title", "article_title", "publication_title"):
        raw_title = raw_record.get(title_key)
        if isinstance(raw_title, str) and raw_title.strip():
            return raw_title.strip()
    return None


def _normalized_string(raw_value: object) -> str | None:
    return (
        raw_value.strip() if isinstance(raw_value, str) and raw_value.strip() else None
    )


def _float_or_none(raw_value: object) -> float | None:
    return float(raw_value) if isinstance(raw_value, int | float) else None


__all__ = ["run_ingestion_stage"]
