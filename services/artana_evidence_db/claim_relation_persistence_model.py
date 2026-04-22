"""Service-local ORM model for claim-to-claim relation edges."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
    qualify_graph_table_name,
)
from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID


def _existing_table(table_name: str) -> Table | None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        return table
    return Base.metadata.tables.get(qualify_graph_table_name(table_name))


_claim_relations_table = _existing_table("claim_relations")
if _claim_relations_table is None:
    _claim_relations_table = Table(
        "claim_relations",
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
            "source_claim_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "target_claim_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "relation_type",
            String(32),
            nullable=False,
        ),
        Column(
            "agent_run_id",
            String(255),
            nullable=True,
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
            "confidence",
            Float,
            nullable=False,
            server_default="0.5",
        ),
        Column(
            "review_status",
            String(16),
            nullable=False,
            server_default="PROPOSED",
        ),
        Column(
            "evidence_summary",
            Text,
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
            ["source_claim_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("relation_claims.id"),
                qualify_graph_foreign_key_target("relation_claims.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_claim_relations_source_claim_space",
        ),
        ForeignKeyConstraint(
            ["target_claim_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("relation_claims.id"),
                qualify_graph_foreign_key_target("relation_claims.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_claim_relations_target_claim_space",
        ),
        CheckConstraint(
            "source_claim_id <> target_claim_id",
            name="ck_claim_relations_no_self_loop",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_claim_relations_confidence",
        ),
        CheckConstraint(
            "review_status IN ('PROPOSED', 'ACCEPTED', 'REJECTED')",
            name="ck_claim_relations_review_status",
        ),
        UniqueConstraint(
            "id",
            "research_space_id",
            name="uq_claim_relations_id_space",
        ),
        Index("idx_claim_relations_space", "research_space_id"),
        Index("idx_claim_relations_review_status", "review_status"),
        Index("idx_claim_relations_source_claim_id", "source_claim_id"),
        Index("idx_claim_relations_target_claim_id", "target_claim_id"),
        Index("idx_claim_relations_source_document_ref", "source_document_ref"),
        Index(
            "idx_claim_relations_space_created_at",
            "research_space_id",
            "created_at",
        ),
        **graph_table_options(
            comment="Directed claim-to-claim ledger edges for mechanism reasoning",
        ),
    )


class GraphClaimRelationModel(Base):
    """Directed claim-to-claim ledger edge."""

    __table__ = _claim_relations_table


ClaimRelationModel = GraphClaimRelationModel

__all__ = ["ClaimRelationModel"]
