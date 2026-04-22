"""Relation projection-lineage model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
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


class RelationProjectionSourceModel(Base):
    """Claim-backed lineage rows for canonical relation projections."""

    __tablename__ = "relation_projection_sources"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    relation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    claim_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    projection_origin: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
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
    agent_run_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
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
        graph_table_options(
            comment="Claim-backed lineage rows for canonical relation projections",
        ),
    )


__all__ = ["RelationProjectionSourceModel"]
