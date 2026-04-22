"""Service-local ORM models for derived reasoning paths."""

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
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID


def _existing_table(table_name: str) -> Table | None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        return table
    return Base.metadata.tables.get(qualify_graph_table_name(table_name))


_reasoning_paths_table = _existing_table("reasoning_paths")
if _reasoning_paths_table is None:
    _reasoning_paths_table = Table(
        "reasoning_paths",
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
            "path_kind",
            String(32),
            nullable=False,
            server_default="MECHANISM",
        ),
        Column(
            "status",
            String(16),
            nullable=False,
            server_default="ACTIVE",
        ),
        Column("start_entity_id", PGUUID(as_uuid=True), nullable=False),
        Column("end_entity_id", PGUUID(as_uuid=True), nullable=False),
        Column("root_claim_id", PGUUID(as_uuid=True), nullable=False),
        Column("path_length", Integer, nullable=False),
        Column("confidence", Float, nullable=False, server_default="0.0"),
        Column("path_signature_hash", String(128), nullable=False),
        Column("generated_by", String(255), nullable=True),
        Column(
            "generated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
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
        CheckConstraint(
            "path_kind IN ('MECHANISM')",
            name="ck_reasoning_paths_kind",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'STALE')",
            name="ck_reasoning_paths_status",
        ),
        CheckConstraint(
            "path_length >= 1 AND path_length <= 32",
            name="ck_reasoning_paths_length",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_reasoning_paths_confidence",
        ),
        ForeignKeyConstraint(
            ["start_entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_reasoning_paths_start_entity_space",
        ),
        ForeignKeyConstraint(
            ["end_entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_reasoning_paths_end_entity_space",
        ),
        ForeignKeyConstraint(
            ["root_claim_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("relation_claims.id"),
                qualify_graph_foreign_key_target("relation_claims.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_reasoning_paths_root_claim_space",
        ),
        UniqueConstraint(
            "research_space_id",
            "path_kind",
            "path_signature_hash",
            name="uq_reasoning_paths_space_signature",
        ),
        Index(
            "idx_reasoning_paths_space_status",
            "research_space_id",
            "status",
        ),
        Index(
            "idx_reasoning_paths_space_start_end",
            "research_space_id",
            "start_entity_id",
            "end_entity_id",
        ),
        **graph_table_options(
            comment="Derived reasoning paths rebuilt from grounded support-claim chains",
        ),
    )


class GraphReasoningPathModel(Base):
    """Derived reasoning path materialized from grounded claim chains."""

    __table__ = _reasoning_paths_table


ReasoningPathModel = GraphReasoningPathModel

_reasoning_path_steps_table = _existing_table("reasoning_path_steps")
if _reasoning_path_steps_table is None:
    _reasoning_path_steps_table = Table(
        "reasoning_path_steps",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        Column(
            "path_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("reasoning_paths.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column("step_index", Integer, nullable=False),
        Column(
            "source_claim_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("relation_claims.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column(
            "target_claim_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("relation_claims.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column(
            "claim_relation_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("claim_relations.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column(
            "canonical_relation_id",
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
            "step_index >= 0 AND step_index <= 255",
            name="ck_reasoning_path_steps_index",
        ),
        UniqueConstraint(
            "path_id",
            "step_index",
            name="uq_reasoning_path_steps_order",
        ),
        Index("idx_reasoning_path_steps_path", "path_id"),
        Index("idx_reasoning_path_steps_source_claim", "source_claim_id"),
        Index("idx_reasoning_path_steps_target_claim", "target_claim_id"),
        Index("idx_reasoning_path_steps_claim_relation", "claim_relation_id"),
        **graph_table_options(
            comment="Ordered claim-to-claim edges explaining one reasoning path",
        ),
    )


class GraphReasoningPathStepModel(Base):
    """Ordered step rows explaining one derived reasoning path."""

    __table__ = _reasoning_path_steps_table


ReasoningPathStepModel = GraphReasoningPathStepModel

__all__ = [
    "ReasoningPathModel",
    "ReasoningPathStepModel",
]
