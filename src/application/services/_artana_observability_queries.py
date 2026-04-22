"""Database-backed loaders for Artana observability views."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError

from src.application.services._artana_observability_models import (
    _DOCUMENT_METADATA_RUN_KEYS,
    _EXTRACTION_METADATA_RUN_KEYS,
    _SNAPSHOT_LIST_QUERY,
    _RunResolution,
    _RunSnapshotRow,
    _snapshot_from_row,
)
from src.application.services._artana_observability_pipeline_resolution import (
    load_pipeline_document_run_ids,
    load_pipeline_extraction_run_ids,
    load_pipeline_job_run_ids,
    load_relation_evidence_run_ids,
)
from src.application.services._artana_observability_support import (
    _document_matches_run,
    _metadata_contains_run,
    _parse_uuid,
    _serialize_datetime,
)
from src.application.services._source_workflow_monitor_shared import coerce_json_object
from src.infrastructure.repositories.graph_observability_repository import (
    load_linked_provenance_rows,
    load_linked_relation_evidence_rows,
)
from src.models.database.publication_extraction import PublicationExtractionModel
from src.models.database.source_document import SourceDocumentModel
from src.models.database.user_data_source import UserDataSourceModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject
else:
    Session = object
    JSONObject = dict[str, object]

logger = logging.getLogger(__name__)


def get_snapshot_row(session: Session, *, run_id: str) -> _RunSnapshotRow | None:
    rows = list_snapshot_rows(
        session,
        run_id=run_id,
        tenant_id=None,
        status=None,
        updated_since=None,
    )
    return rows[0] if rows else None


def list_snapshot_rows(
    session: Session,
    *,
    run_id: str | None,
    tenant_id: str | None,
    status: str | None,
    updated_since: datetime | None,
) -> list[_RunSnapshotRow]:
    try:
        rows = (
            session.execute(
                _SNAPSHOT_LIST_QUERY,
                {
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "status": status,
                    "updated_since": updated_since,
                },
            )
            .mappings()
            .all()
        )
    except SQLAlchemyError as exc:
        logger.debug(
            "Artana run_state_snapshots not available; returning no snapshots. %s",
            exc,
        )
        return []
    return [_snapshot_from_row(row) for row in rows]


def resolve_space_run(
    session: Session,
    *,
    research_space_id: str,
    requested_run_id: str,
) -> _RunResolution | None:
    direct_snapshot = next(
        iter(
            list_snapshot_rows(
                session,
                run_id=requested_run_id,
                tenant_id=research_space_id,
                status=None,
                updated_since=None,
            ),
        ),
        None,
    )
    if direct_snapshot is not None:
        return _RunResolution(
            resolved_run_id=requested_run_id,
            candidate_run_ids=[requested_run_id],
            snapshot=direct_snapshot,
        )

    candidate_run_ids = _resolve_candidate_run_ids_for_pipeline(
        session,
        research_space_id=research_space_id,
        pipeline_run_id=requested_run_id,
    )
    if not candidate_run_ids:
        return None

    snapshots_by_run_id = {
        snapshot.run_id: snapshot
        for snapshot in list_snapshot_rows(
            session,
            run_id=None,
            tenant_id=research_space_id,
            status=None,
            updated_since=None,
        )
        if snapshot.run_id in candidate_run_ids
    }

    def _candidate_updated_at(candidate: str) -> datetime:
        snapshot = snapshots_by_run_id.get(candidate)
        if snapshot is None or snapshot.updated_at is None:
            return datetime.min.replace(tzinfo=UTC)
        return snapshot.updated_at

    sorted_candidates = sorted(
        candidate_run_ids,
        key=_candidate_updated_at,
        reverse=True,
    )
    resolved_run_id = sorted_candidates[0]
    return _RunResolution(
        resolved_run_id=resolved_run_id,
        candidate_run_ids=sorted_candidates,
        snapshot=snapshots_by_run_id.get(resolved_run_id),
    )


def _resolve_candidate_run_ids_for_pipeline(
    session: Session,
    *,
    research_space_id: str,
    pipeline_run_id: str,
) -> list[str]:
    candidates: list[str] = []

    for value in load_pipeline_job_run_ids(
        session,
        research_space_id=research_space_id,
        pipeline_run_id=pipeline_run_id,
    ):
        if value not in candidates:
            candidates.append(value)

    document_run_ids, pipeline_document_ids = load_pipeline_document_run_ids(
        session,
        research_space_id=research_space_id,
        pipeline_run_id=pipeline_run_id,
    )
    for value in document_run_ids:
        if value not in candidates:
            candidates.append(value)

    for value in load_pipeline_extraction_run_ids(
        session,
        research_space_id=research_space_id,
        pipeline_run_id=pipeline_run_id,
    ):
        if value not in candidates:
            candidates.append(value)

    for value in load_relation_evidence_run_ids(
        session,
        pipeline_document_ids=pipeline_document_ids,
    ):
        if value not in candidates:
            candidates.append(value)

    return candidates


def load_linked_records(
    session: Session,
    *,
    run_id: str,
    research_space_id: str | None,
) -> list[JSONObject]:
    linked_records: list[JSONObject] = []
    linked_records.extend(
        _load_linked_source_documents(
            session,
            run_id=run_id,
            research_space_id=research_space_id,
        ),
    )
    linked_records.extend(
        _load_linked_publication_extractions(
            session,
            run_id=run_id,
            research_space_id=research_space_id,
        ),
    )
    linked_records.extend(
        _load_linked_relation_evidence(
            session,
            run_id=run_id,
            research_space_id=research_space_id,
        ),
    )
    linked_records.extend(
        _load_linked_provenance(
            session,
            run_id=run_id,
            research_space_id=research_space_id,
        ),
    )
    return linked_records


def _load_linked_source_documents(
    session: Session,
    *,
    run_id: str,
    research_space_id: str | None,
) -> list[JSONObject]:
    statement: Select[tuple[SourceDocumentModel]] = select(SourceDocumentModel)
    if research_space_id is not None:
        statement = statement.where(
            SourceDocumentModel.research_space_id == research_space_id,
        )
    rows = session.execute(statement).scalars().all()
    records: list[JSONObject] = []
    for row in rows:
        metadata = coerce_json_object(row.metadata_payload)
        if not _document_matches_run(
            row=row,
            metadata=metadata,
            run_id=run_id,
            candidate_keys=_DOCUMENT_METADATA_RUN_KEYS,
        ):
            continue
        records.append(
            {
                "record_type": "source_document",
                "record_id": str(row.id),
                "research_space_id": (
                    str(row.research_space_id) if row.research_space_id else None
                ),
                "source_id": str(row.source_id),
                "document_id": str(row.id),
                "source_type": row.source_type,
                "status": row.extraction_status,
                "label": row.external_record_id,
                "created_at": _serialize_datetime(row.created_at),
                "updated_at": _serialize_datetime(row.updated_at),
                "metadata": {
                    "external_record_id": row.external_record_id,
                    "document_format": row.document_format,
                    "enrichment_status": row.enrichment_status,
                    "enrichment_agent_run_id": row.enrichment_agent_run_id,
                    "extraction_agent_run_id": row.extraction_agent_run_id,
                    "pipeline_run_id": metadata.get("pipeline_run_id"),
                },
            },
        )
    return records


def _load_linked_publication_extractions(
    session: Session,
    *,
    run_id: str,
    research_space_id: str | None,
) -> list[JSONObject]:
    statement = select(PublicationExtractionModel, UserDataSourceModel).join(
        UserDataSourceModel,
        UserDataSourceModel.id == PublicationExtractionModel.source_id,
    )
    if research_space_id is not None:
        statement = statement.where(
            UserDataSourceModel.research_space_id == research_space_id,
        )
    rows = session.execute(statement).all()
    records: list[JSONObject] = []
    for extraction, source in rows:
        metadata = coerce_json_object(extraction.metadata_payload)
        if not _metadata_contains_run(
            metadata=metadata,
            run_id=run_id,
            candidate_keys=_EXTRACTION_METADATA_RUN_KEYS,
        ):
            continue
        records.append(
            {
                "record_type": "publication_extraction",
                "record_id": str(extraction.id),
                "research_space_id": (
                    str(source.research_space_id)
                    if source.research_space_id is not None
                    else None
                ),
                "source_id": str(extraction.source_id),
                "document_id": None,
                "source_type": source.source_type.value,
                "status": extraction.status.value,
                "label": str(extraction.pubmed_id or extraction.id),
                "created_at": _serialize_datetime(extraction.created_at),
                "updated_at": _serialize_datetime(extraction.updated_at),
                "metadata": {
                    "queue_item_id": str(extraction.queue_item_id),
                    "processor_name": extraction.processor_name,
                    "processor_version": extraction.processor_version,
                    "text_source": extraction.text_source,
                    "pipeline_run_id": metadata.get("pipeline_run_id"),
                },
            },
        )
    return records


def _load_linked_relation_evidence(
    session: Session,
    *,
    run_id: str,
    research_space_id: str | None,
) -> list[JSONObject]:
    parsed_space_id = _parse_uuid(research_space_id)
    return [
        {
            "record_type": "relation_evidence",
            "record_id": row.evidence_id,
            "research_space_id": row.research_space_id,
            "source_id": None,
            "document_id": row.source_document_id,
            "source_type": None,
            "status": row.curation_status,
            "label": row.relation_type,
            "created_at": _serialize_datetime(row.created_at),
            "updated_at": _serialize_datetime(row.relation_updated_at),
            "metadata": {
                "relation_id": row.relation_id,
                "relation_type": row.relation_type,
                "source_entity_id": row.source_entity_id,
                "target_entity_id": row.target_entity_id,
                "evidence_tier": row.evidence_tier,
            },
        }
        for row in load_linked_relation_evidence_rows(
            session,
            run_id=run_id,
            research_space_id=parsed_space_id,
        )
    ]


def _load_linked_provenance(
    session: Session,
    *,
    run_id: str,
    research_space_id: str | None,
) -> list[JSONObject]:
    parsed_space_id = _parse_uuid(research_space_id)
    return [
        {
            "record_type": "provenance",
            "record_id": row.provenance_id,
            "research_space_id": row.research_space_id,
            "source_id": None,
            "document_id": None,
            "source_type": row.source_type,
            "status": row.mapping_method,
            "label": row.source_ref,
            "created_at": _serialize_datetime(row.created_at),
            "updated_at": _serialize_datetime(row.created_at),
            "metadata": {
                "mapping_confidence": row.mapping_confidence,
                "agent_model": row.agent_model,
                "source_ref": row.source_ref,
            },
        }
        for row in load_linked_provenance_rows(
            session,
            run_id=run_id,
            research_space_id=parsed_space_id,
        )
    ]


__all__ = [
    "get_snapshot_row",
    "list_snapshot_rows",
    "load_linked_records",
    "resolve_space_run",
]
