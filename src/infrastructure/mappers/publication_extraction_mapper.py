"""Mapper utilities for publication extraction outputs."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard
from uuid import UUID

from src.domain.entities.publication_extraction import (
    ExtractionOutcome,
    ExtractionTextSource,
    PublicationExtraction,
)
from src.models.database.publication_extraction import (
    ExtractionOutcomeEnum,
    PublicationExtractionModel,
)

if TYPE_CHECKING:
    from src.type_definitions.common import (
        ExtractionFact,
        ExtractionFactType,
        JSONObject,
    )


_FACT_TYPES = {
    "variant",
    "phenotype",
    "gene",
    "drug",
    "mechanism",
    "pathway",
    "other",
}


def _is_extraction_fact_type(value: str) -> TypeGuard[ExtractionFactType]:
    return value in _FACT_TYPES


def _coerce_fact(payload: JSONObject) -> ExtractionFact:
    raw_fact_type = payload.get("fact_type", "other")
    fact_type_value = raw_fact_type if isinstance(raw_fact_type, str) else "other"
    if _is_extraction_fact_type(fact_type_value):
        fact_type: ExtractionFactType = fact_type_value
    else:
        fact_type = "other"
    fact: ExtractionFact = {"fact_type": fact_type}

    value = payload.get("value")
    if value is not None:
        fact["value"] = str(value)

    normalized_id = payload.get("normalized_id")
    if normalized_id is not None:
        fact["normalized_id"] = str(normalized_id)

    source = payload.get("source")
    if source is not None:
        fact["source"] = str(source)

    attributes = payload.get("attributes")
    if isinstance(attributes, dict):
        fact["attributes"] = dict(attributes)

    return fact


class PublicationExtractionMapper:
    """Bidirectional mapper between extraction outputs and SQLAlchemy models."""

    @staticmethod
    def to_domain(model: PublicationExtractionModel) -> PublicationExtraction:
        status_value = (
            model.status.value if hasattr(model.status, "value") else str(model.status)
        )
        metadata_payload: JSONObject = dict(model.metadata_payload or {})
        facts_payload = [dict(payload) for payload in (model.facts or [])]
        facts = [_coerce_fact(payload) for payload in facts_payload]
        return PublicationExtraction(
            id=UUID(model.id),
            publication_id=model.publication_id,
            pubmed_id=model.pubmed_id,
            source_id=UUID(model.source_id),
            ingestion_job_id=UUID(model.ingestion_job_id),
            queue_item_id=UUID(model.queue_item_id),
            status=ExtractionOutcome(status_value),
            extraction_version=model.extraction_version,
            processor_name=model.processor_name,
            processor_version=model.processor_version,
            text_source=ExtractionTextSource(model.text_source),
            document_reference=model.document_reference,
            facts=facts,
            metadata=metadata_payload,
            extracted_at=model.extracted_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: PublicationExtraction) -> PublicationExtractionModel:
        return PublicationExtractionModel(
            id=str(entity.id),
            publication_id=entity.publication_id,
            pubmed_id=entity.pubmed_id,
            source_id=str(entity.source_id),
            ingestion_job_id=str(entity.ingestion_job_id),
            queue_item_id=str(entity.queue_item_id),
            status=ExtractionOutcomeEnum(entity.status.value),
            extraction_version=entity.extraction_version,
            processor_name=entity.processor_name,
            processor_version=entity.processor_version,
            text_source=entity.text_source.value,
            document_reference=entity.document_reference,
            facts=list(entity.facts),
            metadata_payload=dict(entity.metadata),
            extracted_at=entity.extracted_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


__all__ = ["PublicationExtractionMapper"]
