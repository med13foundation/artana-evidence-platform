"""Service-local ORM model for graph-owned embedding readiness state."""

from __future__ import annotations

from datetime import UTC, datetime

from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
    qualify_graph_table_name,
)
from sqlalchemy import Column, ForeignKey, Index, Integer, String, Table
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID


def _existing_table(table_name: str) -> Table | None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        return table
    return Base.metadata.tables.get(qualify_graph_table_name(table_name))


_entity_embedding_status_table = _existing_table("entity_embedding_status")
if _entity_embedding_status_table is None:
    _entity_embedding_status_table = Table(
        "entity_embedding_status",
        Base.metadata,
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        Column(
            "entity_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("entities.id"),
                ondelete="CASCADE",
            ),
            primary_key=True,
            nullable=False,
        ),
        Column(
            "state",
            String(16),
            nullable=False,
        ),
        Column(
            "desired_fingerprint",
            String(64),
            nullable=False,
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
            "last_requested_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Column(
            "last_attempted_at",
            TIMESTAMP(timezone=True),
            nullable=True,
        ),
        Column(
            "last_refreshed_at",
            TIMESTAMP(timezone=True),
            nullable=True,
        ),
        Column(
            "last_error_code",
            String(64),
            nullable=True,
        ),
        Column(
            "last_error_message",
            String(2000),
            nullable=True,
        ),
        Index("idx_entity_embedding_status_space", "research_space_id"),
        Index("idx_entity_embedding_status_state", "state"),
        **graph_table_options(
            comment="Graph-owned readiness state for entity embedding projections",
        ),
    )


class GraphEntityEmbeddingStatusModel(Base):
    """Readiness state for graph-owned entity embedding projections."""

    __table__ = _entity_embedding_status_table


EntityEmbeddingStatusModel = GraphEntityEmbeddingStatusModel

__all__ = ["EntityEmbeddingStatusModel"]
