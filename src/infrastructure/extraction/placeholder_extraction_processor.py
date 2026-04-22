"""Placeholder extraction processor for queued PubMed publications."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.services.ports.extraction_processor_port import (
    ExtractionProcessorPort,
    ExtractionProcessorResult,
    ExtractionTextPayload,
)
from src.type_definitions.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from src.domain.entities.extraction_queue_item import ExtractionQueueItem
    from src.domain.entities.publication import Publication


class PlaceholderExtractionProcessor(ExtractionProcessorPort):
    """Marks extraction as skipped until real logic is implemented."""

    def extract_publication(
        self,
        *,
        queue_item: ExtractionQueueItem,
        publication: Publication | None,
        text_payload: ExtractionTextPayload | None = None,
    ) -> ExtractionProcessorResult:
        if publication is None:
            return ExtractionProcessorResult(
                status="failed",
                facts=[],
                metadata={},
                processor_name="placeholder",
                text_source=(
                    text_payload.text_source if text_payload else "title_abstract"
                ),
                document_reference=(
                    text_payload.document_reference if text_payload else None
                ),
                error_message="publication_not_found",
            )

        metadata: JSONObject = {
            "processor": "placeholder",
            "reason": "extraction_not_implemented",
            "queue_item_id": str(queue_item.id),
            "publication_title": publication.title,
            "pubmed_id": publication.identifier.pubmed_id,
            "pmc_id": publication.identifier.pmc_id,
            "doi": publication.identifier.doi,
        }
        return ExtractionProcessorResult(
            status="skipped",
            facts=[],
            metadata=metadata,
            processor_name="placeholder",
            text_source=text_payload.text_source if text_payload else "title_abstract",
            document_reference=(
                text_payload.document_reference if text_payload else None
            ),
        )


__all__ = ["PlaceholderExtractionProcessor"]
