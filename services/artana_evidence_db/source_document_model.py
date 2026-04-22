"""Service-local source-document persistence models."""

from __future__ import annotations

from enum import Enum

from artana_evidence_db.orm_base import Base
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID


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


_source_documents_table = Base.metadata.tables.get("source_documents")
if _source_documents_table is None:
    _source_documents_table = Table(
        "source_documents",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=False),
            primary_key=True,
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=False),
            nullable=True,
            index=True,
            doc="External space reference stored without platform FK coupling",
        ),
        Column(
            "source_id",
            PGUUID(as_uuid=False),
            nullable=False,
            index=True,
            doc="External source reference stored without platform FK coupling",
        ),
        Column(
            "ingestion_job_id",
            PGUUID(as_uuid=False),
            nullable=True,
            index=True,
            doc="External ingestion job reference stored without platform FK coupling",
        ),
        Column(
            "external_record_id",
            String(255),
            nullable=False,
        ),
        Column(
            "source_type",
            String(32),
            nullable=False,
            index=True,
        ),
        Column(
            "document_format",
            String(64),
            nullable=False,
            default=DocumentFormatEnum.JSON.value,
        ),
        Column(
            "raw_storage_key",
            String(500),
            nullable=True,
        ),
        Column(
            "enriched_storage_key",
            String(500),
            nullable=True,
        ),
        Column(
            "content_hash",
            String(128),
            nullable=True,
        ),
        Column(
            "content_length_chars",
            Integer,
            nullable=True,
        ),
        Column(
            "enrichment_status",
            String(32),
            nullable=False,
            default=EnrichmentStatusEnum.PENDING.value,
            index=True,
        ),
        Column(
            "enrichment_method",
            String(64),
            nullable=True,
        ),
        Column(
            "enrichment_agent_run_id",
            String(255),
            nullable=True,
        ),
        Column(
            "extraction_status",
            String(32),
            nullable=False,
            default=DocumentExtractionStatusEnum.PENDING.value,
            index=True,
        ),
        Column(
            "extraction_agent_run_id",
            String(255),
            nullable=True,
        ),
        Column(
            "metadata_payload",
            JSON,
            nullable=False,
            default=dict,
        ),
        Column(
            "created_at",
            DateTime(),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            DateTime(),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
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


class SourceDocumentModel(Base):
    """Persisted document lifecycle state between ingestion and extraction tiers."""

    __table__ = _source_documents_table


__all__ = [
    "DocumentExtractionStatusEnum",
    "DocumentFormatEnum",
    "EnrichmentStatusEnum",
    "SourceDocumentModel",
]
