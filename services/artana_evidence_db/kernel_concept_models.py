"""Service-local graph concept-governance ORM models."""

from __future__ import annotations

from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID

_ACTIVE_VALIDITY_CHECK = (
    "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))"
)
_REVIEW_STATUS_CHECK = "review_status IN ('ACTIVE', 'PENDING_REVIEW', 'REVOKED')"

_concept_sets_table = Base.metadata.tables.get("concept_sets")
if _concept_sets_table is None:
    _concept_sets_table = Table(
        "concept_sets",
        Base.metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True),
        Column("research_space_id", PGUUID(as_uuid=True), nullable=False),
        Column("name", String(128), nullable=False),
        Column("slug", String(128), nullable=False),
        Column("description", Text, nullable=True),
        Column(
            "domain_context",
            String(64),
            ForeignKey(
                qualify_graph_foreign_key_target("dictionary_domain_contexts.id"),
            ),
            nullable=False,
        ),
        Column(
            "created_by",
            String(128),
            nullable=False,
            server_default="seed",
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
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_sets.id"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        UniqueConstraint(
            "research_space_id",
            "slug",
            name="uq_concept_sets_space_slug",
        ),
        UniqueConstraint("id", "research_space_id", name="uq_concept_sets_id_space"),
        CheckConstraint(_ACTIVE_VALIDITY_CHECK, name="ck_concept_sets_active_validity"),
        CheckConstraint(_REVIEW_STATUS_CHECK, name="ck_concept_sets_review_status"),
        CheckConstraint(
            "length(trim(slug)) > 0",
            name="ck_concept_sets_slug_non_empty",
        ),
        Index("idx_concept_sets_space_created_at", "research_space_id", "created_at"),
        Index("idx_concept_sets_space_active", "research_space_id", "is_active"),
        **graph_table_options(
            comment="Research-space scoped semantic concept sets",
        ),
    )

_concept_members_table = Base.metadata.tables.get("concept_members")
if _concept_members_table is None:
    _concept_members_table = Table(
        "concept_members",
        Base.metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True),
        Column(
            "concept_set_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_sets.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column("research_space_id", PGUUID(as_uuid=True), nullable=False),
        Column(
            "domain_context",
            String(64),
            ForeignKey(
                qualify_graph_foreign_key_target("dictionary_domain_contexts.id"),
            ),
            nullable=False,
        ),
        Column("dictionary_dimension", String(32), nullable=True),
        Column("dictionary_entry_id", String(128), nullable=True),
        Column("canonical_label", String(255), nullable=False),
        Column("normalized_label", String(255), nullable=False),
        Column(
            "sense_key",
            String(128),
            nullable=False,
            server_default="",
        ),
        Column(
            "is_provisional",
            Boolean,
            nullable=False,
            server_default=text("false"),
        ),
        Column(
            "metadata_payload",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
        Column(
            "created_by",
            String(128),
            nullable=False,
            server_default="seed",
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
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_members.id"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        UniqueConstraint("id", "research_space_id", name="uq_concept_members_id_space"),
        ForeignKeyConstraint(
            ["concept_set_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("concept_sets.id"),
                qualify_graph_foreign_key_target("concept_sets.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_concept_members_set_space_concept_sets",
        ),
        CheckConstraint(
            _ACTIVE_VALIDITY_CHECK,
            name="ck_concept_members_active_validity",
        ),
        CheckConstraint(_REVIEW_STATUS_CHECK, name="ck_concept_members_review_status"),
        CheckConstraint(
            "((dictionary_dimension IS NULL AND dictionary_entry_id IS NULL) OR "
            "(dictionary_dimension IS NOT NULL AND dictionary_entry_id IS NOT NULL))",
            name="ck_concept_members_dictionary_binding",
        ),
        CheckConstraint(
            "((NOT is_provisional) OR review_status = 'PENDING_REVIEW')",
            name="ck_concept_members_provisional_review_status",
        ),
        Index("idx_concept_members_set_active", "concept_set_id", "is_active"),
        Index(
            "idx_concept_members_space_domain",
            "research_space_id",
            "domain_context",
        ),
        Index(
            "uq_concept_members_active_dictionary_binding",
            "research_space_id",
            "dictionary_dimension",
            "dictionary_entry_id",
            unique=True,
            postgresql_where=text("is_active AND dictionary_entry_id IS NOT NULL"),
        ),
        Index(
            "uq_concept_members_active_provisional_identity",
            "research_space_id",
            "domain_context",
            "normalized_label",
            "sense_key",
            unique=True,
            postgresql_where=text("is_active AND dictionary_entry_id IS NULL"),
        ),
        **graph_table_options(
            comment="Canonical and provisional concept members per research space",
        ),
    )

_concept_aliases_table = Base.metadata.tables.get("concept_aliases")
if _concept_aliases_table is None:
    _concept_aliases_table = Table(
        "concept_aliases",
        Base.metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column(
            "concept_member_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_members.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column("research_space_id", PGUUID(as_uuid=True), nullable=False),
        Column(
            "domain_context",
            String(64),
            ForeignKey(
                qualify_graph_foreign_key_target("dictionary_domain_contexts.id"),
            ),
            nullable=False,
        ),
        Column("alias_label", String(255), nullable=False),
        Column("alias_normalized", String(255), nullable=False),
        Column("source", String(64), nullable=True),
        Column(
            "created_by",
            String(128),
            nullable=False,
            server_default="seed",
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
            ForeignKey(
                qualify_graph_foreign_key_target("concept_aliases.id"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        ForeignKeyConstraint(
            ["concept_member_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("concept_members.id"),
                qualify_graph_foreign_key_target("concept_members.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_concept_aliases_member_space_concept_members",
        ),
        CheckConstraint(
            _ACTIVE_VALIDITY_CHECK,
            name="ck_concept_aliases_active_validity",
        ),
        CheckConstraint(_REVIEW_STATUS_CHECK, name="ck_concept_aliases_review_status"),
        Index("idx_concept_aliases_member_active", "concept_member_id", "is_active"),
        Index(
            "idx_concept_aliases_space_domain",
            "research_space_id",
            "domain_context",
        ),
        Index(
            "uq_concept_aliases_active_alias_scope",
            "research_space_id",
            "domain_context",
            "alias_normalized",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        **graph_table_options(
            comment="Normalized aliases for concept-member resolution",
        ),
    )

_concept_links_table = Base.metadata.tables.get("concept_links")
if _concept_links_table is None:
    _concept_links_table = Table(
        "concept_links",
        Base.metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True),
        Column("research_space_id", PGUUID(as_uuid=True), nullable=False),
        Column(
            "source_member_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_members.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column(
            "target_member_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_members.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column("link_type", String(64), nullable=False),
        Column(
            "confidence",
            Float,
            nullable=False,
            server_default="1.0",
        ),
        Column(
            "metadata_payload",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
        Column(
            "created_by",
            String(128),
            nullable=False,
            server_default="seed",
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
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_links.id"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        UniqueConstraint("id", "research_space_id", name="uq_concept_links_id_space"),
        ForeignKeyConstraint(
            ["source_member_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("concept_members.id"),
                qualify_graph_foreign_key_target("concept_members.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_concept_links_source_member_space_concept_members",
        ),
        ForeignKeyConstraint(
            ["target_member_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("concept_members.id"),
                qualify_graph_foreign_key_target("concept_members.research_space_id"),
            ],
            ondelete="CASCADE",
            name="fk_concept_links_target_member_space_concept_members",
        ),
        CheckConstraint(
            _ACTIVE_VALIDITY_CHECK,
            name="ck_concept_links_active_validity",
        ),
        CheckConstraint(_REVIEW_STATUS_CHECK, name="ck_concept_links_review_status"),
        CheckConstraint(
            "source_member_id <> target_member_id",
            name="ck_concept_links_no_self_loop",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_concept_links_confidence_bounds",
        ),
        Index("idx_concept_links_space_type", "research_space_id", "link_type"),
        Index(
            "idx_concept_links_source_target",
            "source_member_id",
            "target_member_id",
        ),
        Index(
            "uq_concept_links_active_unique_edge",
            "research_space_id",
            "source_member_id",
            "link_type",
            "target_member_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        **graph_table_options(
            comment="Typed semantic links between concept members",
        ),
    )

_concept_policies_table = Base.metadata.tables.get("concept_policies")
if _concept_policies_table is None:
    _concept_policies_table = Table(
        "concept_policies",
        Base.metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True),
        Column("research_space_id", PGUUID(as_uuid=True), nullable=False),
        Column(
            "profile_name",
            String(64),
            nullable=False,
            server_default="default",
        ),
        Column("mode", String(16), nullable=False),
        Column(
            "minimum_edge_confidence",
            Float,
            nullable=False,
            server_default="0.6",
        ),
        Column(
            "minimum_distinct_documents",
            Integer,
            nullable=False,
            server_default="1",
        ),
        Column(
            "allow_generic_relations",
            Boolean,
            nullable=False,
            server_default=true(),
        ),
        Column("max_edges_per_document", Integer, nullable=True),
        Column(
            "policy_payload",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
        Column(
            "created_by",
            String(128),
            nullable=False,
            server_default="seed",
        ),
        Column("source_ref", String(1024), nullable=True),
        Column(
            "is_active",
            Boolean,
            nullable=False,
            server_default=true(),
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        UniqueConstraint(
            "research_space_id",
            "profile_name",
            name="uq_concept_policies_space_profile_name",
        ),
        CheckConstraint(
            "mode IN ('PRECISION', 'BALANCED', 'DISCOVERY')",
            name="ck_concept_policies_mode",
        ),
        CheckConstraint(
            "minimum_edge_confidence >= 0.0 AND minimum_edge_confidence <= 1.0",
            name="ck_concept_policies_minimum_edge_confidence",
        ),
        CheckConstraint(
            "minimum_distinct_documents >= 1",
            name="ck_concept_policies_minimum_distinct_documents",
        ),
        CheckConstraint(
            "(max_edges_per_document IS NULL OR max_edges_per_document >= 1)",
            name="ck_concept_policies_max_edges_per_document",
        ),
        Index(
            "idx_concept_policies_space_created_at",
            "research_space_id",
            "created_at",
        ),
        Index(
            "uq_concept_policies_active_space",
            "research_space_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        **graph_table_options(
            comment="Per-space concept governance policy profiles",
        ),
    )

_concept_decisions_table = Base.metadata.tables.get("concept_decisions")
if _concept_decisions_table is None:
    _concept_decisions_table = Table(
        "concept_decisions",
        Base.metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True),
        Column("research_space_id", PGUUID(as_uuid=True), nullable=False),
        Column(
            "concept_set_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_sets.id"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        Column(
            "concept_member_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_members.id"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        Column(
            "concept_link_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_links.id"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        Column("decision_type", String(32), nullable=False),
        Column("decision_status", String(32), nullable=False),
        Column("proposed_by", String(128), nullable=False),
        Column("decided_by", String(128), nullable=True),
        Column("confidence", Float, nullable=True),
        Column("rationale", Text, nullable=True),
        Column(
            "evidence_payload",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
        Column(
            "decision_payload",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
        Column("harness_outcome", String(32), nullable=True),
        Column("decided_at", TIMESTAMP(timezone=True), nullable=True),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        UniqueConstraint(
            "id",
            "research_space_id",
            name="uq_concept_decisions_id_space",
        ),
        ForeignKeyConstraint(
            ["concept_set_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("concept_sets.id"),
                qualify_graph_foreign_key_target("concept_sets.research_space_id"),
            ],
            ondelete="SET NULL",
            name="fk_concept_decisions_set_space_concept_sets",
        ),
        ForeignKeyConstraint(
            ["concept_member_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("concept_members.id"),
                qualify_graph_foreign_key_target("concept_members.research_space_id"),
            ],
            ondelete="SET NULL",
            name="fk_concept_decisions_member_space_concept_members",
        ),
        ForeignKeyConstraint(
            ["concept_link_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("concept_links.id"),
                qualify_graph_foreign_key_target("concept_links.research_space_id"),
            ],
            ondelete="SET NULL",
            name="fk_concept_decisions_link_space_concept_links",
        ),
        CheckConstraint(
            "decision_type IN ('CREATE', 'MAP', 'MERGE', 'SPLIT', 'LINK', 'PROMOTE', 'DEMOTE')",
            name="ck_concept_decisions_decision_type",
        ),
        CheckConstraint(
            "decision_status IN ('PROPOSED', 'NEEDS_REVIEW', 'APPROVED', 'REJECTED', 'APPLIED')",
            name="ck_concept_decisions_decision_status",
        ),
        CheckConstraint(
            "(harness_outcome IS NULL OR harness_outcome IN ('PASS', 'FAIL', 'NEEDS_REVIEW'))",
            name="ck_concept_decisions_harness_outcome",
        ),
        CheckConstraint(
            "(confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0))",
            name="ck_concept_decisions_confidence_bounds",
        ),
        CheckConstraint(
            "(concept_set_id IS NOT NULL OR concept_member_id IS NOT NULL OR concept_link_id IS NOT NULL)",
            name="ck_concept_decisions_subject_present",
        ),
        Index(
            "idx_concept_decisions_space_status",
            "research_space_id",
            "decision_status",
        ),
        Index(
            "idx_concept_decisions_space_created_at",
            "research_space_id",
            "created_at",
        ),
        **graph_table_options(
            comment="Decision ledger for concept governance operations",
        ),
    )

_concept_harness_results_table = Base.metadata.tables.get("concept_harness_results")
if _concept_harness_results_table is None:
    _concept_harness_results_table = Table(
        "concept_harness_results",
        Base.metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True),
        Column("research_space_id", PGUUID(as_uuid=True), nullable=False),
        Column(
            "decision_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("concept_decisions.id"),
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
        Column("harness_name", String(64), nullable=False),
        Column("harness_version", String(32), nullable=True),
        Column("run_id", String(255), nullable=True),
        Column("outcome", String(32), nullable=False),
        Column(
            "checks_payload",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
        Column(
            "errors_payload",
            JSONB,
            nullable=False,
            server_default="[]",
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
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        ForeignKeyConstraint(
            ["decision_id", "research_space_id"],
            [
                qualify_graph_foreign_key_target("concept_decisions.id"),
                qualify_graph_foreign_key_target("concept_decisions.research_space_id"),
            ],
            ondelete="SET NULL",
            name="fk_concept_harness_results_decision_space_concept_decisions",
        ),
        CheckConstraint(
            "outcome IN ('PASS', 'FAIL', 'NEEDS_REVIEW')",
            name="ck_concept_harness_results_outcome",
        ),
        Index(
            "idx_concept_harness_results_space_outcome",
            "research_space_id",
            "outcome",
        ),
        Index(
            "idx_concept_harness_results_decision_id",
            "decision_id",
        ),
        **graph_table_options(
            comment="Harness/audit outcomes attached to concept decisions",
        ),
    )


class GraphConceptSetModel(Base):
    """Research-space scoped container for concept members."""

    __table__ = _concept_sets_table


class GraphConceptMemberModel(Base):
    """Canonical or provisional concept in a concept set."""

    __table__ = _concept_members_table


class GraphConceptAliasModel(Base):
    """Normalized alias labels for concept members."""

    __table__ = _concept_aliases_table


class GraphConceptLinkModel(Base):
    """Typed relation between two concept members inside a research space."""

    __table__ = _concept_links_table


class GraphConceptPolicyModel(Base):
    """One active policy profile per research space."""

    __table__ = _concept_policies_table


class GraphConceptDecisionModel(Base):
    """Decision ledger rows for concept operations and governance actions."""

    __table__ = _concept_decisions_table


class GraphConceptHarnessResultModel(Base):
    """Audit trail for AI harness checks on concept decisions."""

    __table__ = _concept_harness_results_table


ConceptAliasModel = GraphConceptAliasModel
ConceptDecisionModel = GraphConceptDecisionModel
ConceptHarnessResultModel = GraphConceptHarnessResultModel
ConceptLinkModel = GraphConceptLinkModel
ConceptMemberModel = GraphConceptMemberModel
ConceptPolicyModel = GraphConceptPolicyModel
ConceptSetModel = GraphConceptSetModel

__all__ = [
    "ConceptAliasModel",
    "ConceptDecisionModel",
    "ConceptHarnessResultModel",
    "ConceptLinkModel",
    "ConceptMemberModel",
    "ConceptPolicyModel",
    "ConceptSetModel",
]
