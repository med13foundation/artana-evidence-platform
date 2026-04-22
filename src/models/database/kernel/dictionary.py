"""
Kernel Dictionary Models — Layer 1 (The Rules).

These tables define what is allowed in the system. No data enters
unless it maps to a definition here.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from src.models.database.base import Base
from src.models.database.types import VectorEmbedding
from src.type_definitions.common import JSONObject, JSONValue  # noqa: TC001


class DictionaryDataTypeModel(Base):
    """Reference table for allowed variable data types."""

    __tablename__ = "dictionary_data_types"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        doc="Data type ID, e.g. STRING, FLOAT, DATE",
    )
    display_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Human-readable label for the data type",
    )
    python_type_hint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Python type hint for this data type",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional semantic description for this data type",
    )
    constraint_schema: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc="JSON schema defining supported constraints for this data type",
    )

    __table_args__ = (graph_table_options(comment="First-class dictionary data types"),)


class DictionaryDomainContextModel(Base):
    """Reference table for dictionary domain contexts."""

    __tablename__ = "dictionary_domain_contexts"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Domain context ID, e.g. genomics, clinical, sports",
    )
    display_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Human-readable domain label",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional description of the domain context",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement domain context identifier when superseded",
    )

    __table_args__ = (
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_dictionary_domain_contexts_active_validity",
        ),
        graph_table_options(comment="First-class dictionary domain contexts"),
    )


class DictionarySensitivityLevelModel(Base):
    """Reference table for sensitivity classifications."""

    __tablename__ = "dictionary_sensitivity_levels"

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        doc="Sensitivity ID, e.g. PUBLIC, INTERNAL, PHI",
    )
    display_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Human-readable sensitivity label",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional handling guidance for this sensitivity level",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement sensitivity identifier when superseded",
    )

    __table_args__ = (
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_dictionary_sensitivity_levels_active_validity",
        ),
        graph_table_options(comment="First-class dictionary sensitivity levels"),
    )


class DictionaryEntityTypeModel(Base):
    """Reference table for first-class entity types."""

    __tablename__ = "dictionary_entity_types"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Entity type ID, e.g. GENE, VARIANT",
    )
    display_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Human-readable entity type label",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Semantic description of this entity type",
    )
    domain_context: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_domain_contexts.id")),
        nullable=False,
        index=True,
        doc="Domain context for this entity type",
    )
    external_ontology_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Optional external ontology URI or identifier",
    )
    expected_properties: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc="Expected properties schema for entity metadata",
    )
    description_embedding: Mapped[list[float] | None] = mapped_column(
        VectorEmbedding(1536),
        nullable=True,
        doc="pgvector embedding for semantic search over entity-type descriptions",
    )
    embedded_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when description_embedding was last computed",
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Embedding model used to compute description_embedding",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement entity type identifier when superseded",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )

    __table_args__ = (
        Index("idx_enttype_domain", "domain_context"),
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_dictionary_entity_types_active_validity",
        ),
        graph_table_options(
            comment="First-class entity types with semantic metadata",
        ),
    )


class DictionaryRelationTypeModel(Base):
    """Reference table for first-class relation types."""

    __tablename__ = "dictionary_relation_types"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Relation type ID, e.g. ASSOCIATED_WITH, CAUSES",
    )
    display_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Human-readable relation type label",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Semantic description of this relation type",
    )
    domain_context: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_domain_contexts.id")),
        nullable=False,
        index=True,
        doc="Domain context for this relation type",
    )
    is_directional: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Whether A->B differs semantically from B->A",
    )
    inverse_label: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Optional label for the inverse direction",
    )
    description_embedding: Mapped[list[float] | None] = mapped_column(
        VectorEmbedding(1536),
        nullable=True,
        doc="pgvector embedding for semantic search over relation-type descriptions",
    )
    embedded_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when description_embedding was last computed",
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Embedding model used to compute description_embedding",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement relation type identifier when superseded",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )

    __table_args__ = (
        Index("idx_reltype_domain", "domain_context"),
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_dictionary_relation_types_active_validity",
        ),
        graph_table_options(
            comment="First-class relation types with semantic metadata",
        ),
    )


class DictionaryRelationSynonymModel(Base):
    """Reference table for relation-type synonyms."""

    __tablename__ = "dictionary_relation_synonyms"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            qualify_graph_foreign_key_target("dictionary_relation_types.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        doc="Canonical relation type ID this synonym resolves to",
    )
    synonym: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Normalized synonym label, e.g. DRIVES",
    )
    source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Optional source of this synonym mapping",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement relation type identifier when superseded",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_rel_syn_relation_type", "relation_type"),
        Index(
            "uq_relation_synonyms_active_synonym",
            func.lower(synonym),
            unique=True,
            postgresql_where=text("is_active"),
        ),
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_dictionary_relation_synonyms_active_validity",
        ),
        graph_table_options(
            comment="Synonym labels that resolve to canonical relation types",
        ),
    )


class ValueSetModel(Base):
    """Enumeration set for values of a single CODED variable."""

    __tablename__ = "value_sets"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Value set ID, e.g. VS_CLINVAR_CLASS",
    )
    variable_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="Variable this value set belongs to",
    )
    variable_data_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="CODED",
        doc="Mirrors variable_definitions.data_type and must be CODED",
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Human-readable value set name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="What the value set represents",
    )
    external_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Optional external ontology/standard reference",
    )
    is_extensible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=false(),
        doc="Whether agents may add new items automatically",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["variable_id", "variable_data_type"],
            [
                qualify_graph_foreign_key_target("variable_definitions.id"),
                qualify_graph_foreign_key_target("variable_definitions.data_type"),
            ],
            name="fk_value_sets_variable_coded",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "variable_data_type = 'CODED'",
            name="value_sets_variable_data_type_coded",
        ),
        graph_table_options(comment="Enumerated value sets for CODED variables"),
    )


class ValueSetItemModel(Base):
    """Allowed canonical code entries for a dictionary value set."""

    __tablename__ = "value_set_items"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    value_set_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            qualify_graph_foreign_key_target("value_sets.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
        doc="Parent value set ID",
    )
    code: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Canonical code persisted in observations",
    )
    display_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable label for this code",
    )
    synonyms: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        doc="Alternative strings that map to this code",
    )
    external_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Optional external code reference",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        doc="Display ordering within the value set",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )

    __table_args__ = (
        Index(
            "idx_value_set_item_unique_code",
            "value_set_id",
            "code",
            unique=True,
        ),
        graph_table_options(
            comment="Allowed canonical codes and synonyms per value set",
        ),
    )


class VariableDefinitionModel(Base):
    """
    The Vocabulary — defines every allowed data element.

    Examples: systolic_bp, gene_symbol, algorithm_accuracy
    """

    __tablename__ = "variable_definitions"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Variable identifier, e.g. VAR_SYSTOLIC_BP",
    )
    canonical_name: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        doc="Snake-case canonical name, e.g. systolic_bp",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable display name",
    )
    data_type: Mapped[str] = mapped_column(
        String(32),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_data_types.id")),
        nullable=False,
        doc="Data type: INTEGER, FLOAT, STRING, DATE, CODED, BOOLEAN, JSON",
    )
    preferred_unit: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="UCUM-standard preferred unit, e.g. mmHg",
    )
    constraints: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc='Validation constraints, e.g. {"min": 0, "max": 300}',
    )
    domain_context: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_domain_contexts.id")),
        nullable=False,
        server_default="general",
        index=True,
        doc="Domain: clinical, genomics, cs_benchmarking, general",
    )
    sensitivity: Mapped[str] = mapped_column(
        String(32),
        ForeignKey(
            qualify_graph_foreign_key_target("dictionary_sensitivity_levels.id"),
        ),
        nullable=False,
        server_default="INTERNAL",
        doc="Sensitivity: PUBLIC, INTERNAL, PHI",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional longer description",
    )
    description_embedding: Mapped[list[float] | None] = mapped_column(
        VectorEmbedding(1536),
        nullable=True,
        doc="pgvector embedding for semantic search over variable descriptions",
    )
    embedded_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when description_embedding was last computed",
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Embedding model used to compute description_embedding",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement variable identifier when superseded",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )

    __table_args__ = (
        Index("idx_vardef_domain", "domain_context"),
        Index("idx_vardef_data_type", "data_type"),
        UniqueConstraint("id", "data_type", name="uq_vardef_id_data_type"),
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_variable_definitions_active_validity",
        ),
        graph_table_options(comment="Master dictionary of allowed data variables"),
    )


class VariableSynonymModel(Base):
    """
    Synonym table for fuzzy field-name mapping.

    Allows deterministic mapping before falling back to
    vector or LLM-based mapping.
    """

    __tablename__ = "variable_synonyms"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    variable_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            qualify_graph_foreign_key_target("variable_definitions.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
        doc="FK to variable_definitions.id",
    )
    synonym: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Alternative name for the variable",
    )
    source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Source of synonym: manual, ai_mapped",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement synonym identifier when superseded",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )

    __table_args__ = (
        Index(
            "uq_variable_synonyms_active_synonym",
            text("lower(synonym)"),
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
        Index(
            "idx_synonym_variable_unique",
            "variable_id",
            "synonym",
            unique=True,
        ),
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_variable_synonyms_active_validity",
        ),
        graph_table_options(comment="Synonyms for deterministic field-name matching"),
    )


class TransformRegistryModel(Base):
    """
    Safe unit/format transformations.

    Each transform references a pre-compiled function — no user-defined
    code is allowed.
    """

    __tablename__ = "transform_registry"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Transform ID, e.g. TR_LBS_KG",
    )
    input_unit: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Source unit",
    )
    output_unit: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Target unit",
    )
    category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="UNIT_CONVERSION",
        doc="Transform category: UNIT_CONVERSION, NORMALIZATION, DERIVATION",
    )
    input_data_type: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_data_types.id")),
        nullable=True,
        doc="Optional expected input kernel data type",
    )
    output_data_type: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_data_types.id")),
        nullable=True,
        doc="Optional output kernel data type",
    )
    implementation_ref: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Function reference, e.g. func:std_lib.convert.lbs_to_kg",
    )
    is_deterministic: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Whether transform is deterministic and side-effect free",
    )
    is_production_allowed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=false(),
        doc="Whether transform can be used by production normalization flows",
    )
    test_input: Mapped[JSONValue | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Verification input payload for runtime validation",
    )
    expected_output: Mapped[JSONValue | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Expected output payload for verification",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable transform description",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="ACTIVE or DEPRECATED",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement transform identifier when superseded",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )

    __table_args__ = (
        Index("idx_transform_units", "input_unit", "output_unit"),
        Index("idx_transform_category", "category"),
        Index("idx_transform_production", "is_production_allowed"),
        CheckConstraint(
            "category IN ('UNIT_CONVERSION', 'NORMALIZATION', 'DERIVATION')",
            name="ck_transform_registry_category",
        ),
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_transform_registry_active_validity",
        ),
        graph_table_options(
            comment="Registry of safe, pre-compiled unit conversions",
        ),
    )


class EntityResolutionPolicyModel(Base):
    """
    Deduplication policies per entity type.

    Controls how duplicate entities are detected and merged.
    """

    __tablename__ = "entity_resolution_policies"

    entity_type: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_entity_types.id")),
        primary_key=True,
        doc="Entity type, e.g. PATIENT, GENE, PAPER",
    )
    policy_strategy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Strategy: STRICT_MATCH, LOOKUP, FUZZY, NONE",
    )
    required_anchors: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        doc='Required identifiers for matching, e.g. ["mrn", "issuer"]',
    )
    auto_merge_threshold: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="1.0",
        doc="Similarity threshold for auto-merge (1.0 = exact only)",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement policy identifier when superseded",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )

    __table_args__ = (
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_entity_resolution_policies_active_validity",
        ),
        graph_table_options(comment="Entity deduplication policies by type"),
    )


class RelationConstraintModel(Base):
    """
    Allowed relationship types between entity types.

    Used by the triple validator to block invalid edges.
    """

    __tablename__ = "relation_constraints"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_entity_types.id")),
        nullable=False,
        doc="Source entity type, e.g. GENE",
    )
    relation_type: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_relation_types.id")),
        nullable=False,
        doc="Relation type, e.g. ASSOCIATED_WITH",
    )
    target_type: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_entity_types.id")),
        nullable=False,
        doc="Target entity type, e.g. DISEASE",
    )
    is_allowed: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        doc="Whether this edge type is permitted",
    )
    requires_evidence: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        doc="Whether an evidence reference is mandatory",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement constraint identifier when superseded",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )
    profile: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ALLOWED",
        doc="Governance profile: FORBIDDEN, EXPECTED, ALLOWED, or REVIEW_ONLY",
    )
    required_roles: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        server_default="[]",
        doc="Participant roles required for this constraint (e.g. ['SUBJECT', 'OBJECT'])",
    )
    domain_context: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Domain scope (e.g. 'genomics', 'clinical') limiting applicability",
    )
    qualifier_constraints: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        server_default="{}",
        doc="Required qualifier keys/value rules for this constraint",
    )
    min_evidence_tier: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Minimum evidence tier required (e.g. 'LITERATURE', 'EXPERIMENTAL')",
    )

    __table_args__ = (
        Index(
            "idx_relation_constraint_unique",
            "source_type",
            "relation_type",
            "target_type",
            unique=True,
        ),
        CheckConstraint(
            "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
            name="ck_relation_constraints_active_validity",
        ),
        graph_table_options(comment="Allowed triple patterns for graph edges"),
    )


class DictionaryChangelogModel(Base):
    """Immutable changelog entries for dictionary mutations."""

    __tablename__ = "dictionary_changelog"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    table_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Dictionary table name that changed",
    )
    record_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        doc="Primary identifier of the changed record",
    )
    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Mutation type: CREATE, UPDATE, REVOKE, MERGE",
    )
    before_snapshot: Mapped[JSONObject | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="JSON snapshot before mutation",
    )
    after_snapshot: Mapped[JSONObject | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="JSON snapshot after mutation",
    )
    changed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Actor responsible for the mutation",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference associated with the mutation",
    )

    __table_args__ = (
        Index("idx_dictionary_changelog_table_record", "table_name", "record_id"),
        graph_table_options(comment="Immutable audit log for dictionary mutations"),
    )
