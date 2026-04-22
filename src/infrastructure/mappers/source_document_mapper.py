"""Mapper utilities for source document entities."""

from __future__ import annotations

from uuid import UUID

from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
)
from src.domain.entities.user_data_source import SourceType
from src.models.database.source_document import SourceDocumentModel
from src.type_definitions.common import JSONObject  # noqa: TC001


class SourceDocumentMapper:
    """Bidirectional mapper between source document entities and persistence models."""

    @staticmethod
    def to_domain(model: SourceDocumentModel) -> SourceDocument:
        metadata_payload: JSONObject = dict(model.metadata_payload or {})
        return SourceDocument(
            id=UUID(model.id),
            research_space_id=(
                UUID(model.research_space_id) if model.research_space_id else None
            ),
            source_id=UUID(model.source_id),
            ingestion_job_id=(
                UUID(model.ingestion_job_id) if model.ingestion_job_id else None
            ),
            external_record_id=model.external_record_id,
            source_type=SourceType(model.source_type),
            document_format=DocumentFormat(model.document_format),
            raw_storage_key=model.raw_storage_key,
            enriched_storage_key=model.enriched_storage_key,
            content_hash=model.content_hash,
            content_length_chars=model.content_length_chars,
            enrichment_status=EnrichmentStatus(model.enrichment_status),
            enrichment_method=model.enrichment_method,
            enrichment_agent_run_id=model.enrichment_agent_run_id,
            extraction_status=DocumentExtractionStatus(model.extraction_status),
            extraction_agent_run_id=model.extraction_agent_run_id,
            metadata=metadata_payload,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: SourceDocument) -> SourceDocumentModel:
        return SourceDocumentModel(
            id=str(entity.id),
            research_space_id=(
                str(entity.research_space_id) if entity.research_space_id else None
            ),
            source_id=str(entity.source_id),
            ingestion_job_id=(
                str(entity.ingestion_job_id) if entity.ingestion_job_id else None
            ),
            external_record_id=entity.external_record_id,
            source_type=entity.source_type.value,
            document_format=entity.document_format.value,
            raw_storage_key=entity.raw_storage_key,
            enriched_storage_key=entity.enriched_storage_key,
            content_hash=entity.content_hash,
            content_length_chars=entity.content_length_chars,
            enrichment_status=entity.enrichment_status.value,
            enrichment_method=entity.enrichment_method,
            enrichment_agent_run_id=(
                str(entity.enrichment_agent_run_id)
                if entity.enrichment_agent_run_id
                else None
            ),
            extraction_status=entity.extraction_status.value,
            extraction_agent_run_id=(
                str(entity.extraction_agent_run_id)
                if entity.extraction_agent_run_id
                else None
            ),
            metadata_payload=dict(entity.metadata),
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
