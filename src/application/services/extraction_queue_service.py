"""Application service for managing publication extraction queue items."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.domain.entities.extraction_queue_item import (
    ExtractionQueueItem,
    ExtractionStatus,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.domain.repositories.extraction_queue_repository import (
        ExtractionQueueRepository,
    )
    from src.domain.services.ingestion import IngestionExtractionTarget
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


DEFAULT_EXTRACTION_VERSION = 1


@dataclass(frozen=True)
class ExtractionEnqueueSummary:
    source_id: UUID
    ingestion_job_id: UUID
    extraction_version: int
    requested: int
    queued: int
    skipped: int


class ExtractionQueueService:
    """Coordinates queueing of source records for extraction."""

    def __init__(
        self,
        queue_repository: ExtractionQueueRepository,
        *,
        extraction_version: int = DEFAULT_EXTRACTION_VERSION,
    ) -> None:
        self._queue_repository = queue_repository
        self._extraction_version = extraction_version

    def enqueue_for_ingestion(
        self,
        *,
        source_id: UUID,
        ingestion_job_id: UUID,
        targets: Sequence[IngestionExtractionTarget],
        extraction_version: int | None = None,
    ) -> ExtractionEnqueueSummary:
        unique_targets = self._deduplicate_targets(targets)
        if not unique_targets:
            return ExtractionEnqueueSummary(
                source_id=source_id,
                ingestion_job_id=ingestion_job_id,
                extraction_version=extraction_version or self._extraction_version,
                requested=0,
                queued=0,
                skipped=0,
            )

        version = extraction_version or self._extraction_version
        now = datetime.now(UTC)
        items = [
            self._build_queue_item(
                target=target,
                source_id=source_id,
                ingestion_job_id=ingestion_job_id,
                extraction_version=version,
                queued_at=now,
            )
            for target in unique_targets
        ]

        created = self._queue_repository.enqueue_many(items)
        queued = len(created)
        skipped = max(len(items) - queued, 0)
        if queued:
            logger.info(
                "Queued %s source records for extraction (source=%s, job=%s)",
                queued,
                source_id,
                ingestion_job_id,
            )
        return ExtractionEnqueueSummary(
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            extraction_version=version,
            requested=len(items),
            queued=queued,
            skipped=skipped,
        )

    @staticmethod
    def _deduplicate_targets(
        targets: Sequence[IngestionExtractionTarget],
    ) -> list[IngestionExtractionTarget]:
        deduped: dict[str, IngestionExtractionTarget] = {}
        for target in targets:
            source_record_id = target.source_record_id.strip()
            if not source_record_id:
                continue
            deduped[source_record_id] = target
        return list(deduped.values())

    @staticmethod
    def _build_queue_item(
        *,
        target: IngestionExtractionTarget,
        source_id: UUID,
        ingestion_job_id: UUID,
        extraction_version: int,
        queued_at: datetime,
    ) -> ExtractionQueueItem:
        metadata_payload: JSONObject = {}
        if target.metadata is not None:
            metadata_payload = dict(target.metadata)
        metadata_payload["source_record_id"] = target.source_record_id
        metadata_payload["source_type"] = target.source_type
        raw_storage_key = target.raw_storage_key
        if raw_storage_key is None:
            raw_storage_key_raw = metadata_payload.get("raw_storage_key")
            if isinstance(raw_storage_key_raw, str) and raw_storage_key_raw.strip():
                raw_storage_key = raw_storage_key_raw.strip()
        payload_ref = target.payload_ref
        if payload_ref is None:
            payload_ref_raw = metadata_payload.get("payload_ref")
            if isinstance(payload_ref_raw, str) and payload_ref_raw.strip():
                payload_ref = payload_ref_raw.strip()

        return ExtractionQueueItem(
            id=uuid4(),
            publication_id=target.publication_id,
            pubmed_id=target.pubmed_id,
            source_type=target.source_type,
            source_record_id=target.source_record_id,
            raw_storage_key=raw_storage_key,
            payload_ref=payload_ref,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            status=ExtractionStatus.PENDING,
            attempts=0,
            extraction_version=extraction_version,
            metadata=metadata_payload,
            queued_at=queued_at,
            updated_at=queued_at,
        )


__all__ = ["ExtractionEnqueueSummary", "ExtractionQueueService"]
