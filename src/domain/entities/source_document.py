"""Domain entity for lifecycle tracking of fetched source documents."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.user_data_source import SourceType  # noqa: TC001
from src.type_definitions.common import JSONObject  # noqa: TC001

UpdatePayload = dict[str, object]


def _empty_metadata() -> JSONObject:
    return {}


class DocumentFormat(StrEnum):
    """Supported canonical formats for source document payloads."""

    MEDLINE_XML = "medline_xml"
    CLINVAR_XML = "clinvar_xml"
    MARRVEL_JSON = "marrvel_json"
    CSV = "csv"
    JSON = "json"
    PDF = "pdf"
    TEXT = "text"
    HPO_OBO = "hpo_obo"
    UNIPROT_JSON = "uniprot_json"
    DRUGBANK_JSON = "drugbank_json"
    ALPHAFOLD_JSON = "alphafold_json"


class EnrichmentStatus(StrEnum):
    """Lifecycle status for Tier-2 content enrichment."""

    PENDING = "pending"
    ENRICHED = "enriched"
    SKIPPED = "skipped"
    FAILED = "failed"


class DocumentExtractionStatus(StrEnum):
    """Lifecycle status for Tier-3 knowledge extraction."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    EXTRACTED = "extracted"
    FAILED = "failed"


class SourceDocument(BaseModel):
    """Represents one source record tracked in the Document Store."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    research_space_id: UUID | None = None
    source_id: UUID
    ingestion_job_id: UUID | None = None
    external_record_id: str = Field(..., min_length=1, max_length=255)
    source_type: SourceType
    document_format: DocumentFormat
    raw_storage_key: str | None = None
    enriched_storage_key: str | None = None
    content_hash: str | None = Field(default=None, max_length=128)
    content_length_chars: int | None = Field(default=None, ge=0)
    enrichment_status: EnrichmentStatus = EnrichmentStatus.PENDING
    enrichment_method: str | None = Field(default=None, max_length=64)
    enrichment_agent_run_id: str | None = Field(default=None, max_length=255)
    extraction_status: DocumentExtractionStatus = DocumentExtractionStatus.PENDING
    extraction_agent_run_id: str | None = Field(default=None, max_length=255)
    metadata: JSONObject = Field(default_factory=_empty_metadata)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def mark_enriched(  # noqa: PLR0913
        self,
        *,
        enriched_storage_key: str,
        content_hash: str | None = None,
        content_length_chars: int | None = None,
        enrichment_method: str | None = None,
        enrichment_agent_run_id: str | None = None,
        enriched_at: datetime | None = None,
    ) -> SourceDocument:
        """Return an updated document marked as enriched."""
        now = enriched_at or datetime.now(UTC)
        update_payload: UpdatePayload = {
            "enriched_storage_key": enriched_storage_key,
            "content_hash": content_hash,
            "content_length_chars": content_length_chars,
            "enrichment_status": EnrichmentStatus.ENRICHED,
            "enrichment_method": enrichment_method,
            "enrichment_agent_run_id": enrichment_agent_run_id,
            "updated_at": now,
        }
        return self.model_copy(update=update_payload)

    def mark_extraction_in_progress(
        self,
        *,
        extraction_agent_run_id: str | None = None,
        started_at: datetime | None = None,
    ) -> SourceDocument:
        """Return an updated document marked as in-progress for extraction."""
        now = started_at or datetime.now(UTC)
        update_payload: UpdatePayload = {
            "extraction_status": DocumentExtractionStatus.IN_PROGRESS,
            "extraction_agent_run_id": extraction_agent_run_id,
            "updated_at": now,
        }
        return self.model_copy(update=update_payload)

    def mark_extracted(
        self,
        *,
        extraction_agent_run_id: str | None = None,
        extracted_at: datetime | None = None,
    ) -> SourceDocument:
        """Return an updated document marked as extracted."""
        now = extracted_at or datetime.now(UTC)
        update_payload: UpdatePayload = {
            "extraction_status": DocumentExtractionStatus.EXTRACTED,
            "extraction_agent_run_id": extraction_agent_run_id,
            "updated_at": now,
        }
        return self.model_copy(update=update_payload)


__all__ = [
    "DocumentExtractionStatus",
    "DocumentFormat",
    "EnrichmentStatus",
    "SourceDocument",
]
