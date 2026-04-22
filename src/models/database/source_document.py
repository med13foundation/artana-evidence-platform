"""SQLAlchemy model for source document lifecycle tracking."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base


class DocumentFormatEnum(str, Enum):
    MEDLINE_XML = "medline_xml"
    CLINVAR_XML = "clinvar_xml"
    MARRVEL_JSON = "marrvel_json"
    CSV = "csv"
    JSON = "json"
    PDF = "pdf"
    TEXT = "text"


class EnrichmentStatusEnum(str, Enum):
    PENDING = "pending"
    ENRICHED = "enriched"
    SKIPPED = "skipped"
    FAILED = "failed"


class DocumentExtractionStatusEnum(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    EXTRACTED = "extracted"
    FAILED = "failed"


class SourceDocumentModel(Base):
    """Persisted document lifecycle state between ingestion and extraction tiers."""

    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
    )
    research_space_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("research_spaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("user_data_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ingestion_job_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("ingestion_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_record_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    document_format: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=DocumentFormatEnum.JSON.value,
    )
    raw_storage_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    enriched_storage_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    content_length_chars: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    enrichment_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=EnrichmentStatusEnum.PENDING.value,
        index=True,
    )
    enrichment_method: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    enrichment_agent_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    extraction_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentExtractionStatusEnum.PENDING.value,
        index=True,
    )
    extraction_agent_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "external_record_id",
            name="uq_source_documents_source_external_record",
        ),
        Index(
            "idx_source_documents_source_enrichment_status",
            "source_id",
            "enrichment_status",
        ),
        Index(
            "idx_source_documents_source_extraction_status",
            "source_id",
            "extraction_status",
        ),
    )


__all__ = [
    "DocumentExtractionStatusEnum",
    "DocumentFormatEnum",
    "EnrichmentStatusEnum",
    "SourceDocumentModel",
]
