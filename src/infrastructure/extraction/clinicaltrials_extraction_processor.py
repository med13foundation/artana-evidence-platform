"""ClinicalTrials.gov extraction processor — Tier 1 defer to AI pipeline."""

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


class ClinicalTrialsExtractionProcessor(ExtractionProcessorPort):
    """Tier 1 ClinicalTrials.gov processor that defers to AI for claim generation.

    Pulls the structured trial fields out of the queued raw record (NCT ID,
    conditions, interventions, phase, lead sponsor) and stores them in
    metadata, then returns ``status="skipped"`` with ``ai_required=True`` so
    the entity-recognition + extraction AI pipeline picks up the document
    for Tier 2 relation-claim generation.

    Trial-specific Tier 2 relations the AI pipeline can produce:
      - ``CLINICAL_TRIAL → TARGETS → DISEASE``
      - ``CLINICAL_TRIAL → ASSOCIATED_WITH → DRUG``
      - ``DRUG → TREATS → DISEASE`` (when intervention is a drug)
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
                processor_name="clinical_trials_contract_v1",
                text_source=text_source,
                document_reference=document_reference,
                error_message="missing_raw_record",
            )

        nct_id = _first_scalar(raw_record, ("nct_id", "id"))
        grounding_context: JSONObject = {
            "nct_id": nct_id,
            "brief_title": _first_scalar(raw_record, ("brief_title", "title")),
            "official_title": _first_scalar(raw_record, ("official_title",)),
            "overall_status": _first_scalar(raw_record, ("overall_status", "status")),
            "study_type": _first_scalar(raw_record, ("study_type",)),
            "lead_sponsor": _first_scalar(raw_record, ("lead_sponsor",)),
            "conditions": raw_record.get("conditions") or [],
            "interventions": raw_record.get("interventions") or [],
            "phases": raw_record.get("phases") or [],
            "start_date": _first_scalar(raw_record, ("start_date",)),
            "completion_date": _first_scalar(raw_record, ("completion_date",)),
        }

        metadata: JSONObject = {
            "queue_item_id": str(queue_item.id),
            "source_type": queue_item.source_type,
            "source_record_id": queue_item.source_record_id,
            "ai_required": True,
            "reason": ("clinical_trials_tier1_grounding_complete_defer_to_ai_pipeline"),
            "clinical_trials_grounding": grounding_context,
        }
        if publication_id is not None:
            metadata["publication_id"] = publication_id
        if nct_id:
            metadata["nct_id"] = nct_id

        return ExtractionProcessorResult(
            status="skipped",
            facts=[],
            metadata=metadata,
            processor_name="clinical_trials_contract_v1",
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


__all__ = ["ClinicalTrialsExtractionProcessor"]
