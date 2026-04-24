"""Service-local graph entity ORM models."""

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
from sqlalchemy import Column, ForeignKey, Index, String, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Mapped
_entities_table = Base.metadata.tables.get(qualify_graph_table_name("entities"))
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

_entities_table_model_table = require_table(_entities_table)

class GraphEntityModel(Base):
    """A generic graph node."""


    __table__ = _entities_table_model_table

    if TYPE_CHECKING:
        id: Mapped[UUID]
        research_space_id: Mapped[UUID]
        entity_type: Mapped[str]
        display_label: Mapped[str | None]
        display_label_normalized: Mapped[str | None]
        metadata_payload: Mapped[JSONObject]
        created_at: Mapped[datetime]
        updated_at: Mapped[datetime]

    def __repr__(self) -> str:
        return (
            f"<EntityModel(id={self.id}, type={self.entity_type}, "
            f"label={self.display_label})>"
        )


EntityModel = GraphEntityModel

__all__ = ["EntityModel"]
