"""Runtime helpers for pipeline trace writes and ingestion progress bridging."""

# ruff: noqa: SLF001

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.application.services._pipeline_orchestration_checkpoint_metadata import (
    coerce_json_object,
)
from src.application.services._pipeline_orchestration_direct_cost_runtime import (
    PipelineExecutionDirectCostRuntimeMixin,
)
from src.application.services._pipeline_orchestration_execution_utils import (
    coerce_optional_uuid,
    json_int,
    json_string,
)

if TYPE_CHECKING:
    from datetime import datetime

    from src.domain.services.ingestion import IngestionProgressUpdate
    from src.type_definitions.common import JSONObject

    from ._pipeline_orchestration_execution_models import (
        PipelineExecutionContext,
        PipelineExecutionState,
    )
    from ._pipeline_orchestration_execution_protocols import _PipelineExecutionSelf

logger = logging.getLogger(__name__)


class PipelineExecutionRuntime(PipelineExecutionDirectCostRuntimeMixin):
    """Bridge trace persistence and live progress updates into pipeline state."""

    def __init__(
        self,
        *,
        helper: _PipelineExecutionSelf,
        context: PipelineExecutionContext,
        state: PipelineExecutionState,
    ) -> None:
        self._helper = helper
        self._context = context
        self._state = state

    def record_trace_event(  # noqa: PLR0913
        self,
        *,
        event_type: str,
        scope_kind: str,
        message: str,
        stage: str | None = None,
        scope_id: str | None = None,
        level: str = "info",
        status: str | None = None,
        agent_kind: str | None = None,
        agent_run_id: str | None = None,
        error_code: str | None = None,
        occurred_at: datetime | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        duration_ms: int | None = None,
        queue_wait_ms: int | None = None,
        timeout_budget_ms: int | None = None,
        payload: JSONObject | None = None,
    ) -> None:
        trace_service = self._helper._pipeline_trace
        if trace_service is None:
            return
        try:
            trace_service.record_event(
                research_space_id=self._context.research_space_id,
                source_id=self._context.source_id,
                pipeline_run_id=self._context.run_id,
                event_type=event_type,
                stage=stage,
                scope_kind=scope_kind,
                scope_id=scope_id,
                level=level,
                status=status,
                agent_kind=agent_kind,
                agent_run_id=agent_run_id,
                error_code=error_code,
                occurred_at=occurred_at,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                queue_wait_ms=queue_wait_ms,
                timeout_budget_ms=timeout_budget_ms,
                message=message,
                payload=coerce_json_object(payload) if payload is not None else None,
            )
        except (
            RuntimeError,
            TypeError,
            ValueError,
            ValidationError,
            SQLAlchemyError,
        ):
            logger.warning(
                "Failed to persist pipeline trace event %s for run_id=%s",
                event_type,
                self._context.run_id,
                exc_info=True,
            )

    def record_stage_warning_messages(
        self,
        *,
        stage: str,
        warnings: tuple[str, ...] | list[str],
        occurred_at: datetime,
        agent_kind: str | None = None,
    ) -> None:
        seen_messages: set[str] = set()
        for raw_warning in warnings:
            normalized_warning = raw_warning.strip()
            if not normalized_warning or normalized_warning in seen_messages:
                continue
            seen_messages.add(normalized_warning)
            self.record_trace_event(
                event_type="stage_warning",
                scope_kind="run",
                stage=stage,
                message=normalized_warning,
                level="warning",
                status="warning",
                agent_kind=agent_kind,
                error_code=resolve_pipeline_error_category((normalized_warning,)),
                occurred_at=occurred_at,
                payload={"warning": normalized_warning},
            )

    def persist_timing_summary(  # noqa: PLR0913
        self,
        *,
        stage: str,
        status: str | None,
        stage_started_at: datetime | None,
        stage_completed_at: datetime | None,
        duration_ms: int | None,
        queue_wait_ms: int | None = None,
        timeout_budget_ms: int | None = None,
        total_duration_ms: int | None = None,
    ) -> None:
        trace_service = self._helper._pipeline_trace
        if trace_service is None:
            return
        try:
            existing_timing_summary = {}
            if self._state.pipeline_run_job is not None:
                metadata = coerce_json_object(self._state.pipeline_run_job.metadata)
                pipeline_payload = coerce_json_object(metadata.get("pipeline_run"))
                existing_timing_summary = coerce_json_object(
                    pipeline_payload.get("timing_summary"),
                )
            timing_summary = trace_service.merge_timing_summary(
                existing_summary=existing_timing_summary,
                stage_timing=trace_service.build_stage_timing(
                    stage=stage,
                    status=status,
                    started_at=stage_started_at,
                    completed_at=stage_completed_at,
                    duration_ms=duration_ms,
                    queue_wait_ms=queue_wait_ms,
                    timeout_budget_ms=timeout_budget_ms,
                ),
                total_duration_ms=total_duration_ms,
            )
            self._state.pipeline_run_job = self._helper._persist_pipeline_run_progress(
                run_job=self._state.pipeline_run_job,
                source_id=self._context.source_id,
                research_space_id=self._context.research_space_id,
                run_id=self._context.run_id,
                resume_from_stage=self._context.resume_from_stage,
                progress_key="timing_summary",
                progress_payload=timing_summary.to_json_object(),
                overall_status="running",
            )
        except (
            RuntimeError,
            TypeError,
            ValueError,
            ValidationError,
            SQLAlchemyError,
        ):
            logger.warning(
                "Failed to persist pipeline timing summary for run_id=%s stage=%s",
                self._context.run_id,
                stage,
                exc_info=True,
            )

    def persist_query_progress(self, *, payload: JSONObject) -> None:
        self._state.pipeline_run_job = self._helper._persist_pipeline_run_progress(
            run_job=self._state.pipeline_run_job,
            source_id=self._context.source_id,
            research_space_id=self._context.research_space_id,
            run_id=self._context.run_id,
            resume_from_stage=self._context.resume_from_stage,
            progress_key="query_progress",
            progress_payload=payload,
            overall_status="running",
        )

    def persist_ingestion_progress(
        self,
        *,
        payload: JSONObject,
        event_type: str,
        message: str,
        occurred_at: datetime,
        ingestion_job_id: object,
    ) -> None:
        live_payload = coerce_json_object(payload)
        live_payload["event_type"] = event_type
        live_payload["message"] = message
        live_payload["occurred_at"] = occurred_at.isoformat(timespec="seconds")
        if ingestion_job_id is not None:
            live_payload["ingestion_job_id"] = str(ingestion_job_id)
        self._state.pipeline_run_job = self._helper._persist_pipeline_run_progress(
            run_job=self._state.pipeline_run_job,
            source_id=self._context.source_id,
            research_space_id=self._context.research_space_id,
            run_id=self._context.run_id,
            resume_from_stage=self._context.resume_from_stage,
            progress_key="ingestion_progress",
            progress_payload=live_payload,
            overall_status="running",
        )

    def handle_ingestion_progress(
        self,
        update: IngestionProgressUpdate,
    ) -> None:
        progress_payload = coerce_json_object(update.payload)
        progress_ingestion_job_id = update.ingestion_job_id or coerce_optional_uuid(
            progress_payload.get("ingestion_job_id"),
        )
        if progress_ingestion_job_id is not None:
            self._state.active_ingestion_job_id = progress_ingestion_job_id
            self._state.pipeline_run_job = self._helper._persist_pipeline_run_progress(
                run_job=self._state.pipeline_run_job,
                source_id=self._context.source_id,
                research_space_id=self._context.research_space_id,
                run_id=self._context.run_id,
                resume_from_stage=self._context.resume_from_stage,
                progress_key="run_scope",
                progress_payload={
                    "ingestion_job_id": str(progress_ingestion_job_id),
                },
                overall_status="running",
            )
        self.persist_ingestion_progress(
            payload=progress_payload,
            event_type=update.event_type,
            message=update.message,
            occurred_at=update.occurred_at,
            ingestion_job_id=progress_ingestion_job_id,
        )
        self._record_ingestion_trace_event(update=update, payload=progress_payload)

    def _record_ingestion_trace_event(  # noqa: C901, PLR0911
        self,
        *,
        update: IngestionProgressUpdate,
        payload: JSONObject,
    ) -> None:
        if update.event_type == "ingestion_job_started":
            self.record_trace_event(
                event_type="ingestion_job_started",
                scope_kind="run",
                stage="ingestion",
                message=update.message,
                status="running",
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "kernel_ingestion_record_started":
            self.record_trace_event(
                event_type="kernel_ingestion_record_started",
                scope_kind="document",
                scope_id=json_string(payload, "source_record_id"),
                stage="ingestion",
                message=update.message,
                status="running",
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "kernel_ingestion_mapper_started":
            mapper_name = json_string(payload, "mapper_name")
            self.record_trace_event(
                event_type="kernel_ingestion_mapper_started",
                scope_kind="document",
                scope_id=json_string(payload, "source_record_id"),
                stage="ingestion",
                message=update.message,
                status="running",
                agent_kind=mapper_name,
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "kernel_ingestion_mapper_finished":
            mapper_name = json_string(payload, "mapper_name")
            self.record_trace_event(
                event_type="kernel_ingestion_mapper_finished",
                scope_kind="document",
                scope_id=json_string(payload, "source_record_id"),
                stage="ingestion",
                message=update.message,
                status="completed",
                agent_kind=mapper_name,
                duration_ms=json_int(payload, "duration_ms"),
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "kernel_ingestion_record_finished":
            record_success = payload.get("success") is True
            self.record_trace_event(
                event_type="kernel_ingestion_record_finished",
                scope_kind="document",
                scope_id=json_string(payload, "source_record_id"),
                stage="ingestion",
                message=update.message,
                status="completed" if record_success else "failed",
                level="info" if record_success else "warning",
                duration_ms=json_int(payload, "duration_ms"),
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "resolver_warning":
            source_record_id = json_string(payload, "source_record_id")
            self.record_trace_event(
                event_type="resolver_warning",
                scope_kind="document" if source_record_id is not None else "run",
                scope_id=source_record_id,
                stage="ingestion",
                message=update.message,
                level="warning",
                status="warning",
                agent_kind="entity_resolver",
                error_code="resolver_policy_missing",
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "query_resolved":
            self._update_query_progress(payload)
            query_event_status = (
                "fallback"
                if self._state.query_generation_fallback_reason is not None
                else self._state.query_generation_decision
            )
            self.record_trace_event(
                event_type="query_resolved",
                scope_kind="query",
                scope_id=self._state.query_signature
                or self._state.query_generation_run_id,
                stage="ingestion",
                message=update.message,
                level=(
                    "warning"
                    if self._state.query_generation_fallback_reason is not None
                    else "info"
                ),
                status=query_event_status,
                agent_kind="query_generation",
                agent_run_id=self._state.query_generation_run_id,
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "records_fetched":
            fetched_records = payload.get("fetched_records")
            if isinstance(fetched_records, int):
                self._state.fetched_records = max(fetched_records, 0)
            self.record_trace_event(
                event_type="records_fetched",
                scope_kind="query",
                stage="ingestion",
                message=update.message,
                status="completed",
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "source_documents_upserted":
            self.record_trace_event(
                event_type="source_documents_upserted",
                scope_kind="document",
                stage="ingestion",
                message=update.message,
                status="completed",
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "kernel_ingestion_started":
            self.record_trace_event(
                event_type="kernel_ingestion_started",
                scope_kind="run",
                stage="ingestion",
                message=update.message,
                status="running",
                occurred_at=update.occurred_at,
                payload=payload,
            )
            return

        if update.event_type == "kernel_ingestion_finished":
            error_count = json_int(payload, "error_count") or 0
            self.record_trace_event(
                event_type="kernel_ingestion_finished",
                scope_kind="run",
                stage="ingestion",
                message=update.message,
                status="completed" if payload.get("success") is True else "warning",
                level="warning" if error_count > 0 else "info",
                occurred_at=update.occurred_at,
                payload=payload,
            )

    def _update_query_progress(self, payload: JSONObject) -> None:
        self._state.executed_query = (
            json_string(payload, "executed_query") or self._state.executed_query
        )
        self._state.query_signature = (
            json_string(payload, "query_signature") or self._state.query_signature
        )
        self._state.query_generation_decision = (
            json_string(payload, "query_generation_decision")
            or self._state.query_generation_decision
        )
        raw_confidence = payload.get("query_generation_confidence")
        if isinstance(raw_confidence, int | float):
            self._state.query_generation_confidence = float(raw_confidence)
        self._state.query_generation_run_id = (
            json_string(payload, "query_generation_run_id")
            or self._state.query_generation_run_id
        )
        self._state.query_generation_execution_mode = (
            json_string(payload, "query_generation_execution_mode")
            or self._state.query_generation_execution_mode
        )
        self._state.query_generation_fallback_reason = (
            json_string(payload, "query_generation_fallback_reason")
            or self._state.query_generation_fallback_reason
        )
        self.persist_query_progress(payload=payload)


__all__ = ["PipelineExecutionRuntime"]
