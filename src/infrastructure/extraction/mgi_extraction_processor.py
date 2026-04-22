"""MGI extraction processor — Tier 1 defer to AI pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.application.services.ports.extraction_processor_port import (
    ExtractionProcessorPort,
    ExtractionProcessorResult,
    ExtractionTextPayload,
)

if TYPE_CHECKING:
    from src.domain.entities.extraction_queue_item import ExtractionQueueItem
    from src.domain.entities.publication import Publication
    from src.type_definitions.common import (
        ExtractionTextSource,
        JSONObject,
    )


class MGIExtractionProcessor(ExtractionProcessorPort):
    """Tier 1 MGI processor that defers to AI for claim generation.

    Pulls structured fields out of the queued raw record (gene symbol, MGI
    ID, mouse phenotype statements, disease associations) and stores them
    in metadata, then returns ``status="skipped"`` with ``ai_required=True``
    so the AI extraction pipeline picks up the document for Tier 2
    relation-claim generation.

    MGI Tier 2 relations the AI pipeline can produce:
      - ``GENE → ASSOCIATED_WITH → PHENOTYPE`` (mouse model phenotypes)
      - ``GENE → CAUSES → DISEASE`` (disease associations from mouse models)
      - ``GENE → PARTICIPATES_IN → BIOLOGICAL_PROCESS``
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
                processor_name="mgi_contract_v1",
                text_source=text_source,
                document_reference=document_reference,
                error_message="missing_raw_record",
            )

        mgi_id = _first_scalar(raw_record, ("mgi_id", "id"))
        gene_symbol = _first_scalar(raw_record, ("gene_symbol", "symbol"))
        grounding_context: JSONObject = {
            "mgi_id": mgi_id,
            "gene_symbol": gene_symbol,
            "gene_name": _first_scalar(raw_record, ("gene_name", "name")),
            "species": _first_scalar(raw_record, ("species",)),
            "synonyms": raw_record.get("synonyms") or [],
            "phenotype_statements": raw_record.get("phenotype_statements") or [],
            "disease_associations": raw_record.get("disease_associations") or [],
        }

        metadata: JSONObject = {
            "queue_item_id": str(queue_item.id),
            "source_type": queue_item.source_type,
            "source_record_id": queue_item.source_record_id,
            "ai_required": True,
            "reason": "mgi_tier1_grounding_complete_defer_to_ai_pipeline",
            "mgi_grounding": grounding_context,
        }
        if publication_id is not None:
            metadata["publication_id"] = publication_id
        if mgi_id:
            metadata["mgi_id"] = mgi_id
        if gene_symbol:
            metadata["gene_symbol"] = gene_symbol

        return ExtractionProcessorResult(
            status="skipped",
            facts=[],
            metadata=metadata,
            processor_name="mgi_contract_v1",
            processor_version="1.0",
            text_source=text_source,
            document_reference=document_reference,
        )


def _extract_raw_record(queue_item: ExtractionQueueItem) -> JSONObject | None:
    raw_record_value = queue_item.metadata.get("raw_record")
    if isinstance(raw_record_value, dict):
        return raw_record_value
    return None


ExtractionProcessorResultStatus = Literal["completed", "failed", "skipped"]


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


def _first_scalar(payload: JSONObject, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        if isinstance(value, int):
            return str(value)
    return None


__all__ = ["MGIExtractionProcessor"]
