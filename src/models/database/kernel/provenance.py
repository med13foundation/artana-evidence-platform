"""
Provenance model — tracks where every piece of data came from.

Every observation and relation can point to a provenance record
that captures the extraction source, method, confidence, and
the raw unmapped input.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Float, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import graph_table_options
from src.models.database.base import Base
from src.type_definitions.common import JSONObject  # noqa: TC001


class ProvenanceModel(Base):
    """
    Provenance chain — records how data entered the system.

    Captures source type, extraction method, AI model used,
    mapping confidence, and the raw input for reproducibility.
    """

    __tablename__ = "provenance"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique provenance ID",
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        doc="Owning research space",
    )
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="FILE_UPLOAD, API_FETCH, AI_EXTRACTION, MANUAL",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="File path, URL, or session ID",
    )
    extraction_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Optional ingestion/agent run reference",
    )
    mapping_method: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="exact_match, vector_search, llm_judge",
    )
    mapping_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Confidence of the mapping (0.0-1.0)",
    )
    agent_model: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="AI model used, e.g. gpt-5, rule-based",
    )
    raw_input: Mapped[JSONObject | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Original unmapped data for reproducibility",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_provenance_space", "research_space_id"),
        Index("idx_provenance_source_type", "source_type"),
        Index("idx_provenance_extraction", "extraction_run_id"),
        graph_table_options(comment="Data provenance chain for reproducibility"),
    )

    def __repr__(self) -> str:
        return f"<ProvenanceModel(id={self.id}, source_type={self.source_type})>"
