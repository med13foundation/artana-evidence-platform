"""
Relation model — the graph edges.

Replaces old EvidenceModel and implicit relationships between
entity-specific models. Every edge is now:
  source (entity) --[relation_type]--> target (entity)
with evidence, curation status, and provenance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.graph_schema import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from src.models.database.base import Base


class RelationModel(Base):
    """
    A canonical graph edge with evidence accumulation and curation lifecycle.

    Represents typed relationships between any two entities:
      GENE --ASSOCIATED_WITH--> PHENOTYPE
      PUBLICATION --SUPPORTS--> VARIANT
      DRUG --TARGETS--> PATHWAY
    """

    __tablename__ = "relations"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique relation ID",
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        doc="Owning research space",
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("entities.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        doc="Source entity",
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_relation_types.id")),
        nullable=False,
        doc="Relationship type, e.g. CAUSES, ASSOCIATED_WITH",
    )
    target_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("entities.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        doc="Target entity",
    )

    # Aggregated evidence metadata
    aggregate_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.0",
        doc="Aggregate confidence score 0.0-1.0",
    )
    source_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        doc="Number of supporting evidence rows",
    )
    highest_evidence_tier: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Best evidence tier across all evidence rows",
    )

    # Evidence quality aggregation (P2.5)
    support_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.0",
        doc="Aggregate confidence from supporting evidence only",
    )
    refute_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.0",
        doc="Aggregate confidence from refuting evidence only",
    )
    distinct_source_family_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        doc="Number of independent source families contributing evidence",
    )

    # Context-aware canonicalization (P0.2)
    canonicalization_fingerprint: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="",
        doc=(
            "Hash of scoping context (tissue, organism, population, etc.) "
            "that distinguishes otherwise identical triples."
        ),
    )

    # Curation lifecycle
    curation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="DRAFT",
        doc="DRAFT, UNDER_REVIEW, APPROVED, REJECTED, RETRACTED",
    )

    # Legacy canonical provenance pointer (evidence-level provenance is authoritative)
    provenance_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("provenance.id")),
        nullable=True,
        doc="Optional canonical provenance pointer",
    )

    # Review tracking
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        doc="External actor identifier recorded without platform user FK coupling",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    evidences: Mapped[list[RelationEvidenceModel]] = relationship(
        "RelationEvidenceModel",
        back_populates="relation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_relations_source_space_entities",
        ),
        ForeignKeyConstraint(
            ["target_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_relations_target_space_entities",
        ),
        Index("idx_relations_source", "source_id"),
        Index("idx_relations_target", "target_id"),
        Index("idx_relations_space_type", "research_space_id", "relation_type"),
        Index("idx_relations_space_created_at", "research_space_id", "created_at"),
        Index("idx_relations_curation", "curation_status"),
        Index("idx_relations_provenance", "provenance_id"),
        Index("idx_relations_aggregate_confidence", "aggregate_confidence"),
        UniqueConstraint(
            "id",
            "research_space_id",
            name="uq_relations_id_space",
        ),
        UniqueConstraint(
            "source_id",
            "relation_type",
            "target_id",
            "research_space_id",
            "canonicalization_fingerprint",
            name="uq_relations_canonical_edge",
        ),
        graph_table_options(
            comment="Canonical graph edges with evidence and curation lifecycle",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RelationModel(src={self.source_id}, "
            f"rel={self.relation_type}, tgt={self.target_id})>"
        )


class RelationEvidenceModel(Base):
    """Supporting evidence rows for canonical graph edges."""

    __tablename__ = "relation_evidence"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique evidence ID",
    )
    relation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("relations.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        doc="Parent relation ID",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.5",
        doc="Per-evidence confidence score 0.0-1.0",
    )
    evidence_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable evidence summary",
    )
    evidence_sentence: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Supporting sentence/span text for this evidence row",
    )
    evidence_sentence_source: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Sentence provenance: verbatim_span or artana_generated",
    )
    evidence_sentence_confidence: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Confidence bucket for sentence provenance",
    )
    evidence_sentence_rationale: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Rationale for generated sentence or generation failure context",
    )
    evidence_tier: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="COMPUTATIONAL",
        doc="Evidence tier classification",
    )
    provenance_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("provenance.id")),
        nullable=True,
        doc="Link to ingestion provenance",
    )
    source_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        doc="Optional source document reference",
    )
    source_document_ref: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        doc="Graph-owned external document reference without platform identity coupling",
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Optional agent run reference",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    relation: Mapped[RelationModel] = relationship(
        "RelationModel",
        back_populates="evidences",
    )

    __table_args__ = (
        Index("idx_relation_evidence_relation", "relation_id"),
        Index("idx_relation_evidence_provenance", "provenance_id"),
        Index("idx_relation_evidence_tier", "evidence_tier"),
        Index("idx_relation_evidence_source_document_ref", "source_document_ref"),
        graph_table_options(
            comment="Per-source evidence supporting canonical relation edges",
        ),
    )


__all__ = ["RelationEvidenceModel", "RelationModel"]
