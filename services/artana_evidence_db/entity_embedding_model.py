"""Service-local ORM model for entity embeddings."""

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
from artana_evidence_db.vector_embedding_type import VectorEmbedding
from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID


def _existing_table(table_name: str) -> Table | None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        return table
    return Base.metadata.tables.get(qualify_graph_table_name(table_name))


if TYPE_CHECKING:
    from sqlalchemy.orm import Mapped
_entity_embeddings_table = _existing_table("entity_embeddings")
if _entity_embeddings_table is None:
    _entity_embeddings_table = Table(
        "entity_embeddings",
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
            "entity_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("entities.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column(
            "embedding",
            VectorEmbedding(1536),
            nullable=False,
            doc="pgvector embedding for graph entity similarity and link prediction",
        ),
        Column(
            "embedding_model",
            String(100),
            nullable=False,
        ),
        Column(
            "embedding_version",
            Integer,
            nullable=False,
            server_default="1",
        ),
        Column(
            "source_fingerprint",
            String(64),
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
        UniqueConstraint("entity_id", name="uq_entity_embeddings_entity_id"),
        UniqueConstraint(
            "research_space_id",
            "entity_id",
            name="uq_entity_embeddings_space_entity",
        ),
        Index("idx_entity_embeddings_space", "research_space_id"),
        Index("idx_entity_embeddings_entity", "entity_id"),
        **graph_table_options(
            comment="Entity-level embeddings for hybrid graph + vector workflows",
        ),
    )

_entity_embeddings_table_model_table = require_table(_entity_embeddings_table)

class GraphEntityEmbeddingModel(Base):
    """Embedding vectors for graph entities used by hybrid retrieval."""


    __table__ = _entity_embeddings_table_model_table

    if TYPE_CHECKING:
        id: Mapped[UUID]
        research_space_id: Mapped[UUID]
        entity_id: Mapped[UUID]
        embedding: Mapped[list[float]]
        embedding_model: Mapped[str]
        embedding_version: Mapped[int]
        source_fingerprint: Mapped[str]
        created_at: Mapped[datetime]
        updated_at: Mapped[datetime]


EntityEmbeddingModel = GraphEntityEmbeddingModel

__all__ = ["EntityEmbeddingModel"]
