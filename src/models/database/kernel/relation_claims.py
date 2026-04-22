"""Relation claim ledger model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from src.models.database.base import Base
from src.type_definitions.common import JSONObject  # noqa: TC001


class RelationClaimModel(Base):
    """One extracted relation candidate captured for review."""

    __tablename__ = "relation_claims"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
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
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Stable client-provided replay key for claim idempotency",
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.0",
    )
    validation_state: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    persistability: Mapped[str] = mapped_column(String(32), nullable=False)
    assertion_class: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="SOURCE_BACKED",
        doc="Claim origin type: SOURCE_BACKED, CURATED, COMPUTATIONAL",
    )
    claim_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="OPEN",
    )
    polarity: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="UNCERTAIN",
    )
    claim_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_section: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_relation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("relations.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    triaged_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        doc="External actor identifier recorded without platform user FK coupling",
    )
    triaged_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint(
            "id",
            "research_space_id",
            name="uq_relation_claims_id_space",
        ),
        UniqueConstraint(
            "research_space_id",
            "source_ref",
            name="uq_relation_claims_space_source_ref",
        ),
        Index("idx_relation_claims_space", "research_space_id"),
        Index("idx_relation_claims_status", "claim_status"),
        Index("idx_relation_claims_space_polarity", "research_space_id", "polarity"),
        Index("idx_relation_claims_validation_state", "validation_state"),
        Index("idx_relation_claims_persistability", "persistability"),
        Index("idx_relation_claims_source_document_id", "source_document_id"),
        Index("idx_relation_claims_source_document_ref", "source_document_ref"),
        Index("idx_relation_claims_source_ref", "source_ref"),
        Index("idx_relation_claims_linked_relation_id", "linked_relation_id"),
        Index(
            "idx_relation_claims_space_created_at",
            "research_space_id",
            "created_at",
        ),
        graph_table_options(
            comment="Extracted relation candidate ledger for claim-first curation",
        ),
    )


__all__ = ["RelationClaimModel"]
