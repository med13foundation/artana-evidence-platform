"""Source-document lifecycle models for the evidence API bridge."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field


class SourceType(StrEnum):
    """Source types needed by the research-init observation bridge."""

    FILE_UPLOAD = "file_upload"
    PUBMED = "pubmed"


class DocumentFormat(StrEnum):
    """Canonical document formats used by the observation bridge."""

    ALPHAFOLD_JSON = "alphafold_json"
    CLINVAR_XML = "clinvar_xml"
    CSV = "csv"
    DRUGBANK_JSON = "drugbank_json"
    HPO_OBO = "hpo_obo"
    JSON = "json"
    MARRVEL_JSON = "marrvel_json"
    MEDLINE_XML = "medline_xml"
    PDF = "pdf"
    TEXT = "text"
    UNIPROT_JSON = "uniprot_json"


class EnrichmentStatus(StrEnum):
    """Enrichment lifecycle values used by bridged source documents."""

    PENDING = "pending"
    ENRICHED = "enriched"
    SKIPPED = "skipped"
    FAILED = "failed"


class DocumentExtractionStatus(StrEnum):
    """Extraction lifecycle values used by bridged source documents."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    EXTRACTED = "extracted"
    FAILED = "failed"


def _empty_metadata() -> JSONObject:
    return {}


class SourceDocument(BaseModel):
    """Service-local document lifecycle entity used by the observation bridge."""

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


class SourceDocumentRepositoryProtocol(Protocol):
    """Minimal repository surface used by the observation-bridge runtime."""

    def get_by_id(self, document_id: UUID) -> object | None: ...

    def upsert(self, document: object) -> object: ...

    def upsert_many(self, documents: list[object]) -> Sequence[object]: ...

    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> Sequence[object]: ...

    def recover_stale_in_progress_extraction(
        self,
        *,
        stale_before: datetime,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        limit: int = 500,
    ) -> int: ...


class ObservationBridgeEntityRecognitionServiceProtocol(Protocol):
    """Entity-recognition service hooks used by the observation bridge."""

    async def process_pending_documents(
        self,
        *,
        limit: int,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
        pipeline_run_id: str | None = None,
    ) -> object: ...

    async def close(self) -> None: ...


__all__ = [
    "DocumentExtractionStatus",
    "DocumentFormat",
    "EnrichmentStatus",
    "ObservationBridgeEntityRecognitionServiceProtocol",
    "SourceDocument",
    "SourceDocumentRepositoryProtocol",
    "SourceType",
]
