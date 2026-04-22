"""Persistence models for AI Full Mode governance proposals."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class _TimestampAuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ConceptProposalModel(_TimestampAuditMixin, Base):
    """Proposal ledger for new or merged concept definitions."""

    __tablename__ = "concept_proposals"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("graph_spaces.id")),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    domain_context: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_domain_contexts.id")),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_label: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_label: Mapped[str] = mapped_column(String(255), nullable=False)
    concept_set_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("concept_sets.id")),
        nullable=True,
    )
    existing_concept_member_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("concept_members.id")),
        nullable=True,
    )
    applied_concept_member_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("concept_members.id")),
        nullable=True,
    )
    synonyms_payload: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    external_refs_payload: Mapped[list[JSONObject]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    evidence_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    duplicate_checks_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    warnings_payload: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    decision_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "research_space_id",
            "source_ref",
            name="uq_concept_proposals_space_source_ref",
        ),
        CheckConstraint(
            "status IN ('SUBMITTED', 'DUPLICATE_CANDIDATE', 'CHANGES_REQUESTED', "
            "'APPROVED', 'REJECTED', 'MERGED', 'APPLIED')",
            name="ck_concept_proposals_status",
        ),
        CheckConstraint(
            "candidate_decision IN ('CREATE_NEW', 'MATCH_EXISTING', "
            "'MERGE_AS_SYNONYM', 'SYNONYM_COLLISION', 'EXTERNAL_REF_MATCH', "
            "'NEEDS_REVIEW')",
            name="ck_concept_proposals_candidate_decision",
        ),
        Index("idx_concept_proposals_space_status", "research_space_id", "status"),
        Index(
            "idx_concept_proposals_space_label",
            "research_space_id",
            "domain_context",
            "normalized_label",
        ),
        graph_table_options(
            comment="AI Full Mode concept proposal ledger",
        ),
    )


class GraphChangeProposalModel(_TimestampAuditMixin, Base):
    """Proposal ledger for bundled mini-graph changes."""

    __tablename__ = "graph_change_proposals"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("graph_spaces.id")),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    proposal_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    resolution_plan_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    warnings_payload: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    error_payload: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    applied_concept_member_ids_payload: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    applied_claim_ids_payload: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    proposed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "research_space_id",
            "source_ref",
            name="uq_graph_change_proposals_space_source_ref",
        ),
        CheckConstraint(
            "status IN ('READY_FOR_REVIEW', 'CHANGES_REQUESTED', 'REJECTED', 'APPLIED')",
            name="ck_graph_change_proposals_status",
        ),
        Index("idx_graph_change_proposals_space_status", "research_space_id", "status"),
        graph_table_options(
            comment="AI Full Mode bundled graph-change proposal ledger",
        ),
    )


class AIDecisionModel(_TimestampAuditMixin, Base):
    """Auditable AI decision envelope bound to a proposal snapshot hash."""

    __tablename__ = "ai_full_mode_decisions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("graph_spaces.id")),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    ai_principal: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    computed_confidence: Mapped[float] = mapped_column(
        nullable=False,
        server_default="0.0",
    )
    confidence_assessment_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    confidence_model_version: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_outcome: Mapped[str] = mapped_column(String(32), nullable=False)
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
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('concept_proposal', 'graph_change_proposal')",
            name="ck_ai_full_mode_decisions_target_type",
        ),
        CheckConstraint(
            "action IN ('APPROVE', 'MERGE', 'REJECT', 'REQUEST_CHANGES', "
            "'APPLY_RESOLUTION_PLAN')",
            name="ck_ai_full_mode_decisions_action",
        ),
        CheckConstraint(
            "status IN ('SUBMITTED', 'REJECTED', 'APPLIED')",
            name="ck_ai_full_mode_decisions_status",
        ),
        CheckConstraint(
            "risk_tier IN ('low', 'medium', 'high')",
            name="ck_ai_full_mode_decisions_risk_tier",
        ),
        CheckConstraint(
            "policy_outcome IN ('human_required', 'ai_allowed', "
            "'ai_allowed_when_low_risk', 'blocked')",
            name="ck_ai_full_mode_decisions_policy_outcome",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_ai_full_mode_decisions_confidence",
        ),
        CheckConstraint(
            "computed_confidence >= 0.0 AND computed_confidence <= 1.0",
            name="ck_ai_full_mode_decisions_computed_confidence",
        ),
        Index(
            "idx_ai_full_mode_decisions_space_target",
            "research_space_id",
            "target_type",
            "target_id",
        ),
        graph_table_options(
            comment="AI Full Mode decision-envelope audit ledger",
        ),
    )


class ConnectorProposalModel(_TimestampAuditMixin, Base):
    """Governed metadata proposal for external source connectors."""

    __tablename__ = "connector_proposals"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("graph_spaces.id")),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    connector_slug: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    connector_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_context: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_domain_contexts.id")),
        nullable=False,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    mapping_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    validation_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    approval_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    proposed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "research_space_id",
            "connector_slug",
            name="uq_connector_proposals_space_slug",
        ),
        UniqueConstraint(
            "research_space_id",
            "source_ref",
            name="uq_connector_proposals_space_source_ref",
        ),
        CheckConstraint(
            "status IN ('SUBMITTED', 'CHANGES_REQUESTED', 'APPROVED', 'REJECTED')",
            name="ck_connector_proposals_status",
        ),
        CheckConstraint(
            "length(trim(connector_slug)) > 0",
            name="ck_connector_proposals_slug_non_empty",
        ),
        Index("idx_connector_proposals_space_status", "research_space_id", "status"),
        Index(
            "idx_connector_proposals_space_domain",
            "research_space_id",
            "domain_context",
        ),
        graph_table_options(
            comment="Connector metadata proposals; runtime execution remains external",
        ),
    )


__all__ = [
    "AIDecisionModel",
    "ConceptProposalModel",
    "ConnectorProposalModel",
    "GraphChangeProposalModel",
]
