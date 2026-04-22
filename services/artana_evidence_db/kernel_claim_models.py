"""Service-local kernel claim ORM models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID

_claim_evidence_table = Base.metadata.tables.get("claim_evidence")
if _claim_evidence_table is None:
    _claim_evidence_table = Table(
        "claim_evidence",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        Column(
            "claim_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("relation_claims.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column(
            "source_document_id",
            PGUUID(as_uuid=True),
            nullable=True,
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
        ),
        Column("sentence", Text, nullable=True),
        Column(
            "sentence_source",
            String(32),
            nullable=True,
        ),
        Column(
            "sentence_confidence",
            String(16),
            nullable=True,
        ),
        Column("sentence_rationale", Text, nullable=True),
        Column("figure_reference", Text, nullable=True),
        Column("table_reference", Text, nullable=True),
        Column(
            "confidence",
            Float,
            nullable=False,
            server_default="0.5",
        ),
        Column(
            "metadata_payload",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Index("idx_claim_evidence_claim_id", "claim_id"),
        Index("idx_claim_evidence_source_document_id", "source_document_id"),
        Index("idx_claim_evidence_source_document_ref", "source_document_ref"),
        Index("idx_claim_evidence_created_at", "created_at"),
        **graph_table_options(
            comment="Evidence rows supporting extracted relation claims",
        ),
    )

_claim_participants_table = Base.metadata.tables.get("claim_participants")
if _claim_participants_table is None:
    _claim_participants_table = Table(
        "claim_participants",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        Column("claim_id", PGUUID(as_uuid=True), nullable=False),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column("label", String(512), nullable=True),
        Column("entity_id", PGUUID(as_uuid=True), nullable=True),
        Column("role", String(32), nullable=False),
        Column("position", SmallInteger, nullable=True),
        Column(
            "qualifiers",
            JSONB,
            nullable=False,
            server_default="{}",
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
        CheckConstraint(
            "role IN ('SUBJECT', 'OBJECT', 'CONTEXT', 'QUALIFIER', 'MODIFIER', 'OUTCOME')",
            name="ck_claim_participants_role",
        ),
        CheckConstraint(
            "label IS NOT NULL OR entity_id IS NOT NULL",
            name="ck_claim_participants_anchor",
        ),
        ForeignKeyConstraint(
            ["claim_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("relation_claims.id"),
                qualify_graph_foreign_key_target("relation_claims.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_claim_participants_claim_space",
        ),
        ForeignKeyConstraint(
            ["entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="RESTRICT",
            name="fk_claim_participants_entity_space",
        ),
        Index("idx_claim_participants_claim", "claim_id"),
        Index(
            "idx_claim_participants_space_entity",
            "research_space_id",
            "entity_id",
            postgresql_where=text("entity_id IS NOT NULL"),
        ),
        Index("idx_claim_participants_space_role", "research_space_id", "role"),
        **graph_table_options(
            comment="Structured claim participants with role semantics",
        ),
    )

_relation_claims_table = Base.metadata.tables.get("relation_claims")
if _relation_claims_table is None:
    _relation_claims_table = Table(
        "relation_claims",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "source_document_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
        Column(
            "source_document_ref",
            String(512),
            nullable=True,
            doc="Graph-owned external document reference without platform identity coupling",
        ),
        Column(
            "source_ref",
            String(1024),
            nullable=True,
            doc="Stable client-provided replay key for claim idempotency",
        ),
        Column(
            "agent_run_id",
            String(255),
            nullable=True,
        ),
        Column("source_type", String(64), nullable=False),
        Column("relation_type", String(64), nullable=False),
        Column("target_type", String(64), nullable=False),
        Column("source_label", String(512), nullable=True),
        Column("target_label", String(512), nullable=True),
        Column(
            "confidence",
            Float,
            nullable=False,
            server_default="0.0",
        ),
        Column("validation_state", String(32), nullable=False),
        Column("validation_reason", Text, nullable=True),
        Column("persistability", String(32), nullable=False),
        Column(
            "assertion_class",
            String(32),
            nullable=False,
            server_default="SOURCE_BACKED",
            doc="Claim origin type: SOURCE_BACKED, CURATED, COMPUTATIONAL",
        ),
        Column(
            "claim_status",
            String(32),
            nullable=False,
            server_default="OPEN",
        ),
        Column(
            "polarity",
            String(16),
            nullable=False,
            server_default="UNCERTAIN",
        ),
        Column("claim_text", Text, nullable=True),
        Column("claim_section", String(64), nullable=True),
        Column(
            "linked_relation_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("relations.id"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        Column(
            "metadata_payload",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
        Column(
            "triaged_by",
            PGUUID(as_uuid=True),
            nullable=True,
            doc="External actor identifier recorded without platform user FK coupling",
        ),
        Column(
            "triaged_at",
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
        Index("idx_relation_claims_assertion_class", "assertion_class"),
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
        **graph_table_options(
            comment="Extracted relation candidate ledger for claim-first curation",
        ),
    )

_relation_projection_sources_table = Base.metadata.tables.get(
    "relation_projection_sources",
)
if _relation_projection_sources_table is None:
    _relation_projection_sources_table = Table(
        "relation_projection_sources",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "relation_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "claim_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "projection_origin",
            String(32),
            nullable=False,
        ),
        Column(
            "source_document_id",
            PGUUID(as_uuid=True),
            nullable=True,
            doc="External source-document reference recorded without shared-schema FK",
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
        ),
        Column(
            "metadata_payload",
            JSONB,
            nullable=False,
            server_default="{}",
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
            ["relation_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("relations.id"),
                qualify_graph_foreign_key_target("relations.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_relation_projection_sources_relation_space",
        ),
        ForeignKeyConstraint(
            ["claim_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("relation_claims.id"),
                qualify_graph_foreign_key_target("relation_claims.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_relation_projection_sources_claim_space",
        ),
        CheckConstraint(
            (
                "projection_origin IN "
                "('EXTRACTION','CLAIM_RESOLUTION','MANUAL_RELATION','GRAPH_CONNECTION')"
            ),
            name="ck_relation_projection_sources_origin",
        ),
        UniqueConstraint(
            "research_space_id",
            "relation_id",
            "claim_id",
            name="uq_relation_projection_sources_edge_claim",
        ),
        Index("idx_relation_projection_sources_relation_id", "relation_id"),
        Index("idx_relation_projection_sources_claim_id", "claim_id"),
        Index(
            "idx_relation_projection_sources_source_document_ref",
            "source_document_ref",
        ),
        Index(
            "idx_relation_projection_sources_space_origin",
            "research_space_id",
            "projection_origin",
        ),
        **graph_table_options(
            comment="Claim-backed lineage rows for canonical relation projections",
        ),
    )


class GraphClaimEvidenceModel(Base):
    """Sentence/table/figure evidence rows attached to relation claims."""

    __table__ = _claim_evidence_table


class GraphClaimParticipantModel(Base):
    """N-ary participant rows linked to relation claims."""

    __table__ = _claim_participants_table


class GraphRelationClaimModel(Base):
    """One extracted relation candidate captured for review."""

    __table__ = _relation_claims_table


class GraphRelationProjectionSourceModel(Base):
    """Claim-backed lineage rows for canonical relation projections."""

    __table__ = _relation_projection_sources_table


ClaimEvidenceModel = GraphClaimEvidenceModel
ClaimParticipantModel = GraphClaimParticipantModel
RelationClaimModel = GraphRelationClaimModel
RelationProjectionSourceModel = GraphRelationProjectionSourceModel

__all__ = [
    "ClaimEvidenceModel",
    "ClaimParticipantModel",
    "RelationClaimModel",
    "RelationProjectionSourceModel",
]
