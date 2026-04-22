"""Service-local ORM models for entity identifiers and aliases."""

from __future__ import annotations

from datetime import UTC, datetime

from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
    qualify_graph_table_name,
)
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID

_ACTIVE_VALIDITY_CHECK = (
    "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))"
)
_REVIEW_STATUS_CHECK = "review_status IN ('ACTIVE', 'PENDING_REVIEW', 'REVOKED')"


def _existing_table(table_name: str) -> Table | None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        return table
    return Base.metadata.tables.get(qualify_graph_table_name(table_name))


_entity_identifiers_table = _existing_table("entity_identifiers")
if _entity_identifiers_table is None:
    _entity_identifiers_table = Table(
        "entity_identifiers",
        Base.metadata,
        Column(
            "id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
        Column(
            "entity_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("entities.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
            doc="Owning entity",
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
            doc="Owning research space for deterministic uniqueness guarantees",
        ),
        Column(
            "namespace",
            String(64),
            nullable=False,
            doc="Identifier namespace: MRN, HGNC, DOI, HPOID",
        ),
        Column(
            "identifier_value",
            String(512),
            nullable=False,
            doc="Identifier value (encrypted if PHI)",
        ),
        Column(
            "identifier_blind_index",
            String(64),
            nullable=True,
            doc="Deterministic blind index for encrypted PHI equality lookup",
        ),
        Column(
            "encryption_key_version",
            String(32),
            nullable=True,
            doc="Key version used to encrypt identifier_value",
        ),
        Column(
            "blind_index_version",
            String(32),
            nullable=True,
            doc="Key version used to generate identifier_blind_index",
        ),
        Column(
            "identifier_normalized",
            String(512),
            nullable=True,
            doc="Deterministic exact-match key for non-PHI identifier values",
        ),
        Column(
            "sensitivity",
            String(32),
            nullable=False,
            server_default="INTERNAL",
            doc="Sensitivity level: PUBLIC, INTERNAL, PHI",
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
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
        **graph_table_options(
            comment="PHI-isolated entity identifiers for secure lookup",
        ),
    )


class GraphEntityIdentifierModel(Base):
    """Entity identifiers isolated for PHI protection."""

    __table__ = _entity_identifiers_table


EntityIdentifierModel = GraphEntityIdentifierModel

_entity_aliases_table = _existing_table("entity_aliases")
if _entity_aliases_table is None:
    _entity_aliases_table = Table(
        "entity_aliases",
        Base.metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
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
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
        ),
        Column(
            "entity_type",
            String(64),
            ForeignKey(qualify_graph_foreign_key_target("dictionary_entity_types.id")),
            nullable=False,
        ),
        Column("alias_label", String(512), nullable=False),
        Column("alias_normalized", String(512), nullable=False),
        Column("source", String(64), nullable=True),
        Column(
            "created_by",
            String(128),
            nullable=False,
            server_default="system",
        ),
        Column("source_ref", String(1024), nullable=True),
        Column(
            "review_status",
            String(32),
            nullable=False,
            server_default="ACTIVE",
        ),
        Column("reviewed_by", String(128), nullable=True),
        Column("reviewed_at", TIMESTAMP(timezone=True), nullable=True),
        Column("revocation_reason", Text, nullable=True),
        Column(
            "is_active",
            Boolean,
            nullable=False,
            server_default=true(),
        ),
        Column(
            "valid_from",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column("valid_to", TIMESTAMP(timezone=True), nullable=True),
        Column(
            "superseded_by",
            Integer,
            ForeignKey(
                qualify_graph_foreign_key_target("entity_aliases.id"),
                ondelete="SET NULL",
            ),
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
        **graph_table_options(
            comment="Normalized aliases for deterministic entity resolution",
        ),
    )


class GraphEntityAliasModel(Base):
    """Normalized aliases attached to kernel entities."""

    __table__ = _entity_aliases_table


EntityAliasModel = GraphEntityAliasModel

__all__ = [
    "EntityAliasModel",
    "EntityIdentifierModel",
]
