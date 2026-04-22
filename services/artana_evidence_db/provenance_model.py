"""Service-local graph provenance ORM model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_table_name,
)
from sqlalchemy import Column, Float, Index, String, Table
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID


def _existing_table(table_name: str) -> Table | None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        return table
    return Base.metadata.tables.get(qualify_graph_table_name(table_name))


_provenance_table = _existing_table("provenance")
if _provenance_table is None:
    _provenance_table = Table(
        "provenance",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
            doc="Unique provenance ID",
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
            doc="Owning research space",
        ),
        Column(
            "source_type",
            String(64),
            nullable=False,
            doc="FILE_UPLOAD, API_FETCH, AI_EXTRACTION, MANUAL",
        ),
        Column(
            "source_ref",
            String(1024),
            nullable=True,
            doc="File path, URL, or session ID",
        ),
        Column(
            "extraction_run_id",
            String(255),
            nullable=True,
            doc="Optional ingestion or agent run reference",
        ),
        Column(
            "mapping_method",
            String(64),
            nullable=True,
            doc="exact_match, vector_search, llm_judge",
        ),
        Column(
            "mapping_confidence",
            Float,
            nullable=True,
            doc="Confidence of the mapping (0.0-1.0)",
        ),
        Column(
            "agent_model",
            String(128),
            nullable=True,
            doc="AI model used, e.g. gpt-5, rule-based",
        ),
        Column(
            "raw_input",
            JSONB,
            nullable=True,
            doc="Original unmapped data for reproducibility",
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Index("idx_provenance_space", "research_space_id"),
        Index("idx_provenance_source_type", "source_type"),
        Index("idx_provenance_extraction", "extraction_run_id"),
        **graph_table_options(comment="Data provenance chain for reproducibility"),
    )


class GraphProvenanceModel(Base):
    """Service-local provenance chain row."""

    __table__ = _provenance_table


ProvenanceModel = GraphProvenanceModel

__all__ = ["ProvenanceModel"]
