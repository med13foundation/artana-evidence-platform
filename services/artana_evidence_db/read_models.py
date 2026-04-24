"""Service-local graph read-model mappings used by relation queries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

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
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID


def _existing_table(table_name: str) -> Table | None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        return table
    return Base.metadata.tables.get(qualify_graph_table_name(table_name))


if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Mapped
_entity_neighbors_table = _existing_table("entity_neighbors")
_entity_relation_summary_table = _existing_table("entity_relation_summary")
_entity_claim_summary_table = _existing_table("entity_claim_summary")
_entity_mechanism_paths_table = _existing_table("entity_mechanism_paths")

if _entity_relation_summary_table is None:
    _entity_relation_summary_table = Table(
        "entity_relation_summary",
        Base.metadata,
        Column(
            "entity_id",
            PGUUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "outgoing_relation_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "incoming_relation_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "total_relation_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "distinct_relation_type_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "support_claim_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "last_projection_at",
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
        **graph_table_options(
            comment=(
                "Derived per-entity relation summary rebuilt from canonical "
                "relations and projection lineage"
            ),
        ),
    )

if _entity_neighbors_table is None:
    _entity_neighbors_table = Table(
        "entity_neighbors",
        Base.metadata,
        Column(
            "entity_id",
            PGUUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        Column(
            "relation_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("relations.id"),
                ondelete="CASCADE",
            ),
            primary_key=True,
            nullable=False,
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "neighbor_entity_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "relation_type",
            String(64),
            nullable=False,
        ),
        Column(
            "direction",
            String(16),
            nullable=False,
        ),
        Column(
            "relation_updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
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
        **graph_table_options(
            comment=(
                "Derived one-hop entity neighborhood rebuilt from canonical "
                "relations and projection lineage"
            ),
        ),
    )

if _entity_claim_summary_table is None:
    _entity_claim_summary_table = Table(
        "entity_claim_summary",
        Base.metadata,
        Column(
            "entity_id",
            PGUUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "total_claim_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "support_claim_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "resolved_claim_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "open_claim_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "linked_claim_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "projected_claim_count",
            Integer,
            nullable=False,
            server_default="0",
        ),
        Column(
            "last_claim_activity_at",
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
        **graph_table_options(
            comment=(
                "Derived claim summary row for one entity rebuilt from claim "
                "ledger and projection lineage"
            ),
        ),
    )

if _entity_mechanism_paths_table is None:
    _entity_mechanism_paths_table = Table(
        "entity_mechanism_paths",
        Base.metadata,
        Column(
            "path_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("reasoning_paths.id"),
                ondelete="CASCADE",
            ),
            primary_key=True,
            nullable=False,
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "seed_entity_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "end_entity_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "relation_type",
            String(64),
            nullable=False,
        ),
        Column(
            "path_length",
            Integer,
            nullable=False,
        ),
        Column(
            "confidence",
            Float,
            nullable=False,
        ),
        Column(
            "supporting_claim_ids",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
        Column(
            "path_updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
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
        **graph_table_options(
            comment=(
                "Derived per-seed mechanism path candidates rebuilt from "
                "persisted reasoning paths"
            ),
        ),
    )

_entity_neighbors_table_model_table = require_table(_entity_neighbors_table)

class GraphEntityNeighborModel(Base):
    """Derived one-hop adjacency row for one entity-visible relation."""


    __table__ = _entity_neighbors_table_model_table

    if TYPE_CHECKING:
        entity_id: Mapped[UUID]
        relation_id: Mapped[UUID]
        research_space_id: Mapped[UUID]
        neighbor_entity_id: Mapped[UUID]
        relation_type: Mapped[str]
        direction: Mapped[str]
        relation_updated_at: Mapped[datetime]
        created_at: Mapped[datetime]
        updated_at: Mapped[datetime]


_entity_claim_summary_table_model_table = require_table(_entity_claim_summary_table)

class GraphEntityClaimSummaryModel(Base):
    """Derived claim summary row for one entity."""


    __table__ = _entity_claim_summary_table_model_table

    if TYPE_CHECKING:
        entity_id: Mapped[UUID]
        research_space_id: Mapped[UUID]
        total_claim_count: Mapped[int]
        support_claim_count: Mapped[int]
        resolved_claim_count: Mapped[int]
        open_claim_count: Mapped[int]
        linked_claim_count: Mapped[int]
        projected_claim_count: Mapped[int]
        last_claim_activity_at: Mapped[datetime | None]
        created_at: Mapped[datetime]
        updated_at: Mapped[datetime]


_entity_relation_summary_table_model_table = require_table(_entity_relation_summary_table)

class GraphEntityRelationSummaryModel(Base):
    """Derived relation summary row for one entity."""


    __table__ = _entity_relation_summary_table_model_table

    if TYPE_CHECKING:
        entity_id: Mapped[UUID]
        research_space_id: Mapped[UUID]
        outgoing_relation_count: Mapped[int]
        incoming_relation_count: Mapped[int]
        total_relation_count: Mapped[int]
        distinct_relation_type_count: Mapped[int]
        support_claim_count: Mapped[int]
        last_projection_at: Mapped[datetime | None]
        created_at: Mapped[datetime]
        updated_at: Mapped[datetime]


_entity_mechanism_paths_table_model_table = require_table(_entity_mechanism_paths_table)

class GraphEntityMechanismPathModel(Base):
    """Derived mechanism-path candidate row for one seed entity."""


    __table__ = _entity_mechanism_paths_table_model_table

    if TYPE_CHECKING:
        path_id: Mapped[UUID]
        research_space_id: Mapped[UUID]
        seed_entity_id: Mapped[UUID]
        end_entity_id: Mapped[UUID]
        relation_type: Mapped[str]
        path_length: Mapped[int]
        confidence: Mapped[float]
        supporting_claim_ids: Mapped[list[str]]
        path_updated_at: Mapped[datetime]
        created_at: Mapped[datetime]
        updated_at: Mapped[datetime]


EntityClaimSummaryModel = GraphEntityClaimSummaryModel
EntityMechanismPathModel = GraphEntityMechanismPathModel
EntityRelationSummaryModel = GraphEntityRelationSummaryModel
EntityNeighborModel = GraphEntityNeighborModel

__all__ = [
    "EntityClaimSummaryModel",
    "EntityMechanismPathModel",
    "EntityNeighborModel",
    "EntityRelationSummaryModel",
]
