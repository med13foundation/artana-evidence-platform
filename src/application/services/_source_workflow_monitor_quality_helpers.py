"""Extraction quality helpers for source workflow monitor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import desc, select

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)
from src.models.database.source_document import SourceDocumentModel

from ._source_workflow_monitor_shared import (
    coerce_json_object,
    normalize_optional_string,
    safe_int,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub


class SourceWorkflowMonitorQualityMixin:
    """Extraction quality and warning summaries for monitor payloads."""

    _session: Session
    _TIMEOUT_FAILURE_REASONS: frozenset[str] = frozenset(
        {
            "agent_execution_timeout",
            "extraction_stage_timeout",
        },
    )
    _TIMEOUT_ERROR_CODE_SUFFIX: str = "TIMEOUT"

    def _build_warnings(self, *, extraction_rows: list[JSONObject]) -> list[str]:
        warnings: list[str] = []
        no_full_text_count = 0
        all_rejected_count = 0

        for extraction in extraction_rows:
            text_source = normalize_optional_string(extraction.get("text_source"))
            if text_source == "abstract":
                no_full_text_count += 1
            metadata = coerce_json_object(extraction.get("metadata"))
            funnel = coerce_json_object(metadata.get("extraction_stage_funnel"))
            generated = safe_int(funnel.get("relation_candidates_generated"))
            persisted = safe_int(funnel.get("relation_candidates_persisted"))
            if generated > 0 and persisted == 0:
                all_rejected_count += 1

        if no_full_text_count > 0:
            warnings.append(
                (
                    f"{no_full_text_count} extraction(s) used abstract-only text because "
                    "full text was unavailable."
                ),
            )
        if all_rejected_count > 0:
            warnings.append(
                (
                    f"{all_rejected_count} extraction(s) generated relation candidates "
                    "but persisted zero relations."
                ),
            )
        return warnings

    def _count_document_extraction_outcomes(
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
    ) -> tuple[int, int, int, int]:
        normalized_run_id = (
            run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
        )
        normalized_ingestion_job_id = (
            ingestion_job_id.strip()
            if isinstance(ingestion_job_id, str) and ingestion_job_id.strip()
            else None
        )
        statement = (
            select(
                SourceDocumentModel.extraction_status,
                SourceDocumentModel.ingestion_job_id,
                SourceDocumentModel.metadata_payload,
            )
            .where(SourceDocumentModel.source_id == str(source_id))
            .order_by(desc(SourceDocumentModel.created_at))
        )
        rows = self._session.execute(statement).all()
        extracted = 0
        failed = 0
        skipped = 0
        timeout_failed = 0
        for status_raw, row_ingestion_job_id_raw, metadata_raw in rows:
            row_ingestion_job_id = normalize_optional_string(row_ingestion_job_id_raw)
            metadata = coerce_json_object(metadata_raw)
            row_run_id = normalize_optional_string(metadata.get("pipeline_run_id"))
            if normalized_run_id is not None:
                if row_run_id != normalized_run_id:
                    continue
            elif (
                normalized_ingestion_job_id is not None
                and row_ingestion_job_id != normalized_ingestion_job_id
            ):
                continue
            normalized_status = normalize_optional_string(status_raw)
            if normalized_status == "extracted":
                extracted += 1
            elif normalized_status == "failed":
                if self._is_capacity_failure(metadata=metadata):
                    continue
                failed += 1
                if self._is_timeout_failure(metadata=metadata):
                    timeout_failed += 1
            elif normalized_status == "skipped":
                skipped += 1
        return extracted, failed, skipped, timeout_failed

    def _is_capacity_failure(self, *, metadata: JSONObject) -> bool:
        candidate_messages: list[str] = []
        for key in (
            "entity_recognition_error",
            "extraction_stage_error",
            "entity_recognition_error_code",
            "extraction_stage_error_code",
            "entity_recognition_error_class",
            "extraction_stage_error_class",
        ):
            value = normalize_optional_string(metadata.get(key))
            if value is not None:
                candidate_messages.append(value)
        return resolve_pipeline_error_category(candidate_messages) == "capacity"

    def _is_timeout_failure(self, *, metadata: JSONObject) -> bool:
        for reason_key in (
            "entity_recognition_failure_reason",
            "extraction_stage_failure_reason",
        ):
            reason = normalize_optional_string(metadata.get(reason_key))
            if reason in self._TIMEOUT_FAILURE_REASONS:
                return True

        extraction_error_code = normalize_optional_string(
            metadata.get("extraction_stage_error_code"),
        )
        if extraction_error_code is not None and extraction_error_code.endswith(
            self._TIMEOUT_ERROR_CODE_SUFFIX,
        ):
            return True

        for error_key in ("entity_recognition_error", "extraction_stage_error"):
            error_value = normalize_optional_string(metadata.get(error_key))
            if error_value is None:
                continue
            if "timeout" in error_value.lower():
                return True
        return False


__all__ = ["SourceWorkflowMonitorQualityMixin"]
