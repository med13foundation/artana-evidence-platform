"""Claim relation model for directed claim-to-claim edges."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from src.models.database.base import Base
from src.type_definitions.common import JSONObject  # noqa: TC001


class ClaimRelationModel(Base):
    """Directed semantic relation between two relation claims."""

    __tablename__ = "claim_relations"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    source_claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    target_claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        doc="External source-document reference recorded without shared-schema FK",
    )
    source_document_ref: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        doc="Graph-owned external document reference without platform identity coupling",
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.5",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="PROPOSED",
    )
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        CheckConstraint(
            (
                "relation_type IN "
                "('SUPPORTS','CONTRADICTS','REFINES','CAUSES','UPSTREAM_OF',"
                "'DOWNSTREAM_OF','SAME_AS','GENERALIZES','INSTANCE_OF')"
            ),
            name="ck_claim_relations_type",
        ),
        CheckConstraint(
            "source_claim_id <> target_claim_id",
            name="ck_claim_relations_no_self_loop",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_claim_relations_confidence_range",
        ),
        CheckConstraint(
            "review_status IN ('PROPOSED','ACCEPTED','REJECTED')",
            name="ck_claim_relations_review_status",
        ),
        ForeignKeyConstraint(
            ["source_claim_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("relation_claims.id"),
                qualify_graph_foreign_key_target("relation_claims.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_claim_relations_source_space",
        ),
        ForeignKeyConstraint(
            ["target_claim_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("relation_claims.id"),
                qualify_graph_foreign_key_target("relation_claims.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_claim_relations_target_space",
        ),
        UniqueConstraint(
            "research_space_id",
            "source_claim_id",
            "relation_type",
            "target_claim_id",
            name="uq_claim_relations_space_edge",
        ),
        Index("idx_claim_relations_source", "source_claim_id"),
        Index("idx_claim_relations_target", "target_claim_id"),
        Index("idx_claim_relations_space_type", "research_space_id", "relation_type"),
        Index("idx_claim_relations_review_status", "review_status"),
        Index("idx_claim_relations_source_document_ref", "source_document_ref"),
        graph_table_options(
            comment="Claim-to-claim graph edges with provenance and governance state",
        ),
    )


__all__ = ["ClaimRelationModel"]
