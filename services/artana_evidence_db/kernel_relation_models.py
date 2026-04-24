"""Service-local graph relation ORM models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.orm_base import Base, require_table
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
    qualify_graph_table_name,
)
from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapped
_relations_table = Base.metadata.tables.get(qualify_graph_table_name("relations"))
if _relations_table is None:
    _relations_table = Table(
        "relations",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
            doc="Unique relation ID",
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
            doc="Owning research space",
        ),
        Column(
            "source_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("entities.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
            doc="Source entity",
        ),
        Column(
            "relation_type",
            String(64),
            ForeignKey(
                qualify_graph_foreign_key_target("dictionary_relation_types.id"),
            ),
            nullable=False,
            doc="Relationship type, e.g. CAUSES, ASSOCIATED_WITH",
        ),
        Column(
            "target_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("entities.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
            doc="Target entity",
        ),
        Column(
            "aggregate_confidence",
            Float,
            nullable=False,
            server_default="0.0",
            doc="Aggregate confidence score 0.0-1.0",
        ),
        Column(
            "source_count",
            Integer,
            nullable=False,
            server_default="0",
            doc="Number of supporting evidence rows",
        ),
        Column(
            "highest_evidence_tier",
            String(32),
            nullable=True,
            doc="Best evidence tier across all evidence rows",
        ),
        Column(
            "support_confidence",
            Float,
            nullable=False,
            server_default="0.0",
            doc="Aggregate confidence from supporting evidence only",
        ),
        Column(
            "refute_confidence",
            Float,
            nullable=False,
            server_default="0.0",
            doc="Aggregate confidence from refuting evidence only",
        ),
        Column(
            "distinct_source_family_count",
            Integer,
            nullable=False,
            server_default="0",
            doc="Number of independent source families contributing evidence",
        ),
        Column(
            "canonicalization_fingerprint",
            String(128),
            nullable=False,
            server_default="",
            doc=(
                "Hash of scoping context that distinguishes "
                "otherwise identical triples."
            ),
        ),
        Column(
            "curation_status",
            String(32),
            nullable=False,
            server_default="DRAFT",
            doc="DRAFT, UNDER_REVIEW, APPROVED, REJECTED, RETRACTED",
        ),
        Column(
            "provenance_id",
            PGUUID(as_uuid=True),
            ForeignKey(qualify_graph_foreign_key_target("provenance.id")),
            nullable=True,
            doc="Optional canonical provenance pointer",
        ),
        Column(
            "reviewed_by",
            PGUUID(as_uuid=True),
            nullable=True,
            doc="External actor identifier recorded without platform user FK coupling",
        ),
        Column(
            "reviewed_at",
            TIMESTAMP(timezone=True),
            nullable=True,
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        ),
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
        **graph_table_options(
            comment="Canonical graph edges with evidence and curation lifecycle",
        ),
    )

_relation_evidence_table = Base.metadata.tables.get(
    qualify_graph_table_name("relation_evidence"),
)
if _relation_evidence_table is None:
    _relation_evidence_table = Table(
        "relation_evidence",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
            doc="Unique evidence ID",
        ),
        Column(
            "relation_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("relations.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
            doc="Parent relation ID",
        ),
        Column(
            "confidence",
            Float,
            nullable=False,
            server_default="0.5",
            doc="Per-evidence confidence score 0.0-1.0",
        ),
        Column(
            "evidence_summary",
            Text,
            nullable=True,
            doc="Human-readable evidence summary",
        ),
        Column(
            "evidence_sentence",
            Text,
            nullable=True,
            doc="Supporting sentence/span text for this evidence row",
        ),
        Column(
            "evidence_sentence_source",
            Text,
            nullable=True,
            doc="Sentence provenance: verbatim_span or artana_generated",
        ),
        Column(
            "evidence_sentence_confidence",
            Text,
            nullable=True,
            doc="Confidence bucket for sentence provenance",
        ),
        Column(
            "evidence_sentence_rationale",
            Text,
            nullable=True,
            doc="Rationale for generated sentence or generation failure context",
        ),
        Column(
            "evidence_tier",
            String(32),
            nullable=False,
            server_default="COMPUTATIONAL",
            doc="Evidence tier classification",
        ),
        Column(
            "provenance_id",
            PGUUID(as_uuid=True),
            ForeignKey(qualify_graph_foreign_key_target("provenance.id")),
            nullable=True,
            doc="Link to ingestion provenance",
        ),
        Column(
            "source_document_id",
            PGUUID(as_uuid=True),
            nullable=True,
            doc="Optional source document reference",
        ),
        Column(
            "source_document_ref",
            String(512),
            nullable=True,
            doc="Graph-owned external document reference without platform identity coupling",
        ),
        Column(
            "agent_run_id",
            String(255),
            nullable=True,
            doc="Optional agent run reference",
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Index("idx_relation_evidence_relation", "relation_id"),
        Index("idx_relation_evidence_provenance", "provenance_id"),
        Index("idx_relation_evidence_tier", "evidence_tier"),
        Index("idx_relation_evidence_source_document_ref", "source_document_ref"),
        **graph_table_options(
            comment="Per-source evidence supporting canonical relation edges",
        ),
    )

_relations_table_model_table = require_table(_relations_table)

class GraphRelationModel(Base):
    """A canonical graph edge with evidence accumulation and curation lifecycle."""


    __table__ = _relations_table_model_table

    if TYPE_CHECKING:
        id: Mapped[UUID]
        research_space_id: Mapped[UUID]
        source_id: Mapped[UUID]
        relation_type: Mapped[str]
        target_id: Mapped[UUID]
        aggregate_confidence: Mapped[float]
        source_count: Mapped[int]
        highest_evidence_tier: Mapped[str | None]
        support_confidence: Mapped[float]
        refute_confidence: Mapped[float]
        distinct_source_family_count: Mapped[int]
        canonicalization_fingerprint: Mapped[str]
        curation_status: Mapped[str]
        provenance_id: Mapped[UUID | None]
        reviewed_by: Mapped[UUID | None]
        reviewed_at: Mapped[datetime | None]
        created_at: Mapped[datetime]
        updated_at: Mapped[datetime]

    evidences = relationship(
        "artana_evidence_db.kernel_relation_models.GraphRelationEvidenceModel",
        back_populates="relation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        overlaps="evidences,relation",
    )

    def __repr__(self) -> str:
        return (
            f"<RelationModel(src={self.source_id}, "
            f"rel={self.relation_type}, tgt={self.target_id})>"
        )


_relation_evidence_table_model_table = require_table(_relation_evidence_table)

class GraphRelationEvidenceModel(Base):
    """Supporting evidence rows for canonical graph edges."""


    __table__ = _relation_evidence_table_model_table

    if TYPE_CHECKING:
        id: Mapped[UUID]
        relation_id: Mapped[UUID]
        confidence: Mapped[float]
        evidence_summary: Mapped[str | None]
        evidence_sentence: Mapped[str | None]
        evidence_sentence_source: Mapped[str | None]
        evidence_sentence_confidence: Mapped[str | None]
        evidence_sentence_rationale: Mapped[str | None]
        evidence_tier: Mapped[str]
        provenance_id: Mapped[UUID | None]
        source_document_id: Mapped[UUID | None]
        source_document_ref: Mapped[str | None]
        agent_run_id: Mapped[str | None]
        created_at: Mapped[datetime]

    relation = relationship(
        "artana_evidence_db.kernel_relation_models.GraphRelationModel",
        back_populates="evidences",
        overlaps="evidences,relation",
    )


RelationModel = GraphRelationModel
RelationEvidenceModel = GraphRelationEvidenceModel

__all__ = ["RelationEvidenceModel", "RelationModel"]
