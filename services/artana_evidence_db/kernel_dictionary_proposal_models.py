"""Dictionary proposal and changelog ORM models."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class _TimestampAuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Record creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        doc="Last update timestamp",
    )


class DictionaryProposalModel(_TimestampAuditMixin, Base):
    """Governed proposal for changing dictionary rules."""

    __tablename__ = "dictionary_proposals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        doc="Stable proposal identifier",
    )
    proposal_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Proposal type, e.g. ENTITY_TYPE, RELATION_TYPE, VALUE_SET_ITEM",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="SUBMITTED",
        index=True,
        doc=(
            "Proposal status: SUBMITTED, CHANGES_REQUESTED, APPROVED, "
            "REJECTED, MERGED"
        ),
    )
    source_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Proposed relation source entity type",
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Proposed entity type identifier",
    )
    relation_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Proposed relation type identifier",
    )
    target_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Proposed relation target entity type",
    )
    value_set_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Proposed value set identifier or item parent",
    )
    variable_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Proposed value-set variable identifier",
    )
    canonical_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Proposed variable canonical name",
    )
    data_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Proposed variable data type",
    )
    preferred_unit: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Preferred unit for a proposed variable",
    )
    constraints: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc="Proposed constraints payload for variable definitions",
    )
    sensitivity: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Proposed variable sensitivity level",
    )
    code: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Proposed value-set item code",
    )
    synonym: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Proposed relation synonym",
    )
    source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Optional source label for a proposed synonym",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Proposed dictionary display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Proposed dictionary description",
    )
    name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Proposed value-set name",
    )
    display_label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Proposed value-set item display label",
    )
    domain_context: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Proposed dictionary domain context",
    )
    external_ontology_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Optional external ontology reference for proposed entity types",
    )
    external_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Optional external reference for proposed value sets or codes",
    )
    expected_properties: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc="Expected property schema for proposed entity types",
    )
    synonyms: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        doc="Proposed synonyms for a value-set item",
    )
    is_directional: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        doc="Whether a proposed relation type is directional",
    )
    inverse_label: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Optional inverse label for proposed relation types",
    )
    is_extensible: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        doc="Whether a proposed value set allows extensions",
    )
    sort_order: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Proposed value-set item sort order",
    )
    is_active_value: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        doc="Whether a proposed value-set item starts active",
    )
    is_allowed: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        doc="Whether the proposed constraint permits this triple",
    )
    requires_evidence: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        doc="Whether the proposed constraint requires evidence",
    )
    profile: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        doc="Proposed enforcement profile",
    )
    rationale: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Human or AI rationale for the proposal",
    )
    evidence_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        doc="Evidence, citations, or model trace that supports the proposal",
    )
    proposed_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        doc="Actor proposing the change: manual:{user_id} or agent:{run_id}",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Actor who approved or rejected the proposal",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when the proposal was decided",
    )
    decision_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reviewer reason for approval or rejection",
    )
    merge_target_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Official dictionary dimension this proposal was merged into",
    )
    merge_target_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Official dictionary identifier this proposal was merged into",
    )
    applied_constraint_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(qualify_graph_foreign_key_target("relation_constraints.id")),
        nullable=True,
        doc="Official relation constraint created by approval",
    )
    applied_domain_context_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_domain_contexts.id")),
        nullable=True,
        doc="Official domain context created by approval",
    )
    applied_entity_type_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_entity_types.id")),
        nullable=True,
        doc="Official entity type created by approval",
    )
    applied_variable_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("variable_definitions.id")),
        nullable=True,
        doc="Official variable created by approval",
    )
    applied_relation_type_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_relation_types.id")),
        nullable=True,
        doc="Official relation type created by approval",
    )
    applied_relation_synonym_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(qualify_graph_foreign_key_target("dictionary_relation_synonyms.id")),
        nullable=True,
        doc="Official relation synonym created by approval",
    )
    applied_value_set_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("value_sets.id")),
        nullable=True,
        doc="Official value set created by approval",
    )
    applied_value_set_item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(qualify_graph_foreign_key_target("value_set_items.id")),
        nullable=True,
        doc="Official value-set item created by approval",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for proposal creation",
    )

    __table_args__ = (
        CheckConstraint(
            "proposal_type IN ("
            "'DOMAIN_CONTEXT', 'ENTITY_TYPE', 'VARIABLE', 'RELATION_TYPE', "
            "'RELATION_CONSTRAINT', 'RELATION_SYNONYM', "
            "'VALUE_SET', 'VALUE_SET_ITEM'"
            ")",
            name="ck_dictionary_proposals_type",
        ),
        CheckConstraint(
            "status IN ("
            "'SUBMITTED', 'CHANGES_REQUESTED', 'APPROVED', 'REJECTED', 'MERGED'"
            ")",
            name="ck_dictionary_proposals_status",
        ),
        UniqueConstraint(
            "source_ref",
            name="uq_dictionary_proposals_source_ref",
        ),
        Index(
            "idx_dictionary_proposals_relation_triple",
            "source_type",
            "relation_type",
            "target_type",
        ),
        graph_table_options(comment="Governed dictionary change proposals"),
    )


class DictionaryChangelogModel(_TimestampAuditMixin, Base):
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


__all__ = ["DictionaryChangelogModel", "DictionaryProposalModel"]
