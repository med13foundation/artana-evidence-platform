"""Service-local graph entity ORM models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from sqlalchemy import Column, ForeignKey, Index, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID

_entities_table = Base.metadata.tables.get("entities")
if _entities_table is None:
    _entities_table = Table(
        "entities",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
            doc="Unique entity identifier",
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
            doc="Owning research space",
        ),
        Column(
            "entity_type",
            String(64),
            ForeignKey(qualify_graph_foreign_key_target("dictionary_entity_types.id")),
            nullable=False,
            index=True,
            doc="Entity type, e.g. GENE, VARIANT, PATIENT",
        ),
        Column(
            "display_label",
            String(512),
            nullable=True,
            doc="Human-readable label",
        ),
        Column(
            "display_label_normalized",
            String(512),
            nullable=True,
            doc="Deterministic exact-match key for the canonical display label",
        ),
        Column(
            "metadata_payload",
            JSONB,
            nullable=False,
            server_default="{}",
            doc="Sparse, low-velocity metadata only",
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
            name="uq_entities_id_space",
        ),
        Index("idx_entities_space_type", "research_space_id", "entity_type"),
        Index("idx_entities_created_at", "created_at"),
        Index(
            "idx_entities_space_type_label_normalized",
            "research_space_id",
            "entity_type",
            "display_label_normalized",
        ),
        **graph_table_options(
            comment="Generic graph nodes (entities) for all domain types",
        ),
    )


class GraphEntityModel(Base):
    """A generic graph node."""

    __table__ = _entities_table

    def __repr__(self) -> str:
        return (
            f"<EntityModel(id={self.id}, type={self.entity_type}, "
            f"label={self.display_label})>"
        )


EntityModel = GraphEntityModel

__all__ = ["EntityModel"]
