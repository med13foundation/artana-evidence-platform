"""Database models for graph query read models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID  # noqa: TC003

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from src.models.database.base import Base


class EntityRelationSummaryModel(Base):
    """Derived relation summary row for one entity."""

    __tablename__ = "entity_relation_summary"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    outgoing_relation_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    incoming_relation_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    total_relation_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    distinct_relation_type_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    support_claim_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    last_projection_at: Mapped[datetime | None] = mapped_column(
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
        ForeignKeyConstraint(
            ["entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_entity_relation_summary_entity_space",
        ),
        Index(
            "idx_entity_relation_summary_space_total",
            "research_space_id",
            "total_relation_count",
        ),
        Index(
            "idx_entity_relation_summary_space_entity",
            "research_space_id",
            "entity_id",
        ),
        graph_table_options(
            comment="Derived per-entity relation summary rebuilt from canonical relations and projection lineage",
        ),
    )


class EntityNeighborModel(Base):
    """Derived one-hop adjacency row for one entity-visible relation."""

    __tablename__ = "entity_neighbors"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )
    relation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("relations.id"),
            ondelete="CASCADE",
        ),
        primary_key=True,
        nullable=False,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    neighbor_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    relation_updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
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
            ["entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_entity_neighbors_entity_space",
        ),
        ForeignKeyConstraint(
            ["neighbor_entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_entity_neighbors_neighbor_space",
        ),
        Index(
            "idx_entity_neighbors_space_entity_updated",
            "research_space_id",
            "entity_id",
            "relation_updated_at",
        ),
        Index(
            "idx_entity_neighbors_space_neighbor",
            "research_space_id",
            "neighbor_entity_id",
        ),
        graph_table_options(
            comment=(
                "Derived one-hop entity neighborhood rebuilt from canonical "
                "relations and projection lineage"
            ),
        ),
    )


class EntityClaimSummaryModel(Base):
    """Derived claim summary row for one entity."""

    __tablename__ = "entity_claim_summary"

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    total_claim_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    support_claim_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    resolved_claim_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    open_claim_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    linked_claim_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    projected_claim_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    last_claim_activity_at: Mapped[datetime | None] = mapped_column(
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
        ForeignKeyConstraint(
            ["entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_entity_claim_summary_entity_space",
        ),
        Index(
            "idx_entity_claim_summary_space_total",
            "research_space_id",
            "total_claim_count",
        ),
        Index(
            "idx_entity_claim_summary_space_entity",
            "research_space_id",
            "entity_id",
        ),
        graph_table_options(
            comment=(
                "Derived per-entity claim summary rebuilt from the claim ledger "
                "and projection lineage"
            ),
        ),
    )


class EntityMechanismPathModel(Base):
    """Derived mechanism-path candidate row for one seed entity."""

    __tablename__ = "entity_mechanism_paths"

    path_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("reasoning_paths.id"),
            ondelete="CASCADE",
        ),
        primary_key=True,
        nullable=False,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    seed_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    end_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    path_length: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        nullable=False,
    )
    supporting_claim_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    path_updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
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
            ["seed_entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_entity_mechanism_paths_seed_entity_space",
        ),
        ForeignKeyConstraint(
            ["end_entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_entity_mechanism_paths_end_entity_space",
        ),
        Index(
            "idx_entity_mechanism_paths_space_seed_confidence",
            "research_space_id",
            "seed_entity_id",
            "confidence",
        ),
        Index(
            "idx_entity_mechanism_paths_space_end",
            "research_space_id",
            "end_entity_id",
        ),
        graph_table_options(
            comment=(
                "Derived per-seed mechanism path candidates rebuilt from "
                "persisted reasoning paths"
            ),
        ),
    )


__all__ = [
    "EntityClaimSummaryModel",
    "EntityMechanismPathModel",
    "EntityNeighborModel",
    "EntityRelationSummaryModel",
]
