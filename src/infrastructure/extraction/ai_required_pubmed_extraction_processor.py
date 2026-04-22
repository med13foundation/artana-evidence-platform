"""PubMed extraction processor that defers to AI orchestration stages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.services.ports.extraction_processor_port import (
    ExtractionProcessorPort,
    ExtractionProcessorResult,
    ExtractionTextPayload,
)

if TYPE_CHECKING:
    from src.domain.entities.extraction_queue_item import ExtractionQueueItem
    from src.domain.entities.publication import Publication
    from src.type_definitions.common import JSONObject


class AiRequiredPubMedExtractionProcessor(ExtractionProcessorPort):
    """Skip legacy queued PubMed extraction and require AI orchestration stages."""

    def extract_publication(
        self,
        *,
        queue_item: ExtractionQueueItem,
        publication: Publication | None,
        text_payload: ExtractionTextPayload | None = None,
    ) -> ExtractionProcessorResult:
        text_source = text_payload.text_source if text_payload else "full_text"
        document_reference = text_payload.document_reference if text_payload else None

        metadata: JSONObject = {
            "queue_item_id": str(queue_item.id),
            "source_type": queue_item.source_type,
            "source_record_id": queue_item.source_record_id,
            "reason": "legacy_pubmed_extraction_disabled_use_ai_pipeline",
            "ai_required": True,
            "has_text_payload": text_payload is not None,
        }
        if queue_item.pubmed_id:
            metadata["pubmed_id"] = queue_item.pubmed_id
        if publication is not None:
            metadata["publication_id"] = publication.id
            metadata["publication_title"] = publication.title
            metadata["pmc_id"] = publication.identifier.pmc_id
            metadata["doi"] = publication.identifier.doi

        return ExtractionProcessorResult(
            status="skipped",
            facts=[],
            metadata=metadata,
            processor_name="ai_required_pubmed_v1",
            processor_version="1.0",
            text_source=text_source,
            document_reference=document_reference,
        )


__all__ = ["AiRequiredPubMedExtractionProcessor"]
