"""MARRVEL-specific extraction processor for queued MARRVEL records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.application.services.ports.extraction_processor_port import (
    ExtractionProcessorPort,
    ExtractionProcessorResult,
    ExtractionTextPayload,
)
from src.domain.services.marrvel_grounding import (
    attach_marrvel_grounding_context,
    build_marrvel_grounding_context,
    extract_marrvel_grounding_facts,
)

if TYPE_CHECKING:
    from src.domain.entities.extraction_queue_item import ExtractionQueueItem
    from src.domain.entities.publication import Publication
    from src.type_definitions.common import ExtractionTextSource, JSONObject


class MarrvelExtractionProcessor(ExtractionProcessorPort):
    """Tier 1 MARRVEL grounding processor that defers to AI for claim generation.

    Extracts deterministic grounding (gene, variant, phenotype, OMIM,
    ClinVar entries) and stores it in metadata, then returns
    ``status="skipped"`` with ``ai_required=True`` so the entity-recognition
    + extraction AI pipeline picks up the document for Tier 2 relation-claim
    generation.
    """

    def extract_publication(
        self,
        *,
        queue_item: ExtractionQueueItem,
        publication: Publication | None,
        text_payload: ExtractionTextPayload | None = None,
    ) -> ExtractionProcessorResult:
        text_source = _resolve_text_source(text_payload)
        document_reference = _resolve_document_reference(text_payload)
        publication_id = publication.id if publication is not None else None

        raw_record = _extract_raw_record(queue_item)
        if raw_record is None:
            failure_metadata: JSONObject = {
                "reason": "missing_raw_record",
                "queue_item_id": str(queue_item.id),
                "source_record_id": queue_item.source_record_id,
            }
            if publication_id is not None:
                failure_metadata["publication_id"] = publication_id
            return ExtractionProcessorResult(
                status="failed",
                facts=[],
                metadata=failure_metadata,
                processor_name="marrvel_contract_v1",
                text_source=text_source,
                document_reference=document_reference,
                error_message="missing_raw_record",
            )

        # Tier 1: deterministic grounding — stored in metadata for the AI
        # pipeline to read; not returned as processor facts.
        grounding_facts = extract_marrvel_grounding_facts(raw_record)
        grounding_context = build_marrvel_grounding_context(raw_record)
        gene_symbol_value = raw_record.get("gene_symbol")
        gene_symbol = (
            gene_symbol_value.strip()
            if isinstance(gene_symbol_value, str) and gene_symbol_value.strip()
            else None
        )

        metadata: JSONObject = {
            "queue_item_id": str(queue_item.id),
            "source_type": queue_item.source_type,
            "source_record_id": queue_item.source_record_id,
            "ai_required": True,
            "reason": "marrvel_tier1_grounding_complete_defer_to_ai_pipeline",
            "grounding_fact_count": len(grounding_facts),
            "marrvel_grounding": grounding_context,
        }
        if publication_id is not None:
            metadata["publication_id"] = publication_id
        if gene_symbol:
            metadata["gene_symbol"] = gene_symbol

        return ExtractionProcessorResult(
            status="skipped",
            facts=[],
            metadata=metadata,
            processor_name="marrvel_contract_v1",
            processor_version="1.0",
            text_source=text_source,
            document_reference=document_reference,
        )


def _extract_raw_record(queue_item: ExtractionQueueItem) -> JSONObject | None:
    raw_record_value = queue_item.metadata.get("raw_record")
    if isinstance(raw_record_value, dict):
        return raw_record_value
    return None


_ExtractionProcessorResultStatus = Literal["completed", "failed", "skipped"]


def _resolve_text_source(
    payload: ExtractionTextPayload | None,
) -> ExtractionTextSource:
    if payload is None:
        return "full_text"
    return payload.text_source


def _resolve_document_reference(payload: ExtractionTextPayload | None) -> str | None:
    if payload is None:
        return None
    return payload.document_reference


__all__ = [
    "MarrvelExtractionProcessor",
    "attach_marrvel_grounding_context",
    "build_marrvel_grounding_context",
    "extract_marrvel_grounding_facts",
]
