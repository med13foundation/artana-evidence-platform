from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from sqlalchemy import desc, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.infrastructure.repositories.graph_observability_repository import (
    count_open_relation_claims_for_source_documents,
    count_pending_relation_reviews_for_source_documents,
    load_source_document_relation_rows,
    load_space_graph_summary_metrics,
)
from src.models.database.extraction_queue import (
    ExtractionQueueItemModel,
    ExtractionStatusEnum,
)
from src.models.database.review import ReviewRecord
from src.models.database.source_document import SourceDocumentModel

from ._source_workflow_monitor_paper_links import resolve_paper_links
from ._source_workflow_monitor_quality_helpers import (
    SourceWorkflowMonitorQualityMixin,
)
from ._source_workflow_monitor_shared import (
    PENDING_DOCUMENT_STATUSES,
    PENDING_RELATION_STATUSES,
    PipelineRunRecord,
    coerce_json_list,
    coerce_json_object,
    normalize_optional_string,
    parse_uuid_runtime,
    safe_int,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub

_PENDING_QUEUE_STATUSES: tuple[ExtractionStatusEnum, ...] = (
    ExtractionStatusEnum.PENDING,
    ExtractionStatusEnum.PROCESSING,
)


class SourceWorkflowMonitorRelationsMixin(SourceWorkflowMonitorQualityMixin):
    """Relation and graph summarization helpers for workflow monitor."""

    _session: Session

    def _build_relation_review_payload(  # noqa: PLR0913 - explicit inputs improve readability
        self,
        *,
        space_id: UUID,
        document_ids: set[str],
        document_context_by_id: dict[str, JSONObject],
        queue_id_to_document_id: dict[str, str],
        extraction_rows: list[JSONObject],
        limit: int | None,
    ) -> JSONObject:
        persisted = self._load_document_relations(
            space_id=space_id,
            document_ids=document_ids,
            document_context_by_id=document_context_by_id,
            limit=limit,
        )
        pending_relation_ids = {
            str(item["relation_id"])
            for item in persisted
            if isinstance(item.get("relation_id"), str)
            and str(item.get("curation_status")) in PENDING_RELATION_STATUSES
        }
        pending_relations = [
            item
            for item in persisted
            if item.get("relation_id") in pending_relation_ids
        ]
        pending_claim_count = self._count_open_relation_claims_for_document_ids(
            document_ids=document_ids,
            space_id=space_id,
        )
        rejected_by_document, rejected_reason_counts = (
            self._extract_rejected_relation_details(
                extraction_rows=extraction_rows,
                queue_id_to_document_id=queue_id_to_document_id,
            )
        )
        review_queue = self._load_relation_review_queue(space_id=space_id, limit=limit)
        return {
            "persisted_relation_rows": persisted,
            "pending_review_relation_rows": pending_relations,
            "pending_review_relation_count": len(pending_relation_ids)
            + pending_claim_count,
            "review_queue_rows": review_queue,
            "rejected_relation_rows": rejected_by_document,
            "rejected_reason_counts": rejected_reason_counts,
        }

    def _load_document_relations(
        self,
        *,
        space_id: UUID,
        document_ids: set[str],
        document_context_by_id: dict[str, JSONObject],
        limit: int | None,
    ) -> list[JSONObject]:
        if not document_ids:
            return []
        document_uuid_to_id = {
            parsed_uuid: document_id
            for document_id in document_ids
            if (parsed_uuid := parse_uuid_runtime(document_id)) is not None
        }
        if not document_uuid_to_id:
            return []
        rows = load_source_document_relation_rows(
            self._session,
            space_id=space_id,
            source_document_ids=list(document_uuid_to_id),
            limit=limit,
        )
        payload_rows: list[JSONObject] = []
        for row in rows:
            parsed_document_uuid = parse_uuid_runtime(row.source_document_id)
            document_id = (
                document_uuid_to_id.get(parsed_document_uuid, row.source_document_id)
                if parsed_document_uuid is not None
                else row.source_document_id
            )
            document_context = coerce_json_object(
                document_context_by_id.get(document_id),
            )
            external_record_id = normalize_optional_string(
                document_context.get("external_record_id"),
            )
            source_type = normalize_optional_string(document_context.get("source_type"))
            metadata = coerce_json_object(document_context.get("metadata"))
            paper_links = self._resolve_paper_links(
                source_type=source_type,
                external_record_id=external_record_id,
                metadata=metadata,
            )
            payload_rows.append(
                {
                    "document_id": document_id,
                    "external_record_id": external_record_id,
                    "relation_id": row.relation_id,
                    "relation_type": row.relation_type,
                    "curation_status": row.curation_status,
                    "aggregate_confidence": row.aggregate_confidence,
                    "source_entity_id": row.source_entity_id,
                    "target_entity_id": row.target_entity_id,
                    "evidence_id": row.evidence_id,
                    "evidence_confidence": row.evidence_confidence,
                    "evidence_summary": row.evidence_summary,
                    "evidence_sentence": row.evidence_sentence,
                    "evidence_sentence_source": row.evidence_sentence_source,
                    "evidence_sentence_confidence": row.evidence_sentence_confidence,
                    "evidence_sentence_rationale": row.evidence_sentence_rationale,
                    "agent_run_id": row.agent_run_id,
                    "source_entity_label": row.source_entity_label,
                    "target_entity_label": row.target_entity_label,
                    "paper_links": paper_links,
                },
            )
        return payload_rows

    def _resolve_paper_links(
        self,
        *,
        source_type: str | None,
        external_record_id: str | None,
        metadata: JSONObject,
    ) -> list[JSONObject]:
        return resolve_paper_links(
            source_type=source_type,
            external_record_id=external_record_id,
            metadata=metadata,
        )

    def _extract_rejected_relation_details(
        self,
        *,
        extraction_rows: list[JSONObject],
        queue_id_to_document_id: dict[str, str],
    ) -> tuple[list[JSONObject], dict[str, int]]:
        rows: list[JSONObject] = []
        reason_counter: Counter[str] = Counter()
        for extraction in extraction_rows:
            extraction_metadata = coerce_json_object(extraction.get("metadata"))
            rejected_details = coerce_json_list(
                extraction_metadata.get("extraction_stage_rejected_relation_details"),
            )
            queue_item_id = normalize_optional_string(extraction.get("queue_item_id"))
            document_id = (
                queue_id_to_document_id.get(queue_item_id)
                if queue_item_id is not None
                else None
            )
            for detail in rejected_details:
                detail_payload = coerce_json_object(detail)
                reason = (
                    normalize_optional_string(detail_payload.get("reason")) or "unknown"
                )
                reason_counter[reason] += 1
                rows.append(
                    {
                        "document_id": document_id,
                        "queue_item_id": queue_item_id,
                        "extraction_id": extraction.get("id"),
                        "reason": reason,
                        "status": normalize_optional_string(
                            detail_payload.get("status"),
                        ),
                        "payload": coerce_json_object(detail_payload.get("payload")),
                    },
                )
        return rows, dict(reason_counter)

    def _load_relation_review_queue(
        self,
        *,
        space_id: UUID,
        limit: int | None,
    ) -> list[JSONObject]:
        statement = (
            select(ReviewRecord)
            .where(ReviewRecord.research_space_id == str(space_id))
            .where(ReviewRecord.status == "pending")
            .order_by(desc(ReviewRecord.last_updated))
        )
        if limit is not None:
            statement = statement.limit(max(limit, 1) * 3)
        try:
            rows = self._session.execute(statement).scalars().all()
        except (OperationalError, ProgrammingError):
            self._session.rollback()
            return []

        payload: list[JSONObject] = []
        for row in rows:
            if "relation" not in row.entity_type.lower():
                continue
            payload.append(
                {
                    "id": int(row.id),
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "priority": row.priority,
                    "status": row.status,
                    "issues": int(row.issues),
                    "quality_score": row.quality_score,
                    "last_updated": row.last_updated.isoformat(),
                },
            )
        return payload

    def _build_graph_summary(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
    ) -> JSONObject:
        source_document_ids = self._load_source_document_uuid_ids(source_id=source_id)
        summary_metrics = load_space_graph_summary_metrics(
            self._session,
            space_id=space_id,
            source_document_ids=source_document_ids,
        )
        top_relation_types: list[JSONObject] = [
            {"relation_type": relation_type, "count": int(count)}
            for relation_type, count in summary_metrics.top_relation_types
        ]
        return {
            "node_count": summary_metrics.node_count,
            "edge_count": summary_metrics.edge_count,
            "source_edge_count": summary_metrics.source_edge_count,
            "top_relation_types": top_relation_types,
        }

    def _build_operational_counters(  # noqa: PLR0913 - explicit counters are intentional
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        selected_run: PipelineRunRecord | None,
        graph_summary: JSONObject | None,
        relation_edge_delta: int,
        selected_run_id: str | None,
        selected_ingestion_job_id: str | None,
    ) -> JSONObject:
        pending_documents = self._count_pending_documents(source_id=source_id)
        pending_queue = self._count_pending_queue_items(source_id=source_id)
        pending_relation_reviews = self._count_pending_relation_reviews(
            space_id=space_id,
            source_id=source_id,
        )
        (
            extraction_extracted_count,
            extraction_failed_count,
            extraction_skipped_count,
            extraction_timeout_failed_count,
        ) = self._count_document_extraction_outcomes(
            source_id=source_id,
            run_id=selected_run_id,
            ingestion_job_id=selected_ingestion_job_id,
        )
        graph_edges_total = (
            safe_int(graph_summary.get("edge_count"))
            if graph_summary is not None
            else 0
        )
        graph_edges_for_source = (
            safe_int(graph_summary.get("source_edge_count"))
            if graph_summary is not None
            else 0
        )
        stage_counters = (
            coerce_json_object(selected_run.payload.get("stage_counters"))
            if selected_run is not None
            else {}
        )
        selected_cost_summary = (
            coerce_json_object(selected_run.payload.get("cost_summary"))
            if selected_run is not None
            else {}
        )
        selected_timing_summary = (
            coerce_json_object(selected_run.payload.get("timing_summary"))
            if selected_run is not None
            else {}
        )
        return {
            "last_pipeline_status": (
                normalize_optional_string(selected_run.payload.get("status"))
                if selected_run is not None
                else None
            ),
            "pending_paper_count": pending_documents + pending_queue,
            "pending_document_count": pending_documents,
            "pending_queue_count": pending_queue,
            "pending_relation_review_count": pending_relation_reviews,
            "extraction_extracted_count": extraction_extracted_count,
            "extraction_failed_count": extraction_failed_count,
            "extraction_skipped_count": extraction_skipped_count,
            "extraction_timeout_failed_count": extraction_timeout_failed_count,
            "graph_edges_total": graph_edges_total,
            "graph_edges_for_source": graph_edges_for_source,
            "graph_edges_delta_last_run": max(relation_edge_delta, 0),
            "stage_counters": stage_counters,
            "last_run_total_cost_usd": selected_cost_summary.get("total_cost_usd"),
            "last_run_duration_ms": selected_timing_summary.get("total_duration_ms"),
        }

    def _count_pending_documents(self, *, source_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(SourceDocumentModel)
            .where(SourceDocumentModel.source_id == str(source_id))
            .where(
                SourceDocumentModel.extraction_status.in_(PENDING_DOCUMENT_STATUSES),
            )
        )
        return int(self._session.execute(statement).scalar_one() or 0)

    def _count_pending_queue_items(self, *, source_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(ExtractionQueueItemModel)
            .where(ExtractionQueueItemModel.source_id == str(source_id))
            .where(
                ExtractionQueueItemModel.status.in_(_PENDING_QUEUE_STATUSES),
            )
        )
        return int(self._session.execute(statement).scalar_one() or 0)

    def _count_pending_relation_reviews(
        self,
        *,
        space_id: UUID,
        source_id: UUID,
    ) -> int:
        source_document_ids = self._load_source_document_uuid_ids(source_id=source_id)
        pending_relations = count_pending_relation_reviews_for_source_documents(
            self._session,
            space_id=space_id,
            source_document_ids=source_document_ids,
            pending_relation_statuses=PENDING_RELATION_STATUSES,
        )
        pending_claims = self._count_open_relation_claims_for_source_document_ids(
            space_id=space_id,
            source_document_ids=source_document_ids,
        )
        return pending_relations + pending_claims

    def _count_open_relation_claims_for_document_ids(
        self,
        *,
        document_ids: set[str],
        space_id: UUID,
    ) -> int:
        source_document_ids = [
            parsed_uuid
            for document_id in document_ids
            if (parsed_uuid := parse_uuid_runtime(document_id)) is not None
        ]
        if not source_document_ids:
            return 0
        return self._count_open_relation_claims_for_source_document_ids(
            space_id=space_id,
            source_document_ids=source_document_ids,
        )

    def _count_open_relation_claims_for_source_document_ids(
        self,
        *,
        space_id: UUID,
        source_document_ids: list[UUID],
    ) -> int:
        return count_open_relation_claims_for_source_documents(
            self._session,
            space_id=space_id,
            source_document_ids=source_document_ids,
        )

    def _load_source_document_uuid_ids(self, *, source_id: UUID) -> list[UUID]:
        statement = select(SourceDocumentModel.id).where(
            SourceDocumentModel.source_id == str(source_id),
        )
        raw_ids = self._session.execute(statement).scalars().all()
        return [
            parsed_uuid
            for raw_id in raw_ids
            if (parsed_uuid := parse_uuid_runtime(raw_id)) is not None
        ]


__all__ = ["SourceWorkflowMonitorRelationsMixin"]
