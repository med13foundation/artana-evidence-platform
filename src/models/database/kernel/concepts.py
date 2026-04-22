"""Kernel Concept Manager models.

Concept Manager is a research-space semantic overlay over the canonical
dictionary. It tracks concept sets, aliases, links, policies, and
AI/human decision governance.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from sqlalchemy import (
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
from src.type_definitions.common import JSONObject  # noqa: TC001

_ACTIVE_VALIDITY_CHECK = (
    "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))"
)
_REVIEW_STATUS_CHECK = "review_status IN ('ACTIVE', 'PENDING_REVIEW', 'REVOKED')"


class ConceptSetModel(Base):
    """Research-space scoped container for concept members."""

    __tablename__ = "concept_sets"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain_context: Mapped[str] = mapped_column(
        ForeignKey(qualify_graph_foreign_key_target("dictionary_domain_contexts.id")),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
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
    superseded_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_sets.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
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
        graph_table_options(
            comment="Research-space scoped semantic concept sets",
        ),
    )


class ConceptMemberModel(Base):
    """Canonical or provisional concept in a concept set."""

    __tablename__ = "concept_members"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    concept_set_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_sets.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    domain_context: Mapped[str] = mapped_column(
        ForeignKey(qualify_graph_foreign_key_target("dictionary_domain_contexts.id")),
        nullable=False,
    )
    dictionary_dimension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dictionary_entry_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    canonical_label: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_label: Mapped[str] = mapped_column(String(255), nullable=False)
    sense_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="",
    )
    is_provisional: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
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
    superseded_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_members.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
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
        graph_table_options(
            comment="Canonical and provisional concept members per research space",
        ),
    )


class ConceptAliasModel(Base):
    """Normalized alias labels for concept members."""

    __tablename__ = "concept_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concept_member_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_members.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    domain_context: Mapped[str] = mapped_column(
        ForeignKey(qualify_graph_foreign_key_target("dictionary_domain_contexts.id")),
        nullable=False,
    )
    alias_label: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
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
            qualify_graph_foreign_key_target("concept_aliases.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
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
        graph_table_options(
            comment="Normalized aliases for concept-member resolution",
        ),
    )


class ConceptLinkModel(Base):
    """Typed relation between two concept members inside a research space."""

    __tablename__ = "concept_links"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    source_member_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_members.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    target_member_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_members.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    link_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="1.0",
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
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
    superseded_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_links.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
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
        graph_table_options(
            comment="Typed semantic links between concept members",
        ),
    )


class ConceptPolicyModel(Base):
    """One active policy profile per research space."""

    __tablename__ = "concept_policies"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    profile_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="default",
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    minimum_edge_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.6",
    )
    minimum_distinct_documents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )
    allow_generic_relations: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
    )
    max_edges_per_document: Mapped[int | None] = mapped_column(Integer, nullable=True)
    policy_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
    )
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
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
        graph_table_options(
            comment="Per-space concept governance policy profiles",
        ),
    )


class ConceptDecisionModel(Base):
    """Decision ledger rows for concept operations and governance actions."""

    __tablename__ = "concept_decisions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    concept_set_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_sets.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    concept_member_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_members.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    concept_link_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_links.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    decision_type: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_status: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    decision_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    harness_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
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
        graph_table_options(
            comment="Decision ledger for concept governance operations",
        ),
    )


class ConceptHarnessResultModel(Base):
    """Audit trail for AI harness checks on concept decisions."""

    __tablename__ = "concept_harness_results"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    decision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("concept_decisions.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    harness_name: Mapped[str] = mapped_column(String(64), nullable=False)
    harness_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    checks_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    errors_payload: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
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
        graph_table_options(
            comment="Harness/audit outcomes attached to concept decisions",
        ),
    )


__all__ = [
    "ConceptAliasModel",
    "ConceptDecisionModel",
    "ConceptHarnessResultModel",
    "ConceptLinkModel",
    "ConceptMemberModel",
    "ConceptPolicyModel",
    "ConceptSetModel",
]
