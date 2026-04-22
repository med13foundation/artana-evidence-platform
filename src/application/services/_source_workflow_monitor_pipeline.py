"""Pipeline and source/read-model loading helpers for workflow monitor."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from sqlalchemy import desc, select

from src.models.database.extraction_queue import ExtractionQueueItemModel
from src.models.database.ingestion_job import IngestionJobKindEnum, IngestionJobModel
from src.models.database.publication_extraction import PublicationExtractionModel
from src.models.database.source_document import SourceDocumentModel
from src.models.database.user_data_source import UserDataSourceModel

from ._source_workflow_monitor_shared import (
    PipelineRunRecord,
    coerce_json_list,
    coerce_json_object,
    normalize_optional_string,
    parse_uuid_runtime,
    safe_int,
)
from .pipeline_run_trace_service import parse_cost_summary, parse_timing_summary

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub

_TERMINAL_PIPELINE_ROW_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "partial"},
)


def _resolve_monitor_pipeline_status(
    *,
    row_status: str | None,
    pipeline_status: str | None,
) -> str | None:
    if row_status in _TERMINAL_PIPELINE_ROW_STATUSES:
        return row_status
    return pipeline_status or row_status


def _resolve_monitor_pipeline_queue_status(
    *,
    row_status: str | None,
    pipeline_status: str | None,
    queue_status: str | None,
) -> str | None:
    if row_status in _TERMINAL_PIPELINE_ROW_STATUSES:
        return row_status
    return queue_status or pipeline_status or row_status


class SourceWorkflowMonitorPipelineMixin:
    """Data loading and shaping helpers for source workflow monitoring."""

    _session: Session
    _RUN_SCOPED_PREFETCH_MULTIPLIER = 10
    _RUN_SCOPED_PREFETCH_FLOOR = 500
    _MONITOR_PREFETCH_HARD_CAP = 2_000
    _PIPELINE_RUN_SCAN_MULTIPLIER = 6
    _PIPELINE_RUN_SCAN_HARD_CAP = 5_000

    @classmethod
    def _resolve_prefetch_limit(
        cls,
        *,
        limit: int,
        run_scoped: bool,
    ) -> int:
        requested_limit = max(limit, 1)
        if run_scoped:
            requested_limit = max(
                requested_limit * cls._RUN_SCOPED_PREFETCH_MULTIPLIER,
                cls._RUN_SCOPED_PREFETCH_FLOOR,
            )
        return min(requested_limit, cls._MONITOR_PREFETCH_HARD_CAP)

    def _require_source(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
    ) -> UserDataSourceModel:
        statement = (
            select(UserDataSourceModel)
            .where(UserDataSourceModel.id == str(source_id))
            .where(UserDataSourceModel.research_space_id == str(space_id))
            .limit(1)
        )
        source = self._session.execute(statement).scalar_one_or_none()
        if source is None:
            msg = "Data source not found in this research space"
            raise LookupError(msg)
        return source

    def _load_pipeline_runs(
        self,
        *,
        source_id: UUID,
        limit: int,
    ) -> list[PipelineRunRecord]:
        fetch_limit = min(
            max(limit, 1) * self._PIPELINE_RUN_SCAN_MULTIPLIER,
            self._PIPELINE_RUN_SCAN_HARD_CAP,
        )
        statement = (
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .where(
                IngestionJobModel.job_kind
                == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
            )
            .order_by(desc(IngestionJobModel.triggered_at))
            .limit(fetch_limit)
        )
        rows = self._session.execute(statement).scalars().all()

        run_records: list[PipelineRunRecord] = []
        for row in rows:
            metadata = coerce_json_object(row.job_metadata)
            pipeline_payload = coerce_json_object(metadata.get("pipeline_run"))
            run_id = normalize_optional_string(pipeline_payload.get("run_id"))
            if run_id is None:
                continue
            payload = self._build_pipeline_run_payload(
                row=row,
                pipeline_payload=pipeline_payload,
            )
            run_records.append(
                PipelineRunRecord(
                    payload=payload,
                    run_id=run_id,
                    job_id=str(row.id),
                ),
            )
            if len(run_records) >= limit:
                break
        return run_records

    def _load_pipeline_run_by_id(
        self,
        *,
        source_id: UUID,
        run_id: str,
    ) -> PipelineRunRecord | None:
        normalized_run_id = run_id.strip()
        if not normalized_run_id:
            return None

        statement = (
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .where(
                IngestionJobModel.job_kind
                == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
            )
            .order_by(desc(IngestionJobModel.triggered_at))
        )
        rows = self._session.execute(statement).scalars().all()
        for row in rows:
            metadata = coerce_json_object(row.job_metadata)
            pipeline_payload = coerce_json_object(metadata.get("pipeline_run"))
            candidate_run_id = normalize_optional_string(pipeline_payload.get("run_id"))
            if candidate_run_id != normalized_run_id:
                continue
            payload = self._build_pipeline_run_payload(
                row=row,
                pipeline_payload=pipeline_payload,
            )
            return PipelineRunRecord(
                payload=payload,
                run_id=normalized_run_id,
                job_id=str(row.id),
            )
        return None

    def _resolve_run_record(
        self,
        *,
        source_id: UUID,
        requested_run_id: str | None,
        recent_limit: int,
    ) -> PipelineRunRecord | None:
        recent_runs = self._load_pipeline_runs(source_id=source_id, limit=recent_limit)
        if requested_run_id is None or not requested_run_id.strip():
            return self._select_run_record(recent_runs, None)

        normalized_run_id = requested_run_id.strip()
        for recent_record in recent_runs:
            if recent_record.run_id == normalized_run_id:
                return recent_record

        direct_record = self._load_pipeline_run_by_id(
            source_id=source_id,
            run_id=normalized_run_id,
        )
        if direct_record is not None:
            return direct_record

        msg = f"Pipeline run '{normalized_run_id}' not found for this source"
        raise LookupError(msg)

    @staticmethod
    def _select_run_record(
        run_records: list[PipelineRunRecord],
        requested_run_id: str | None,
    ) -> PipelineRunRecord | None:
        if not run_records:
            if requested_run_id is not None and requested_run_id.strip():
                msg = f"Pipeline run '{requested_run_id.strip()}' not found for this source"
                raise LookupError(msg)
            return None
        if requested_run_id is None or not requested_run_id.strip():
            return run_records[0]
        normalized = requested_run_id.strip()
        for record in run_records:
            if record.run_id == normalized:
                return record
        msg = f"Pipeline run '{normalized}' not found for this source"
        raise LookupError(msg)

    def _build_pipeline_run_payload(  # noqa: C901, PLR0912, PLR0915
        self,
        *,
        row: IngestionJobModel,
        pipeline_payload: JSONObject,
    ) -> JSONObject:
        checkpoints = coerce_json_object(pipeline_payload.get("checkpoints"))
        stage_statuses, stage_errors = self._parse_stage_details(checkpoints)

        metrics = coerce_json_object(row.metrics)
        metadata = coerce_json_object(row.job_metadata)
        query_generation = coerce_json_object(metadata.get("query_generation"))
        extraction_queue_meta = coerce_json_object(metadata.get("extraction_queue"))
        extraction_run_meta = coerce_json_object(
            pipeline_payload.get("extraction_run"),
        )
        if not extraction_run_meta:
            extraction_run_meta = coerce_json_object(metadata.get("extraction_run"))
        graph_progress = coerce_json_object(pipeline_payload.get("graph_progress"))
        timing_summary_payload = coerce_json_object(
            pipeline_payload.get("timing_summary"),
        )
        parsed_timing_summary = parse_timing_summary(timing_summary_payload)
        cost_summary_payload = coerce_json_object(pipeline_payload.get("cost_summary"))
        parsed_cost_summary = parse_cost_summary(cost_summary_payload)
        source_row = getattr(row, "source", None)
        if (
            parsed_cost_summary is None
            and hasattr(self, "_pipeline_trace")
            and self._pipeline_trace is not None
        ):
            research_space_id = parse_uuid_runtime(
                pipeline_payload.get("research_space_id"),
            ) or parse_uuid_runtime(getattr(source_row, "research_space_id", None))
            run_id = normalize_optional_string(pipeline_payload.get("run_id"))
            if research_space_id is not None and run_id is not None:
                parsed_cost_summary = self._pipeline_trace.resolve_cost_summary(
                    research_space_id=research_space_id,
                    pipeline_run_id=run_id,
                )
        extraction_processed = safe_int(extraction_run_meta.get("processed"))
        extraction_completed = safe_int(extraction_run_meta.get("completed"))
        extraction_failed = safe_int(extraction_run_meta.get("failed"))
        if extraction_run_meta.get("processed") is None:
            extraction_processed = safe_int(graph_progress.get("extraction_processed"))
        if extraction_run_meta.get("completed") is None:
            extraction_completed = safe_int(graph_progress.get("extraction_completed"))
        if extraction_run_meta.get("failed") is None:
            extraction_failed = safe_int(graph_progress.get("extraction_failed"))
        run_scope = coerce_json_object(pipeline_payload.get("run_scope"))
        run_ingestion_job_id = normalize_optional_string(
            run_scope.get("ingestion_job_id"),
        )
        if run_ingestion_job_id is None:
            run_ingestion_job_id = normalize_optional_string(
                pipeline_payload.get("ingestion_job_id"),
            )
        idempotency_checkpoint_after = self._resolve_idempotency_checkpoint_after(
            row=row,
            metadata=metadata,
            ingestion_job_id=run_ingestion_job_id,
        )
        stage_counters: JSONObject = {
            "records_processed": safe_int(metrics.get("records_processed")),
            "records_failed": safe_int(metrics.get("records_failed")),
            "records_skipped": safe_int(metrics.get("records_skipped")),
            "queued_for_extraction": safe_int(extraction_queue_meta.get("queued")),
            "extraction_processed": extraction_processed,
            "extraction_completed": extraction_completed,
            "extraction_failed": extraction_failed,
            "graph_requested": safe_int(graph_progress.get("requested")),
            "graph_processed": safe_int(graph_progress.get("processed")),
            "graph_completed": safe_int(graph_progress.get("completed")),
            "persisted_relations": safe_int(graph_progress.get("persisted_relations")),
            "extraction_persisted_relations": safe_int(
                graph_progress.get("extraction_persisted_relations"),
            ),
            "extraction_concept_members_created": safe_int(
                graph_progress.get("extraction_concept_members_created"),
            ),
            "extraction_concept_aliases_created": safe_int(
                graph_progress.get("extraction_concept_aliases_created"),
            ),
            "extraction_concept_decisions_proposed": safe_int(
                graph_progress.get("extraction_concept_decisions_proposed"),
            ),
            "graph_stage_persisted_relations": safe_int(
                graph_progress.get("graph_stage_persisted_relations"),
            ),
            "relevance_filtered_out_count": safe_int(
                idempotency_checkpoint_after.get("filtered_out_count"),
            ),
            "relevance_pre_rescue_filtered_out_count": safe_int(
                idempotency_checkpoint_after.get("pre_rescue_filtered_out_count"),
            ),
            "full_text_rescue_attempted_count": safe_int(
                idempotency_checkpoint_after.get("full_text_rescue_attempted_count"),
            ),
            "full_text_rescued_count": safe_int(
                idempotency_checkpoint_after.get("full_text_rescued_count"),
            ),
        }

        source_snapshot = coerce_json_object(row.source_config_snapshot)
        source_metadata = coerce_json_object(source_snapshot.get("metadata"))
        query_progress = coerce_json_object(pipeline_payload.get("query_progress"))
        executed_query = normalize_optional_string(metadata.get("executed_query"))
        if executed_query is None:
            executed_query = normalize_optional_string(
                query_progress.get("executed_query"),
            )
        if executed_query is None:
            executed_query = normalize_optional_string(source_metadata.get("query"))
        row_status = normalize_optional_string(row.status.value)
        pipeline_status = normalize_optional_string(pipeline_payload.get("status"))
        queue_status = normalize_optional_string(pipeline_payload.get("queue_status"))
        owner_payload = coerce_json_object(pipeline_payload.get("owner"))
        run_owner_user_id = normalize_optional_string(
            owner_payload.get("run_owner_user_id"),
        )
        run_owner_source = normalize_optional_string(
            owner_payload.get("run_owner_source"),
        )
        if run_owner_user_id is None:
            triggered_by = normalize_optional_string(getattr(row, "triggered_by", None))
            source_owner_id = normalize_optional_string(
                getattr(source_row, "owner_id", None),
            )
            if triggered_by is not None:
                run_owner_user_id = triggered_by
                run_owner_source = "triggered_by"
            elif source_owner_id is not None:
                run_owner_user_id = source_owner_id
                run_owner_source = "source_owner"
            else:
                run_owner_source = "system"

        total_cost_usd = (
            parsed_cost_summary.total_cost_usd
            if parsed_cost_summary is not None
            else 0.0
        )
        extracted_count = max(extraction_completed, 0)
        persisted_relation_count = max(
            safe_int(graph_progress.get("persisted_relations")),
            safe_int(graph_progress.get("graph_stage_persisted_relations")),
            safe_int(graph_progress.get("extraction_persisted_relations")),
        )
        full_text_rescue_attempted = safe_int(
            idempotency_checkpoint_after.get("full_text_rescue_attempted_count"),
        )
        full_text_rescued = safe_int(
            idempotency_checkpoint_after.get("full_text_rescued_count"),
        )
        diagnostic_signals: JSONObject = {
            "extraction_failure_ratio": (
                round(extraction_failed / extraction_processed, 6)
                if extraction_processed > 0
                else 0.0
            ),
            "full_text_rescue_dependence": (
                round(full_text_rescued / full_text_rescue_attempted, 6)
                if full_text_rescue_attempted > 0
                else 0.0
            ),
            "cost_per_extracted_document": (
                round(total_cost_usd / extracted_count, 8)
                if extracted_count > 0
                else 0.0
            ),
            "cost_per_persisted_relation": (
                round(total_cost_usd / persisted_relation_count, 8)
                if persisted_relation_count > 0
                else 0.0
            ),
        }
        paper_candidate_summary: JSONObject = {
            "filtered_out_external_record_ids": [
                str(item)
                for item in coerce_json_list(
                    idempotency_checkpoint_after.get("filtered_out_pubmed_ids"),
                )
                if normalize_optional_string(item) is not None
            ],
            "pre_rescue_filtered_external_record_ids": [
                str(item)
                for item in coerce_json_list(
                    idempotency_checkpoint_after.get(
                        "pre_rescue_filtered_out_pubmed_ids",
                    ),
                )
                if normalize_optional_string(item) is not None
            ],
            "full_text_rescued_external_record_ids": [
                str(item)
                for item in coerce_json_list(
                    idempotency_checkpoint_after.get("full_text_rescued_pubmed_ids"),
                )
                if normalize_optional_string(item) is not None
            ],
        }

        return {
            "job_id": str(row.id),
            "run_id": str(pipeline_payload.get("run_id")),
            "ingestion_job_id": run_ingestion_job_id,
            "status": _resolve_monitor_pipeline_status(
                row_status=row_status,
                pipeline_status=pipeline_status,
            ),
            "queue_status": _resolve_monitor_pipeline_queue_status(
                row_status=row_status,
                pipeline_status=pipeline_status,
                queue_status=queue_status,
            ),
            "triggered_at": row.triggered_at,
            "accepted_at": normalize_optional_string(
                pipeline_payload.get("accepted_at"),
            ),
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "resume_from_stage": normalize_optional_string(
                pipeline_payload.get("resume_from_stage"),
            ),
            "attempt_count": safe_int(pipeline_payload.get("attempt_count")),
            "next_attempt_at": normalize_optional_string(
                pipeline_payload.get("next_attempt_at"),
            ),
            "last_error": normalize_optional_string(pipeline_payload.get("last_error")),
            "error_category": normalize_optional_string(
                pipeline_payload.get("error_category"),
            ),
            "worker_id": normalize_optional_string(pipeline_payload.get("worker_id")),
            "executed_query": executed_query,
            "query_progress": query_progress,
            "query_generation": query_generation,
            "stage_statuses": stage_statuses,
            "stage_errors": stage_errors,
            "stage_checkpoints": checkpoints,
            "stage_counters": stage_counters,
            "timing_summary": (
                parsed_timing_summary.to_json_object()
                if parsed_timing_summary is not None
                else timing_summary_payload
            ),
            "cost_summary": (
                parsed_cost_summary.to_json_object()
                if parsed_cost_summary is not None
                else cost_summary_payload
            ),
            "run_owner_user_id": run_owner_user_id,
            "run_owner_source": run_owner_source,
            "diagnostic_signals": diagnostic_signals,
            "paper_candidate_summary": paper_candidate_summary,
        }

    @staticmethod
    def _parse_stage_details(
        checkpoints: JSONObject,
    ) -> tuple[dict[str, str], dict[str, str]]:
        statuses: dict[str, str] = {}
        errors: dict[str, str] = {}
        for stage_name, raw_value in checkpoints.items():
            checkpoint = coerce_json_object(raw_value)
            status = normalize_optional_string(checkpoint.get("status"))
            if status is not None:
                statuses[str(stage_name)] = status
            stage_error = normalize_optional_string(checkpoint.get("error"))
            if stage_error is not None:
                errors[str(stage_name)] = stage_error
        return statuses, errors

    def _build_source_snapshot(self, source: UserDataSourceModel) -> JSONObject:
        configuration = coerce_json_object(source.configuration)
        metadata = coerce_json_object(configuration.get("metadata"))
        agent_config = coerce_json_object(metadata.get("agent_config"))

        return {
            "source_id": str(source.id),
            "name": source.name,
            "source_type": source.source_type.value,
            "status": source.status.value,
            "schedule": coerce_json_object(source.ingestion_schedule),
            "query": normalize_optional_string(metadata.get("query"))
            or normalize_optional_string(configuration.get("query")),
            "model_id": normalize_optional_string(agent_config.get("model_id")),
            "open_access_only": metadata.get("open_access_only"),
            "max_results": metadata.get("max_results"),
            "agent_prompt": normalize_optional_string(
                agent_config.get("agent_prompt"),
            ),
            "use_research_space_context": agent_config.get(
                "use_research_space_context",
            ),
            "is_ai_managed": agent_config.get("is_ai_managed"),
            "relevance_threshold": metadata.get("relevance_threshold"),
            "full_text_entity_rescue_enabled": metadata.get(
                "full_text_entity_rescue_enabled",
            ),
            "full_text_entity_rescue_terms": metadata.get(
                "full_text_entity_rescue_terms",
            ),
        }

    def _resolve_idempotency_checkpoint_after(
        self,
        *,
        row: IngestionJobModel,
        metadata: JSONObject,
        ingestion_job_id: str | None,
    ) -> JSONObject:
        idempotency = coerce_json_object(metadata.get("idempotency"))
        checkpoint_after = coerce_json_object(idempotency.get("checkpoint_after"))
        if checkpoint_after:
            return checkpoint_after
        if ingestion_job_id is None or ingestion_job_id == str(row.id):
            return {}

        statement = (
            select(IngestionJobModel.job_metadata)
            .where(IngestionJobModel.id == ingestion_job_id)
            .limit(1)
        )
        linked_job_metadata_raw = self._session.execute(statement).scalar_one_or_none()
        linked_job_metadata = coerce_json_object(linked_job_metadata_raw)
        linked_idempotency = coerce_json_object(linked_job_metadata.get("idempotency"))
        return coerce_json_object(linked_idempotency.get("checkpoint_after"))

    @staticmethod
    def _normalize_paper_external_record_id(
        *,
        source_type: str | None,
        record_id: object,
    ) -> str | None:
        normalized = normalize_optional_string(record_id)
        if normalized is None:
            return None
        if source_type == "pubmed" and normalized.isdigit():
            return f"pubmed:pubmed_id:{normalized}"
        return normalized

    def _build_run_paper_candidates(
        self,
        *,
        source_type: str | None,
        selected_run_payload: JSONObject,
        documents: list[JSONObject],
    ) -> list[JSONObject]:
        paper_summary = coerce_json_object(
            selected_run_payload.get("paper_candidate_summary"),
        )
        filtered_out_ids = [
            normalized
            for item in coerce_json_list(
                paper_summary.get("filtered_out_external_record_ids"),
            )
            if (
                normalized := self._normalize_paper_external_record_id(
                    source_type=source_type,
                    record_id=item,
                )
            )
            is not None
        ]
        pre_rescue_filtered_ids = [
            normalized
            for item in coerce_json_list(
                paper_summary.get("pre_rescue_filtered_external_record_ids"),
            )
            if (
                normalized := self._normalize_paper_external_record_id(
                    source_type=source_type,
                    record_id=item,
                )
            )
            is not None
        ]
        rescued_ids = [
            normalized
            for item in coerce_json_list(
                paper_summary.get("full_text_rescued_external_record_ids"),
            )
            if (
                normalized := self._normalize_paper_external_record_id(
                    source_type=source_type,
                    record_id=item,
                )
            )
            is not None
        ]

        document_by_external_id: dict[str, JSONObject] = {}
        for document in documents:
            external_record_id = normalize_optional_string(
                document.get("external_record_id"),
            )
            if external_record_id is None:
                continue
            document_by_external_id[external_record_id] = document

        ordered_external_ids: list[str] = []
        for candidate_id in (
            list(document_by_external_id.keys())
            + pre_rescue_filtered_ids
            + filtered_out_ids
            + rescued_ids
        ):
            if candidate_id not in ordered_external_ids:
                ordered_external_ids.append(candidate_id)

        filtered_out_set = set(filtered_out_ids)
        pre_rescue_filtered_set = set(pre_rescue_filtered_ids)
        rescued_set = set(rescued_ids)

        paper_candidates: list[JSONObject] = []
        for external_record_id in ordered_external_ids:
            document = coerce_json_object(
                document_by_external_id.get(external_record_id),
            )
            is_rescued = external_record_id in rescued_set
            is_final_filtered = external_record_id in filtered_out_set
            was_pre_rescue_filtered = external_record_id in pre_rescue_filtered_set
            document_id = normalize_optional_string(document.get("id"))
            enrichment_status = normalize_optional_string(
                document.get("enrichment_status"),
            )
            extraction_status = normalize_optional_string(
                document.get("extraction_status"),
            )

            outcome = "processed"
            reason = "Retained after ingestion filtering and document upsert."
            if document_id is not None and is_rescued:
                outcome = "rescued_and_processed"
                reason = (
                    "Retained by full-text rescue after semantic relevance filtering."
                )
            elif document_id is None and is_final_filtered:
                outcome = "dropped"
                if was_pre_rescue_filtered:
                    reason = "Filtered out by semantic relevance; full-text rescue did not retain it."
                else:
                    reason = "Filtered out before source document creation."
            elif document_id is None and was_pre_rescue_filtered:
                outcome = "dropped"
                reason = "Filtered out before source document creation."

            paper_candidates.append(
                {
                    "external_record_id": external_record_id,
                    "paper_outcome": outcome,
                    "paper_reason": reason,
                    "rescued_by_full_text": is_rescued,
                    "pre_rescue_filtered": was_pre_rescue_filtered,
                    "document_id": document_id,
                    "enrichment_status": enrichment_status,
                    "extraction_status": extraction_status,
                },
            )
        return paper_candidates

    def _load_source_documents(
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        limit: int | None,
    ) -> list[JSONObject]:
        normalized_run_id = (
            run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
        )
        normalized_ingestion_job_id = (
            ingestion_job_id.strip()
            if isinstance(ingestion_job_id, str) and ingestion_job_id.strip()
            else None
        )
        statement = (
            select(SourceDocumentModel)
            .where(SourceDocumentModel.source_id == str(source_id))
            .order_by(desc(SourceDocumentModel.created_at))
        )
        if limit is not None:
            fetch_limit = self._resolve_prefetch_limit(
                limit=limit,
                run_scoped=(
                    normalized_run_id is not None
                    or normalized_ingestion_job_id is not None
                ),
            )
            statement = statement.limit(fetch_limit)
        rows = self._session.execute(statement).scalars().all()

        documents: list[JSONObject] = []
        for row in rows:
            row_ingestion_job_id = normalize_optional_string(row.ingestion_job_id)
            if (
                normalized_ingestion_job_id is not None
                and row_ingestion_job_id != normalized_ingestion_job_id
            ):
                continue
            metadata = coerce_json_object(row.metadata_payload)
            row_run_id = normalize_optional_string(metadata.get("pipeline_run_id"))
            if (
                normalized_run_id is not None
                and row_run_id is not None
                and row_run_id != normalized_run_id
            ):
                continue
            documents.append(
                {
                    "id": str(row.id),
                    "external_record_id": row.external_record_id,
                    "source_type": row.source_type,
                    "document_format": row.document_format,
                    "enrichment_status": row.enrichment_status,
                    "enrichment_agent_run_id": row.enrichment_agent_run_id,
                    "extraction_status": row.extraction_status,
                    "extraction_agent_run_id": row.extraction_agent_run_id,
                    "ingestion_job_id": row.ingestion_job_id,
                    "content_length_chars": row.content_length_chars,
                    "metadata": metadata,
                    "created_at": row.created_at.isoformat(),
                    "updated_at": row.updated_at.isoformat(),
                },
            )
            if limit is not None and len(documents) >= limit:
                break
        return documents

    def _load_extraction_queue(  # noqa: PLR0913 - explicit monitor filters are intentional
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        external_record_ids: set[str],
        limit: int | None,
    ) -> list[JSONObject]:
        normalized_run_id = (
            run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
        )
        normalized_ingestion_job_id = (
            ingestion_job_id.strip()
            if isinstance(ingestion_job_id, str) and ingestion_job_id.strip()
            else None
        )
        statement = (
            select(ExtractionQueueItemModel)
            .where(ExtractionQueueItemModel.source_id == str(source_id))
            .order_by(desc(ExtractionQueueItemModel.queued_at))
        )
        if limit is not None:
            fetch_limit = self._resolve_prefetch_limit(
                limit=limit,
                run_scoped=(
                    normalized_run_id is not None
                    or normalized_ingestion_job_id is not None
                ),
            )
            statement = statement.limit(fetch_limit)
        rows = self._session.execute(statement).scalars().all()

        queue_rows: list[JSONObject] = []
        for row in rows:
            row_ingestion_job_id = normalize_optional_string(row.ingestion_job_id)
            if (
                normalized_ingestion_job_id is not None
                and row_ingestion_job_id != normalized_ingestion_job_id
            ):
                continue
            metadata = coerce_json_object(row.metadata_payload)
            if normalized_run_id is not None and (
                (
                    normalize_optional_string(metadata.get("pipeline_run_id"))
                    not in {None, normalized_run_id}
                )
                or row.source_record_id not in external_record_ids
            ):
                continue
            queue_rows.append(
                {
                    "id": str(row.id),
                    "source_record_id": row.source_record_id,
                    "pubmed_id": row.pubmed_id,
                    "status": row.status.value,
                    "attempts": row.attempts,
                    "last_error": row.last_error,
                    "ingestion_job_id": row.ingestion_job_id,
                    "queued_at": row.queued_at.isoformat(),
                    "started_at": (
                        row.started_at.isoformat() if row.started_at else None
                    ),
                    "completed_at": (
                        row.completed_at.isoformat() if row.completed_at else None
                    ),
                    "metadata": metadata,
                },
            )
            if limit is not None and len(queue_rows) >= limit:
                break
        return queue_rows

    def _load_publication_extractions(  # noqa: PLR0913 - explicit monitor filters are intentional
        self,
        *,
        source_id: UUID,
        run_id: str | None,
        ingestion_job_id: str | None,
        queue_item_ids: set[str],
        limit: int | None,
    ) -> list[JSONObject]:
        normalized_run_id = (
            run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
        )
        normalized_ingestion_job_id = (
            ingestion_job_id.strip()
            if isinstance(ingestion_job_id, str) and ingestion_job_id.strip()
            else None
        )
        statement = (
            select(PublicationExtractionModel)
            .where(PublicationExtractionModel.source_id == str(source_id))
            .order_by(desc(PublicationExtractionModel.extracted_at))
        )
        if limit is not None:
            fetch_limit = self._resolve_prefetch_limit(
                limit=limit,
                run_scoped=(
                    normalized_run_id is not None
                    or normalized_ingestion_job_id is not None
                ),
            )
            statement = statement.limit(fetch_limit)
        rows = self._session.execute(statement).scalars().all()

        extraction_rows: list[JSONObject] = []
        for row in rows:
            row_ingestion_job_id = normalize_optional_string(row.ingestion_job_id)
            if (
                normalized_ingestion_job_id is not None
                and row_ingestion_job_id != normalized_ingestion_job_id
            ):
                continue
            metadata = coerce_json_object(row.metadata_payload)
            if normalized_run_id is not None and (
                (
                    normalize_optional_string(metadata.get("pipeline_run_id"))
                    not in {None, normalized_run_id}
                )
                or str(row.queue_item_id) not in queue_item_ids
            ):
                continue
            extraction_rows.append(
                {
                    "id": str(row.id),
                    "queue_item_id": str(row.queue_item_id),
                    "status": row.status.value,
                    "text_source": row.text_source,
                    "processor_name": row.processor_name,
                    "processor_version": row.processor_version,
                    "facts_count": len(row.facts or []),
                    "metadata": metadata,
                    "extracted_at": row.extracted_at.isoformat(),
                },
            )
            if limit is not None and len(extraction_rows) >= limit:
                break
        return extraction_rows

    @staticmethod
    def _count_statuses(
        *,
        records: list[JSONObject],
        key: str,
    ) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for record in records:
            normalized = normalize_optional_string(record.get(key)) or "unknown"
            counter[normalized] += 1
        return dict(counter)


__all__ = ["SourceWorkflowMonitorPipelineMixin"]
