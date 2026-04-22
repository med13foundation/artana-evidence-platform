"""Claim evidence model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from src.models.database.base import Base
from src.type_definitions.common import JSONObject  # noqa: TC001


class ClaimEvidenceModel(Base):
    """Sentence/table/figure evidence rows attached to relation claims."""

    __tablename__ = "claim_evidence"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    claim_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("relation_claims.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    source_document_ref: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        doc="Graph-owned external document reference without platform identity coupling",
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    sentence: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentence_source: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    sentence_confidence: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    sentence_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    figure_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    table_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.5",
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_claim_evidence_claim_id", "claim_id"),
        Index("idx_claim_evidence_source_document_id", "source_document_id"),
        Index("idx_claim_evidence_source_document_ref", "source_document_ref"),
        Index("idx_claim_evidence_created_at", "created_at"),
        graph_table_options(
            comment="Evidence rows supporting extracted relation claims",
        ),
    )


__all__ = ["ClaimEvidenceModel"]
