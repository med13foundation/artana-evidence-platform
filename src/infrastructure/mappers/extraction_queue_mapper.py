"""Mapper utilities for extraction queue items."""

from __future__ import annotations

from uuid import UUID

from src.domain.entities.extraction_queue_item import (
    ExtractionQueueItem,
    ExtractionStatus,
)
from src.models.database.extraction_queue import (
    ExtractionQueueItemModel,
    ExtractionStatusEnum,
)
from src.type_definitions.common import JSONObject  # noqa: TC001


class ExtractionQueueMapper:
    """Bidirectional mapper between queue domain entities and SQLAlchemy models."""

    @staticmethod
    def to_domain(model: ExtractionQueueItemModel) -> ExtractionQueueItem:
        status_value = (
            model.status.value if hasattr(model.status, "value") else str(model.status)
        )
        metadata_payload: JSONObject = dict(model.metadata_payload or {})
        return ExtractionQueueItem(
            id=UUID(model.id),
            publication_id=model.publication_id,
            pubmed_id=model.pubmed_id,
            source_type=model.source_type,
            source_record_id=model.source_record_id,
            raw_storage_key=model.raw_storage_key,
            payload_ref=model.payload_ref,
            source_id=UUID(model.source_id),
            ingestion_job_id=UUID(model.ingestion_job_id),
            status=ExtractionStatus(status_value),
            attempts=model.attempts,
            last_error=model.last_error,
            extraction_version=model.extraction_version,
            metadata=metadata_payload,
            queued_at=model.queued_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: ExtractionQueueItem) -> ExtractionQueueItemModel:
        source_record_id = entity.source_record_id.strip()
        if not source_record_id:
            if entity.publication_id is not None:
                source_record_id = f"publication:{entity.publication_id}"
            else:
                source_record_id = str(entity.id)
        source_type = entity.source_type.strip() or "pubmed"
        return ExtractionQueueItemModel(
            id=str(entity.id),
            publication_id=entity.publication_id,
            pubmed_id=entity.pubmed_id,
            source_type=source_type,
            source_record_id=source_record_id,
            raw_storage_key=entity.raw_storage_key,
            payload_ref=entity.payload_ref,
            source_id=str(entity.source_id),
            ingestion_job_id=str(entity.ingestion_job_id),
            status=ExtractionStatusEnum(entity.status.value),
            attempts=entity.attempts,
            last_error=entity.last_error,
            extraction_version=entity.extraction_version,
            metadata_payload=entity.metadata,
            queued_at=entity.queued_at,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def to_domain_sequence(
        models: list[ExtractionQueueItemModel],
    ) -> list[ExtractionQueueItem]:
        return [ExtractionQueueMapper.to_domain(model) for model in models]
