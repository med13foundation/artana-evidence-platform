"""
Entity models — the graph nodes.

Replaces the old GeneModel, VariantModel, PhenotypeModel, etc.
with a single generic entity table + identifier isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from src.models.database.base import Base
from src.models.database.types import VectorEmbedding
from src.type_definitions.common import JSONObject  # noqa: TC001

_ACTIVE_VALIDITY_CHECK = (
    "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))"
)
_REVIEW_STATUS_CHECK = "review_status IN ('ACTIVE', 'PENDING_REVIEW', 'REVOKED')"


class EntityModel(Base):
    """
    A generic graph node.

    Represents any typed entity: GENE, VARIANT, PHENOTYPE, DRUG,
    PATHWAY, MECHANISM, PUBLICATION, PATIENT, etc.

    No PHI or high-volume data lives here — only stable metadata.
    """

    __tablename__ = "entities"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique entity identifier",
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        doc="Owning research space",
    )
    entity_type: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_entity_types.id")),
        nullable=False,
        index=True,
        doc="Entity type, e.g. GENE, VARIANT, PATIENT",
    )
    display_label: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        doc="Human-readable label",
    )
    display_label_normalized: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        doc="Deterministic exact-match key for the canonical display label",
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc="Sparse, low-velocity metadata only",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
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
        graph_table_options(
            comment="Generic graph nodes (entities) for all domain types",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<EntityModel(id={self.id}, type={self.entity_type}, "
            f"label={self.display_label})>"
        )


class EntityIdentifierModel(Base):
    """
    Entity identifiers — isolated for PHI protection.

    Stores lookup keys (MRN, HGNC, DOI, HPO ID, etc.) separately
    from the entity itself. PHI identifiers are encrypted at rest
    and protected by RLS.
    """

    __tablename__ = "entity_identifiers"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("entities.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        doc="Owning entity",
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        doc="Owning research space for deterministic uniqueness guarantees",
    )
    namespace: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Identifier namespace: MRN, HGNC, DOI, HPOID",
    )
    identifier_value: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        doc="Identifier value (encrypted if PHI)",
    )
    identifier_blind_index: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Deterministic blind index for encrypted PHI equality lookup",
    )
    encryption_key_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Key version used to encrypt identifier_value",
    )
    blind_index_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Key version used to generate identifier_blind_index",
    )
    identifier_normalized: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        doc="Deterministic exact-match key for non-PHI identifier values",
    )
    sensitivity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="INTERNAL",
        doc="Sensitivity level: PUBLIC, INTERNAL, PHI",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index(
            "idx_identifier_lookup",
            "namespace",
            "identifier_value",
        ),
        Index(
            "idx_identifier_space_ns_normalized",
            "research_space_id",
            "namespace",
            "identifier_normalized",
        ),
        Index(
            "idx_identifier_blind_lookup",
            "research_space_id",
            "namespace",
            "identifier_blind_index",
        ),
        Index(
            "idx_identifier_entity_ns_unique",
            "entity_id",
            "namespace",
            "identifier_value",
            unique=True,
        ),
        Index(
            "idx_identifier_entity_ns_blind_unique",
            "entity_id",
            "namespace",
            "identifier_blind_index",
            unique=True,
        ),
        Index(
            "uq_identifier_space_ns_normalized",
            "research_space_id",
            "namespace",
            "identifier_normalized",
            unique=True,
            postgresql_where=text(
                "identifier_normalized IS NOT NULL AND sensitivity <> 'PHI'",
            ),
            sqlite_where=text(
                "identifier_normalized IS NOT NULL AND sensitivity <> 'PHI'",
            ),
        ),
        Index(
            "uq_identifier_space_ns_blind",
            "research_space_id",
            "namespace",
            "identifier_blind_index",
            unique=True,
            postgresql_where=text("identifier_blind_index IS NOT NULL"),
            sqlite_where=text("identifier_blind_index IS NOT NULL"),
        ),
        graph_table_options(
            comment="PHI-isolated entity identifiers for secure lookup",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<EntityIdentifierModel(entity={self.entity_id}, "
            f"ns={self.namespace}, val={self.identifier_value})>"
        )


class EntityAliasModel(Base):
    """Normalized aliases attached to kernel entities."""

    __tablename__ = "entity_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("entities.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_entity_types.id")),
        nullable=False,
    )
    alias_label: Mapped[str] = mapped_column(String(512), nullable=False)
    alias_normalized: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="system",
    )
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    valid_to: Mapped[datetime | None] = mapped_column(nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            qualify_graph_foreign_key_target("entity_aliases.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            _ACTIVE_VALIDITY_CHECK,
            name="ck_entity_aliases_active_validity",
        ),
        CheckConstraint(
            _REVIEW_STATUS_CHECK,
            name="ck_entity_aliases_review_status",
        ),
        Index("idx_entity_aliases_entity_active", "entity_id", "is_active"),
        Index(
            "idx_entity_aliases_space_type_normalized",
            "research_space_id",
            "entity_type",
            "alias_normalized",
        ),
        Index(
            "uq_entity_aliases_active_alias_scope",
            "research_space_id",
            "entity_type",
            "alias_normalized",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
        graph_table_options(
            comment="Normalized aliases for deterministic entity resolution",
        ),
    )


class EntityEmbeddingModel(Base):
    """Embedding vectors for kernel entities used by hybrid graph retrieval."""

    __tablename__ = "entity_embeddings"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("entities.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(
        VectorEmbedding(1536),
        nullable=False,
        doc="pgvector embedding for kernel entity similarity and link prediction",
    )
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    embedding_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )
    source_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("entity_id", name="uq_entity_embeddings_entity_id"),
        UniqueConstraint(
            "research_space_id",
            "entity_id",
            name="uq_entity_embeddings_space_entity",
        ),
        Index("idx_entity_embeddings_space", "research_space_id"),
        Index("idx_entity_embeddings_entity", "entity_id"),
        graph_table_options(
            comment="Entity-level embeddings for hybrid graph + vector workflows",
        ),
    )
