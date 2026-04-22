"""Database models for derived reasoning paths."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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


class ReasoningPathModel(Base):
    """Derived reasoning path materialized from grounded claim chains."""

    __tablename__ = "reasoning_paths"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    path_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="MECHANISM",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="ACTIVE",
    )
    start_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    end_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    root_claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    path_length: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, server_default="0.0")
    path_signature_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    generated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
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
        graph_table_options(
            comment="Derived reasoning paths rebuilt from grounded support-claim chains",
        ),
    )


class ReasoningPathStepModel(Base):
    """Ordered step rows explaining one derived reasoning path."""

    __tablename__ = "reasoning_path_steps"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    path_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("reasoning_paths.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_claim_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("relation_claims.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    target_claim_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("relation_claims.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    claim_relation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("claim_relations.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    canonical_relation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("relations.id"),
            ondelete="SET NULL",
        ),
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
        graph_table_options(
            comment="Ordered claim-to-claim edges explaining one reasoning path",
        ),
    )


__all__ = ["ReasoningPathModel", "ReasoningPathStepModel"]
