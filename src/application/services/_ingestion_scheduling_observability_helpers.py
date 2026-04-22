"""Observability helpers for ingestion scheduling execution paths."""

# mypy: disable-error-code="misc"

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.entities import ingestion_job

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.ingestion_scheduling_service import (
        IngestionSchedulingService,
    )
    from src.domain.services.ingestion import IngestionRunSummary

logger = logging.getLogger(__name__)

DEDUP_WARNING_THRESHOLD = 0.9
PROLONGED_QUERY_FALLBACK_THRESHOLD = 3
QUERY_FALLBACK_HISTORY_LIMIT = 25


class _IngestionSchedulingObservabilityHelpers:
    """Helpers for dedup/query-generation runtime telemetry emissions."""

    def _emit_dedup_telemetry(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
        summary: IngestionRunSummary,
    ) -> None:
        fetched_records = summary.fetched_records
        if fetched_records <= 0:
            return
        unchanged_records = self._int_summary_field(summary, "unchanged_records")
        new_records = self._int_summary_field(summary, "new_records")
        updated_records = self._int_summary_field(summary, "updated_records")
        dedup_ratio = unchanged_records / fetched_records
        log_extra = {
            "source_id": str(source_id),
            "fetched_records": fetched_records,
            "new_records": new_records,
            "updated_records": updated_records,
            "unchanged_records": unchanged_records,
            "dedup_ratio": round(dedup_ratio, 4),
        }
        checkpoint_after_raw = getattr(summary, "checkpoint_after", None)
        if isinstance(checkpoint_after_raw, dict):
            pre_rescue_filtered_out_count = self._int_payload_field(
                checkpoint_after_raw,
                "pre_rescue_filtered_out_count",
            )
            filtered_out_count = self._int_payload_field(
                checkpoint_after_raw,
                "filtered_out_count",
            )
            full_text_rescue_attempted_count = self._int_payload_field(
                checkpoint_after_raw,
                "full_text_rescue_attempted_count",
            )
            full_text_rescued_count = self._int_payload_field(
                checkpoint_after_raw,
                "full_text_rescued_count",
            )
            log_extra.update(
                {
                    "pre_rescue_filtered_out_count": pre_rescue_filtered_out_count,
                    "filtered_out_count": filtered_out_count,
                    "full_text_rescue_attempted_count": (
                        full_text_rescue_attempted_count
                    ),
                    "full_text_rescued_count": full_text_rescued_count,
                },
            )
        if dedup_ratio >= DEDUP_WARNING_THRESHOLD:
            logger.warning(
                "High dedup ratio detected for source ingestion run",
                extra=log_extra,
            )
            return
        logger.info("Source ingestion dedup telemetry", extra=log_extra)

    def _emit_query_generation_telemetry(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
        summary: IngestionRunSummary,
    ) -> None:
        execution_mode_raw = getattr(summary, "query_generation_execution_mode", None)
        if not isinstance(execution_mode_raw, str) or not execution_mode_raw.strip():
            return

        execution_mode = execution_mode_raw.strip().lower()
        decision_raw = getattr(summary, "query_generation_decision", None)
        decision = (
            decision_raw.strip().lower()
            if isinstance(decision_raw, str) and decision_raw.strip()
            else None
        )
        fallback_reason_raw = getattr(summary, "query_generation_fallback_reason", None)
        fallback_reason = (
            fallback_reason_raw.strip()
            if isinstance(fallback_reason_raw, str) and fallback_reason_raw.strip()
            else None
        )
        log_extra: dict[str, object] = {
            "source_id": str(source_id),
            "execution_mode": execution_mode,
            "decision": decision,
            "fallback_reason": fallback_reason,
        }

        if execution_mode != "deterministic":
            logger.info("AI query generation executed", extra=log_extra)
            return

        previous_fallback_runs = self._count_recent_deterministic_query_fallbacks(
            source_id=source_id,
        )
        consecutive_fallback_runs = previous_fallback_runs + 1
        log_extra["consecutive_fallback_runs"] = consecutive_fallback_runs
        if consecutive_fallback_runs >= PROLONGED_QUERY_FALLBACK_THRESHOLD:
            logger.warning(
                "Prolonged deterministic query fallback detected",
                extra=log_extra,
            )
            return

        logger.info(
            "Deterministic query fallback used for source ingestion run",
            extra=log_extra,
        )

    def _count_recent_deterministic_query_fallbacks(
        self: IngestionSchedulingService,
        *,
        source_id: UUID,
    ) -> int:
        recent_jobs = self._job_repository.find_by_source(
            source_id,
            limit=QUERY_FALLBACK_HISTORY_LIMIT,
        )
        fallback_count = 0
        for job in recent_jobs:
            if job.status == ingestion_job.IngestionStatus.RUNNING:
                continue
            metadata = job.metadata
            query_generation_payload = metadata.get("query_generation")
            if not isinstance(query_generation_payload, dict):
                if fallback_count > 0:
                    break
                continue

            mode_raw = query_generation_payload.get("execution_mode")
            if (
                isinstance(mode_raw, str)
                and mode_raw.strip().lower() == "deterministic"
            ):
                fallback_count += 1
                continue
            if isinstance(mode_raw, str) and mode_raw.strip():
                break
        return fallback_count

    @staticmethod
    def _int_payload_field(payload: dict[object, object], key: str) -> int:
        raw_value = payload.get(key)
        if isinstance(raw_value, int):
            return max(raw_value, 0)
        return 0
