"""Claim participant model for structured claim endpoint linkage."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    text,
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


class ClaimParticipantModel(Base):
    """N-ary participant rows linked to relation claims."""

    __tablename__ = "claim_participants"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    qualifiers: Mapped[JSONObject] = mapped_column(
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
            "role IN ('SUBJECT', 'OBJECT', 'CONTEXT', 'QUALIFIER', 'MODIFIER', 'OUTCOME')",
            name="ck_claim_participants_role",
        ),
        CheckConstraint(
            "label IS NOT NULL OR entity_id IS NOT NULL",
            name="ck_claim_participants_anchor",
        ),
        ForeignKeyConstraint(
            ["claim_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("relation_claims.id"),
                qualify_graph_foreign_key_target("relation_claims.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_claim_participants_claim_space",
        ),
        ForeignKeyConstraint(
            ["entity_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("entities.id"),
                qualify_graph_foreign_key_target("entities.research_space_id"),
            ],
            ondelete="RESTRICT",
            name="fk_claim_participants_entity_space",
        ),
        Index("idx_claim_participants_claim", "claim_id"),
        Index(
            "idx_claim_participants_space_entity",
            "research_space_id",
            "entity_id",
            postgresql_where=text("entity_id IS NOT NULL"),
        ),
        Index("idx_claim_participants_space_role", "research_space_id", "role"),
        graph_table_options(
            comment="Structured claim participants with role semantics",
        ),
    )


__all__ = ["ClaimParticipantModel"]
