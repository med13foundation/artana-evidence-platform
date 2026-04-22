"""Read-only workflow monitoring service for source pipeline visibility."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError

from src.models.database.ingestion_job import IngestionJobKindEnum, IngestionJobModel
from src.models.database.user_data_source import UserDataSourceModel

from ._source_workflow_monitor_events import SourceWorkflowMonitorEventsMixin
from ._source_workflow_monitor_progress import SourceWorkflowMonitorProgressMixin
from ._source_workflow_monitor_relations import SourceWorkflowMonitorRelationsMixin
from ._source_workflow_monitor_shared import (
    coerce_json_list,
    coerce_json_object,
    normalize_optional_string,
    safe_int,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.application.services.pipeline_run_trace_service import (
        PipelineRunTraceService,
    )
    from src.application.services.ports.run_progress_port import RunProgressPort
    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub


class SourceWorkflowMonitorService(
    SourceWorkflowMonitorEventsMixin,
    SourceWorkflowMonitorRelationsMixin,
    SourceWorkflowMonitorProgressMixin,
):
    """Aggregate workflow read models for one source inside one research space."""

    def __init__(
        self,
        session: Session,
        *,
        run_progress: RunProgressPort | None = None,
        pipeline_trace: PipelineRunTraceService | None = None,
    ) -> None:
        self._session = session
        self._run_progress = run_progress
        self._pipeline_trace = pipeline_trace

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> int:
        if not values:
            return 0
        ordered = sorted(value for value in values if value >= 0)
        if not ordered:
            return 0
        position = int(round((len(ordered) - 1) * percentile))
        bounded_position = min(max(position, 0), len(ordered) - 1)
        return ordered[bounded_position]

    @staticmethod
    def _resolve_source_type_value(raw_value: object) -> str | None:
        enum_value = getattr(raw_value, "value", None)
        if isinstance(enum_value, str) and enum_value.strip():
            return enum_value.strip()
        return normalize_optional_string(raw_value)

    def _enrich_run_diagnostic_signals(  # noqa: C901, PLR0913, PLR0915
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str,
        run_payload: JSONObject,
        extraction_rows: list[JSONObject],
        relation_review_payload: JSONObject,
    ) -> JSONObject:
        enriched_payload = dict(run_payload)
        diagnostic_signals = coerce_json_object(
            enriched_payload.get("diagnostic_signals"),
        )
        stage_counters = coerce_json_object(enriched_payload.get("stage_counters"))
        persisted_relations = max(
            safe_int(stage_counters.get("persisted_relations")),
            safe_int(stage_counters.get("graph_stage_persisted_relations")),
            safe_int(stage_counters.get("extraction_persisted_relations")),
        )
        undefined_relations = 0
        metadata_dictionary_churn_count = 0
        metadata_concept_churn_count = 0
        for extraction_row in extraction_rows:
            extraction_metadata = coerce_json_object(extraction_row.get("metadata"))
            undefined_relations += safe_int(
                extraction_metadata.get("extraction_stage_undefined_relations"),
            )
            metadata_dictionary_churn_count += safe_int(
                extraction_metadata.get("dictionary_variables_created"),
            )
            metadata_dictionary_churn_count += safe_int(
                extraction_metadata.get("dictionary_synonyms_created"),
            )
            metadata_dictionary_churn_count += safe_int(
                extraction_metadata.get("dictionary_entity_types_created"),
            )
            metadata_concept_churn_count += safe_int(
                extraction_metadata.get("extraction_stage_concept_members_created"),
            )
            metadata_concept_churn_count += safe_int(
                extraction_metadata.get("extraction_stage_concept_aliases_created"),
            )
            metadata_concept_churn_count += safe_int(
                extraction_metadata.get("extraction_stage_concept_decisions_proposed"),
            )

        try:
            events_payload = self.list_workflow_events(
                space_id=space_id,
                source_id=source_id,
                run_id=run_id,
                limit=2000,
                since=None,
            )
            events = [
                coerce_json_object(item)
                for item in coerce_json_list(events_payload.get("events"))
            ]
        except (AttributeError, SQLAlchemyError, TypeError, ValueError):
            events = []
        extraction_document_durations: list[int] = []
        warning_event_count = 0
        error_event_count = 0
        review_required_document_count = 0
        timeout_scope_ids: set[str] = set()
        event_dictionary_churn_count = 0
        event_concept_churn_count = 0
        for event in events:
            level = normalize_optional_string(event.get("level"))
            if level == "warning":
                warning_event_count += 1
            elif level == "error":
                error_event_count += 1

            status = normalize_optional_string(event.get("status"))
            stage = normalize_optional_string(event.get("stage"))
            scope_kind = normalize_optional_string(event.get("scope_kind"))
            event_type = normalize_optional_string(event.get("event_type"))
            event_payload = coerce_json_object(event.get("payload"))
            if (
                stage == "extraction"
                and scope_kind == "document"
                and event_type == "document_finished"
            ):
                duration_ms = safe_int(event.get("duration_ms"))
                if duration_ms > 0:
                    extraction_document_durations.append(duration_ms)
                if event_payload.get("review_required") is True:
                    review_required_document_count += 1
                event_dictionary_churn_count += safe_int(
                    event_payload.get("dictionary_variables_created"),
                )
                event_dictionary_churn_count += safe_int(
                    event_payload.get("dictionary_synonyms_created"),
                )
                event_dictionary_churn_count += safe_int(
                    event_payload.get("dictionary_entity_types_created"),
                )
                event_concept_churn_count += safe_int(
                    event_payload.get("concept_members_created_count"),
                )
                event_concept_churn_count += safe_int(
                    event_payload.get("concept_aliases_created_count"),
                )
                event_concept_churn_count += safe_int(
                    event_payload.get("concept_decisions_proposed_count"),
                )

            timeout_budget_ms = safe_int(event.get("timeout_budget_ms"))
            error_code = normalize_optional_string(event.get("error_code"))
            message = normalize_optional_string(event.get("message"))
            if (
                "timeout" in (error_code or "").lower()
                or "timeout" in (message or "").lower()
                or (timeout_budget_ms > 0 and status == "failed")
            ):
                scope_id = normalize_optional_string(event.get("scope_id"))
                if scope_id is not None:
                    timeout_scope_ids.add(scope_id)

        pending_review_count = safe_int(
            relation_review_payload.get("pending_review_relation_count"),
        )
        dictionary_churn_count = max(
            metadata_dictionary_churn_count,
            event_dictionary_churn_count,
        )
        concept_churn_count = max(
            metadata_concept_churn_count,
            event_concept_churn_count,
        )
        diagnostic_signals.update(
            {
                "review_burden": pending_review_count,
                "review_burden_ratio": (
                    round(pending_review_count / persisted_relations, 6)
                    if persisted_relations > 0
                    else 0.0
                ),
                "review_required_document_count": review_required_document_count,
                "undefined_relation_rate": (
                    round(
                        undefined_relations
                        / max(undefined_relations + persisted_relations, 1),
                        6,
                    )
                    if undefined_relations > 0 or persisted_relations > 0
                    else 0.0
                ),
                "dictionary_churn_count": dictionary_churn_count,
                "concept_churn_count": concept_churn_count,
                "warning_event_count": warning_event_count,
                "error_event_count": error_event_count,
                "timeout_hotspot_count": len(timeout_scope_ids),
                "timeout_scope_ids": sorted(timeout_scope_ids),
                "p50_document_extraction_duration_ms": self._percentile(
                    extraction_document_durations,
                    0.5,
                ),
                "p95_document_extraction_duration_ms": self._percentile(
                    extraction_document_durations,
                    0.95,
                ),
                "document_extraction_duration_samples": len(
                    extraction_document_durations,
                ),
            },
        )
        enriched_payload["diagnostic_signals"] = diagnostic_signals
        return enriched_payload

    def list_pipeline_runs(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        limit: int,
    ) -> list[JSONObject]:
        self._require_source(space_id=space_id, source_id=source_id)
        return [
            record.payload
            for record in self._load_pipeline_runs(source_id=source_id, limit=limit)
        ]

    def get_source_workflow_monitor(  # noqa: PLR0913, PLR0915 - explicit read model fields are intentional
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str | None,
        limit: int,
        include_graph: bool,
    ) -> JSONObject:
        source = self._require_source(space_id=space_id, source_id=source_id)
        run_records = self._load_pipeline_runs(
            source_id=source_id,
            limit=max(limit * 4, 50),
        )
        selected_run = self._resolve_run_record(
            source_id=source_id,
            requested_run_id=run_id,
            recent_limit=max(limit * 4, 50),
        )
        selected_run_id = selected_run.run_id if selected_run is not None else None
        selected_run_job_id = selected_run.job_id if selected_run is not None else None
        selected_run_payload = (
            coerce_json_object(selected_run.payload) if selected_run is not None else {}
        )
        selected_run_ingestion_job_id = normalize_optional_string(
            selected_run_payload.get("ingestion_job_id"),
        )
        source_type_value = self._resolve_source_type_value(source.source_type)
        run_scoped_ingestion_job_id = (
            selected_run_ingestion_job_id
            if selected_run_ingestion_job_id is not None
            else (None if selected_run_id is not None else selected_run_job_id)
        )

        documents = self._load_source_documents(
            source_id=source_id,
            run_id=selected_run_id,
            ingestion_job_id=run_scoped_ingestion_job_id,
            limit=limit,
        )
        paper_candidates = self._build_run_paper_candidates(
            source_type=source_type_value,
            selected_run_payload=selected_run_payload,
            documents=documents,
        )
        document_status_counts = self._count_statuses(
            records=documents,
            key="extraction_status",
        )
        document_ids = {
            str(item["id"]) for item in documents if isinstance(item.get("id"), str)
        }
        external_record_to_document_id = {
            str(item["external_record_id"]): str(item["id"])
            for item in documents
            if isinstance(item.get("external_record_id"), str)
            and isinstance(item.get("id"), str)
        }

        queue_rows = self._load_extraction_queue(
            source_id=source_id,
            run_id=selected_run_id,
            ingestion_job_id=run_scoped_ingestion_job_id,
            external_record_ids=set(external_record_to_document_id.keys()),
            limit=limit,
        )
        queue_status_counts = self._count_statuses(records=queue_rows, key="status")
        queue_id_to_document_id = {
            str(item["id"]): external_record_to_document_id[
                str(item["source_record_id"])
            ]
            for item in queue_rows
            if isinstance(item.get("id"), str)
            and isinstance(item.get("source_record_id"), str)
            and str(item["source_record_id"]) in external_record_to_document_id
        }

        extraction_rows = self._load_publication_extractions(
            source_id=source_id,
            run_id=selected_run_id,
            ingestion_job_id=run_scoped_ingestion_job_id,
            queue_item_ids=set(queue_id_to_document_id.keys()),
            limit=limit,
        )
        extraction_status_counts = self._count_statuses(
            records=extraction_rows,
            key="status",
        )

        relation_review_payload = self._build_relation_review_payload(
            space_id=space_id,
            document_ids=document_ids,
            document_context_by_id={
                str(item["id"]): {
                    "external_record_id": item.get("external_record_id"),
                    "source_type": item.get("source_type"),
                    "metadata": item.get("metadata"),
                }
                for item in documents
                if isinstance(item.get("id"), str)
            },
            queue_id_to_document_id=queue_id_to_document_id,
            extraction_rows=extraction_rows,
            limit=limit,
        )
        relation_rows = [
            coerce_json_object(item)
            for item in coerce_json_list(
                relation_review_payload.get("persisted_relation_rows"),
            )
        ]
        relation_edge_delta = len(
            {
                str(coerce_json_object(item).get("relation_id"))
                for item in relation_rows
                if normalize_optional_string(
                    coerce_json_object(item).get("relation_id"),
                )
                is not None
            },
        )

        graph_summary = (
            self._build_graph_summary(space_id=space_id, source_id=source_id)
            if include_graph
            else None
        )
        warnings = self._build_warnings(extraction_rows=extraction_rows)
        operational_counters = self._build_operational_counters(
            space_id=space_id,
            source_id=source_id,
            selected_run=selected_run,
            graph_summary=graph_summary,
            relation_edge_delta=relation_edge_delta,
            selected_run_id=selected_run_id,
            selected_ingestion_job_id=run_scoped_ingestion_job_id,
        )
        artana_progress = self._build_artana_progress(
            tenant_id=str(space_id),
            selected_run_id=selected_run_id,
            selected_run_payload=(
                selected_run.payload if selected_run is not None else None
            ),
            documents=documents,
            extraction_rows=extraction_rows,
            relation_rows=relation_rows,
        )
        if selected_run is not None:
            selected_run_payload = self._enrich_run_diagnostic_signals(
                space_id=space_id,
                source_id=source_id,
                run_id=selected_run.run_id,
                run_payload=selected_run_payload,
                extraction_rows=extraction_rows,
                relation_review_payload=relation_review_payload,
            )

        return {
            "source_snapshot": self._build_source_snapshot(source),
            "last_run": selected_run_payload if selected_run is not None else None,
            "pipeline_runs": [record.payload for record in run_records[:limit]],
            "documents": documents,
            "paper_candidates": paper_candidates,
            "document_status_counts": document_status_counts,
            "extraction_queue": queue_rows,
            "extraction_queue_status_counts": queue_status_counts,
            "publication_extractions": extraction_rows,
            "publication_extraction_status_counts": extraction_status_counts,
            "relation_review": relation_review_payload,
            "graph_summary": graph_summary,
            "operational_counters": operational_counters,
            "artana_progress": artana_progress,
            "warnings": warnings,
        }

    def get_pipeline_run_summary(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str,
    ) -> JSONObject:
        self._require_source(space_id=space_id, source_id=source_id)
        run_record = self._resolve_run_record(
            source_id=source_id,
            requested_run_id=run_id,
            recent_limit=200,
        )
        if run_record is None:
            msg = "Pipeline run not found for this source"
            raise LookupError(msg)
        run_payload = coerce_json_object(run_record.payload)
        run_ingestion_job_id = normalize_optional_string(
            run_payload.get("ingestion_job_id"),
        )
        documents = self._load_source_documents(
            source_id=source_id,
            run_id=run_record.run_id,
            ingestion_job_id=run_ingestion_job_id,
            limit=None,
        )
        external_record_to_document_id = {
            str(item["external_record_id"]): str(item["id"])
            for item in documents
            if isinstance(item.get("external_record_id"), str)
            and isinstance(item.get("id"), str)
        }
        queue_rows = self._load_extraction_queue(
            source_id=source_id,
            run_id=run_record.run_id,
            ingestion_job_id=run_ingestion_job_id,
            external_record_ids=set(external_record_to_document_id.keys()),
            limit=None,
        )
        queue_id_to_document_id = {
            str(item["id"]): external_record_to_document_id[
                str(item["source_record_id"])
            ]
            for item in queue_rows
            if isinstance(item.get("id"), str)
            and isinstance(item.get("source_record_id"), str)
            and str(item["source_record_id"]) in external_record_to_document_id
        }
        extraction_rows = self._load_publication_extractions(
            source_id=source_id,
            run_id=run_record.run_id,
            ingestion_job_id=run_ingestion_job_id,
            queue_item_ids=set(queue_id_to_document_id.keys()),
            limit=None,
        )
        relation_review_payload = self._build_relation_review_payload(
            space_id=space_id,
            document_ids={
                str(item["id"]) for item in documents if isinstance(item.get("id"), str)
            },
            document_context_by_id={
                str(item["id"]): {
                    "external_record_id": item.get("external_record_id"),
                    "source_type": item.get("source_type"),
                    "metadata": item.get("metadata"),
                }
                for item in documents
                if isinstance(item.get("id"), str)
            },
            queue_id_to_document_id=queue_id_to_document_id,
            extraction_rows=extraction_rows,
            limit=None,
        )
        run_payload = self._enrich_run_diagnostic_signals(
            space_id=space_id,
            source_id=source_id,
            run_id=run_record.run_id,
            run_payload=run_payload,
            extraction_rows=extraction_rows,
            relation_review_payload=relation_review_payload,
        )
        return {
            "source_id": str(source_id),
            "run_id": run_record.run_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "run": run_payload,
        }

    def get_document_trace(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str,
        document_id: UUID,
    ) -> JSONObject:
        self._require_source(space_id=space_id, source_id=source_id)
        run_record = self._resolve_run_record(
            source_id=source_id,
            requested_run_id=run_id,
            recent_limit=200,
        )
        if run_record is None:
            msg = "Pipeline run not found for this source"
            raise LookupError(msg)
        run_payload = coerce_json_object(run_record.payload)
        run_ingestion_job_id = normalize_optional_string(
            run_payload.get("ingestion_job_id"),
        )
        documents = self._load_source_documents(
            source_id=source_id,
            run_id=run_record.run_id,
            ingestion_job_id=run_ingestion_job_id,
            limit=500,
        )
        document_payload = next(
            (
                row
                for row in documents
                if normalize_optional_string(row.get("id")) == str(document_id)
            ),
            None,
        )
        if document_payload is None:
            msg = "Document not found for this pipeline run"
            raise LookupError(msg)

        external_record_id = normalize_optional_string(
            document_payload.get("external_record_id"),
        )
        queue_rows = self._load_extraction_queue(
            source_id=source_id,
            run_id=run_record.run_id,
            ingestion_job_id=run_ingestion_job_id,
            external_record_ids=(
                {external_record_id} if external_record_id is not None else set()
            ),
            limit=50,
        )
        queue_ids = {
            str(item["id"]) for item in queue_rows if isinstance(item.get("id"), str)
        }
        extraction_rows = self._load_publication_extractions(
            source_id=source_id,
            run_id=run_record.run_id,
            ingestion_job_id=run_ingestion_job_id,
            queue_item_ids=queue_ids,
            limit=50,
        )
        scope_ids = [str(document_id)]
        if external_record_id is not None and external_record_id not in scope_ids:
            scope_ids.append(external_record_id)
        merged_events: list[JSONObject] = []
        seen_event_ids: set[str] = set()
        for scope_id in scope_ids:
            events_payload = self.list_workflow_events(
                space_id=space_id,
                source_id=source_id,
                run_id=run_record.run_id,
                limit=500,
                since=None,
                scope_kind="document",
                scope_id=scope_id,
            )
            for raw_event in coerce_json_list(events_payload.get("events")):
                event = coerce_json_object(raw_event)
                event_id = normalize_optional_string(event.get("event_id"))
                if event_id is not None:
                    if event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(event_id)
                merged_events.append(event)

        merged_events.sort(
            key=lambda event: (
                normalize_optional_string(event.get("occurred_at")) or "",
                normalize_optional_string(event.get("event_id")) or "",
            ),
            reverse=True,
        )
        return {
            "source_id": str(source_id),
            "run_id": run_record.run_id,
            "document_id": str(document_id),
            "generated_at": datetime.now(UTC).isoformat(),
            "document": document_payload,
            "extraction_rows": extraction_rows,
            "events": merged_events,
        }

    def get_query_generation_trace(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str,
    ) -> JSONObject:
        source = self._require_source(space_id=space_id, source_id=source_id)
        run_record = self._resolve_run_record(
            source_id=source_id,
            requested_run_id=run_id,
            recent_limit=200,
        )
        if run_record is None:
            msg = "Pipeline run not found for this source"
            raise LookupError(msg)
        run_payload = coerce_json_object(run_record.payload)
        events_payload = self.list_workflow_events(
            space_id=space_id,
            source_id=source_id,
            run_id=run_record.run_id,
            limit=200,
            since=None,
            scope_kind="query",
        )
        return {
            "source_id": str(source_id),
            "run_id": run_record.run_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "base_query": self._build_source_snapshot(source).get("query"),
            "executed_query": run_payload.get("executed_query"),
            "query_generation": coerce_json_object(run_payload.get("query_generation")),
            "events": events_payload.get("events", []),
        }

    def get_run_timing_summary(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str,
    ) -> JSONObject:
        summary = self.get_pipeline_run_summary(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
        )
        run_payload = coerce_json_object(summary.get("run"))
        return {
            "source_id": str(source_id),
            "run_id": run_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "timing_summary": coerce_json_object(run_payload.get("timing_summary")),
        }

    def get_run_cost_summary(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str,
    ) -> JSONObject:
        summary = self.get_pipeline_run_summary(
            space_id=space_id,
            source_id=source_id,
            run_id=run_id,
        )
        run_payload = coerce_json_object(summary.get("run"))
        return {
            "source_id": str(source_id),
            "run_id": run_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "cost_summary": coerce_json_object(run_payload.get("cost_summary")),
        }

    def list_run_costs(  # noqa: PLR0913
        self,
        *,
        space_id: UUID,
        source_id: UUID | None,
        source_type: str | None,
        user_id: str | None,
        date_from: str | None,
        date_to: str | None,
        limit: int,
    ) -> JSONObject:
        normalized_source_type = normalize_optional_string(source_type)
        normalized_user_id = normalize_optional_string(user_id)
        date_from_ts = _parse_iso_datetime(date_from)
        date_to_ts = _parse_iso_datetime(date_to)

        statement = (
            select(IngestionJobModel)
            .join(
                UserDataSourceModel,
                UserDataSourceModel.id == IngestionJobModel.source_id,
            )
            .where(UserDataSourceModel.research_space_id == str(space_id))
            .where(
                IngestionJobModel.job_kind
                == IngestionJobKindEnum.PIPELINE_ORCHESTRATION,
            )
            .order_by(desc(IngestionJobModel.triggered_at))
        )
        if source_id is not None:
            statement = statement.where(IngestionJobModel.source_id == str(source_id))
        if normalized_source_type is not None:
            statement = statement.where(
                UserDataSourceModel.source_type == normalized_source_type,
            )

        rows = self._session.execute(statement).scalars().all()
        items: list[JSONObject] = []
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
            started_at = _parse_iso_datetime(
                normalize_optional_string(payload.get("started_at")),
            )
            completed_at = _parse_iso_datetime(
                normalize_optional_string(payload.get("completed_at")),
            )
            if (
                date_from_ts is not None
                and started_at is not None
                and started_at < date_from_ts
            ):
                continue
            if (
                date_to_ts is not None
                and completed_at is not None
                and completed_at > date_to_ts
            ):
                continue
            resolved_user_id = normalize_optional_string(
                payload.get("run_owner_user_id"),
            )
            if (
                normalized_user_id is not None
                and resolved_user_id != normalized_user_id
            ):
                continue

            cost_summary = coerce_json_object(payload.get("cost_summary"))
            timing_summary = coerce_json_object(payload.get("timing_summary"))
            stage_counters = coerce_json_object(payload.get("stage_counters"))
            items.append(
                {
                    "run_id": run_id,
                    "source_id": str(row.source_id),
                    "research_space_id": str(space_id),
                    "source_name": getattr(row.source, "name", None),
                    "source_type": self._resolve_source_type_value(
                        getattr(row.source, "source_type", None),
                    ),
                    "status": payload.get("status"),
                    "run_owner_user_id": resolved_user_id,
                    "run_owner_source": payload.get("run_owner_source"),
                    "started_at": payload.get("started_at"),
                    "completed_at": payload.get("completed_at"),
                    "total_duration_ms": timing_summary.get("total_duration_ms"),
                    "total_cost_usd": cost_summary.get("total_cost_usd", 0.0),
                    "extracted_documents": stage_counters.get(
                        "extraction_completed",
                        0,
                    ),
                    "persisted_relations": stage_counters.get("persisted_relations", 0),
                },
            )
            if len(items) >= max(limit, 1):
                break

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "items": items,
            "total": len(items),
        }

    def compare_source_runs(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_a_id: str,
        run_b_id: str,
    ) -> JSONObject:
        self._require_source(space_id=space_id, source_id=source_id)
        run_a = self._resolve_run_record(
            source_id=source_id,
            requested_run_id=run_a_id,
            recent_limit=500,
        )
        run_b = self._resolve_run_record(
            source_id=source_id,
            requested_run_id=run_b_id,
            recent_limit=500,
        )
        if run_a is None or run_b is None:
            msg = "Both pipeline runs must exist for this source"
            raise ValueError(msg)

        run_a_payload = coerce_json_object(run_a.payload)
        run_b_payload = coerce_json_object(run_b.payload)
        run_a_timing = coerce_json_object(run_a_payload.get("timing_summary"))
        run_b_timing = coerce_json_object(run_b_payload.get("timing_summary"))
        run_a_cost = coerce_json_object(run_a_payload.get("cost_summary"))
        run_b_cost = coerce_json_object(run_b_payload.get("cost_summary"))
        run_a_counters = coerce_json_object(run_a_payload.get("stage_counters"))
        run_b_counters = coerce_json_object(run_b_payload.get("stage_counters"))

        delta: JSONObject = {
            "total_duration_ms": _delta_int(
                run_a_timing.get("total_duration_ms"),
                run_b_timing.get("total_duration_ms"),
            ),
            "total_cost_usd": _delta_float(
                run_a_cost.get("total_cost_usd"),
                run_b_cost.get("total_cost_usd"),
            ),
            "extraction_completed": _delta_int(
                run_a_counters.get("extraction_completed"),
                run_b_counters.get("extraction_completed"),
            ),
            "extraction_failed": _delta_int(
                run_a_counters.get("extraction_failed"),
                run_b_counters.get("extraction_failed"),
            ),
            "persisted_relations": _delta_int(
                run_a_counters.get("persisted_relations"),
                run_b_counters.get("persisted_relations"),
            ),
        }
        return {
            "source_id": str(source_id),
            "run_a_id": run_a_id,
            "run_b_id": run_b_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "run_a": run_a_payload,
            "run_b": run_b_payload,
            "delta": delta,
        }


def _parse_iso_datetime(raw_value: str | None) -> datetime | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    candidate = normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _delta_int(run_a_value: object, run_b_value: object) -> int:
    return safe_int(run_b_value) - safe_int(run_a_value)


def _delta_float(run_a_value: object, run_b_value: object) -> float:
    run_a_float = _safe_float(run_a_value)
    run_b_float = _safe_float(run_b_value)
    return run_b_float - run_a_float


def _safe_float(raw_value: object) -> float:
    if isinstance(raw_value, int | float):
        return float(raw_value)
    if isinstance(raw_value, str):
        try:
            return float(raw_value)
        except ValueError:
            return 0.0
    return 0.0


__all__ = ["SourceWorkflowMonitorService"]
