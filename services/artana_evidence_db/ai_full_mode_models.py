"""Domain models for DB-owned AI Full Mode governance."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field

ConceptProposalStatus = Literal[
    "SUBMITTED",
    "DUPLICATE_CANDIDATE",
    "CHANGES_REQUESTED",
    "APPROVED",
    "REJECTED",
    "MERGED",
    "APPLIED",
]
ConceptProposalDecision = Literal[
    "CREATE_NEW",
    "MATCH_EXISTING",
    "MERGE_AS_SYNONYM",
    "SYNONYM_COLLISION",
    "EXTERNAL_REF_MATCH",
    "NEEDS_REVIEW",
]
GraphChangeProposalStatus = Literal[
    "READY_FOR_REVIEW",
    "CHANGES_REQUESTED",
    "REJECTED",
    "APPLIED",
]
AIDecisionStatus = Literal["SUBMITTED", "REJECTED", "APPLIED"]
AIDecisionAction = Literal[
    "APPROVE",
    "MERGE",
    "REJECT",
    "REQUEST_CHANGES",
    "APPLY_RESOLUTION_PLAN",
]
AIDecisionRiskTier = Literal["low", "medium", "high"]
AIPolicyOutcome = Literal[
    "human_required",
    "ai_allowed",
    "ai_allowed_when_low_risk",
    "blocked",
]
ConnectorProposalStatus = Literal[
    "SUBMITTED",
    "CHANGES_REQUESTED",
    "APPROVED",
    "REJECTED",
]


class ConceptProposal(BaseModel):
    """AI or human proposal for a new or merged semantic concept."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str
    research_space_id: str
    status: ConceptProposalStatus
    candidate_decision: ConceptProposalDecision
    domain_context: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    normalized_label: str = Field(..., min_length=1, max_length=255)
    concept_set_id: str | None = None
    existing_concept_member_id: str | None = None
    applied_concept_member_id: str | None = None
    synonyms_payload: list[str] = Field(default_factory=list)
    external_refs_payload: list[JSONObject] = Field(default_factory=list)
    evidence_payload: JSONObject = Field(default_factory=dict)
    duplicate_checks_payload: JSONObject = Field(default_factory=dict)
    warnings_payload: list[str] = Field(default_factory=list)
    decision_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = None
    proposed_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    decision_reason: str | None = None
    source_ref: str | None = None
    proposal_hash: str
    created_at: datetime
    updated_at: datetime


class GraphChangeProposal(BaseModel):
    """Mini-graph proposal containing concepts and relation claims."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str
    research_space_id: str
    status: GraphChangeProposalStatus
    proposal_payload: JSONObject
    resolution_plan_payload: JSONObject
    warnings_payload: list[str] = Field(default_factory=list)
    error_payload: list[str] = Field(default_factory=list)
    applied_concept_member_ids_payload: list[str] = Field(default_factory=list)
    applied_claim_ids_payload: list[str] = Field(default_factory=list)
    proposed_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    decision_reason: str | None = None
    source_ref: str | None = None
    proposal_hash: str
    created_at: datetime
    updated_at: datetime


class AIDecision(BaseModel):
    """Auditable AI decision envelope for one proposal snapshot."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str
    research_space_id: str
    target_type: Literal["concept_proposal", "graph_change_proposal"]
    target_id: str
    action: AIDecisionAction
    status: AIDecisionStatus
    ai_principal: str
    confidence: float
    computed_confidence: float
    confidence_assessment_payload: JSONObject
    confidence_model_version: str | None
    risk_tier: AIDecisionRiskTier
    input_hash: str
    policy_outcome: AIPolicyOutcome
    evidence_payload: JSONObject
    decision_payload: JSONObject
    rejection_reason: str | None = None
    created_by: str
    applied_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConnectorProposal(BaseModel):
    """Governed connector metadata proposal.

    The graph DB records connector metadata and mappings only. It never stores
    or executes connector runtime code.
    """

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str
    research_space_id: str
    status: ConnectorProposalStatus
    connector_slug: str
    display_name: str
    connector_kind: str
    domain_context: str
    metadata_payload: JSONObject
    mapping_payload: JSONObject
    validation_payload: JSONObject
    approval_payload: JSONObject
    rationale: str | None = None
    evidence_payload: JSONObject
    proposed_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    decision_reason: str | None = None
    source_ref: str | None = None
    created_at: datetime
    updated_at: datetime


__all__ = [
    "AIDecision",
    "AIDecisionAction",
    "AIDecisionRiskTier",
    "AIDecisionStatus",
    "AIPolicyOutcome",
    "ConceptProposal",
    "ConceptProposalDecision",
    "ConceptProposalStatus",
    "ConnectorProposal",
    "ConnectorProposalStatus",
    "GraphChangeProposal",
    "GraphChangeProposalStatus",
]
