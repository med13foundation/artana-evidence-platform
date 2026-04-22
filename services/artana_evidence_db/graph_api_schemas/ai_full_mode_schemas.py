"""Typed API schemas for AI Full Mode governance."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.ai_full_mode_models import (
    AIDecision,
    ConceptProposal,
    ConnectorProposal,
    GraphChangeProposal,
)
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.decision_confidence import DecisionConfidenceAssessment
from artana_evidence_db.fact_assessment import (
    FactAssessment,
    assessment_confidence,
)
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


class ConceptExternalRefRequest(BaseModel):
    """External concept identifier proposed by a client or AI agent."""

    model_config = ConfigDict(strict=False)

    namespace: str = Field(..., min_length=1, max_length=128)
    identifier: str = Field(..., min_length=1, max_length=255)


class ConceptProposalCreateRequest(BaseModel):
    """Create a concept proposal without mutating official concept state."""

    model_config = ConfigDict(strict=False)

    domain_context: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    synonyms: list[str] = Field(default_factory=list)
    external_refs: list[ConceptExternalRefRequest] = Field(default_factory=list)
    evidence_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptProposalResponse(BaseModel):
    """Public concept proposal response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    status: ConceptProposalStatus
    candidate_decision: ConceptProposalDecision
    domain_context: str
    entity_type: str
    canonical_label: str
    normalized_label: str
    concept_set_id: str | None
    existing_concept_member_id: str | None
    applied_concept_member_id: str | None
    synonyms_payload: list[str]
    external_refs_payload: list[JSONObject]
    evidence_payload: JSONObject
    duplicate_checks_payload: JSONObject
    warnings_payload: list[str]
    decision_payload: JSONObject
    rationale: str | None
    proposed_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    decision_reason: str | None
    source_ref: str | None
    proposal_hash: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ConceptProposal) -> ConceptProposalResponse:
        return cls.model_validate(model.model_dump())


class ConceptProposalListResponse(BaseModel):
    """List response for concept proposals."""

    model_config = ConfigDict(strict=True)

    concept_proposals: list[ConceptProposalResponse]
    total: int = Field(..., ge=0)


class ConceptProposalDecisionRequest(BaseModel):
    """Manual approval/merge/rejection note."""

    model_config = ConfigDict(strict=False)

    decision_reason: str | None = Field(default=None, max_length=4096)


class ConceptProposalRejectRequest(BaseModel):
    """Reject or request changes on a concept proposal."""

    model_config = ConfigDict(strict=False)

    decision_reason: str = Field(..., min_length=1, max_length=4096)


class ConceptProposalMergeRequest(BaseModel):
    """Merge a concept proposal into an existing concept member."""

    model_config = ConfigDict(strict=False)

    target_concept_member_id: UUID
    decision_reason: str | None = Field(default=None, max_length=4096)


class GraphChangeConceptRequest(BaseModel):
    """Local concept inside a graph-change bundle."""

    model_config = ConfigDict(strict=False)

    local_id: str = Field(..., min_length=1, max_length=128)
    domain_context: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    synonyms: list[str] = Field(default_factory=list)
    external_refs: list[ConceptExternalRefRequest] = Field(default_factory=list)
    evidence_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)


class GraphChangeClaimRequest(BaseModel):
    """Local relation claim inside a graph-change bundle."""

    model_config = ConfigDict(strict=False, extra="forbid")

    source_local_id: str = Field(..., min_length=1, max_length=128)
    target_local_id: str = Field(..., min_length=1, max_length=128)
    relation_type: str = Field(..., min_length=1, max_length=64)
    assessment: FactAssessment
    evidence_payload: JSONObject = Field(default_factory=dict)
    claim_text: str | None = Field(default=None, max_length=4000)
    source_document_ref: str | None = Field(default=None, max_length=1024)

    @property
    def derived_confidence(self) -> float:
        return assessment_confidence(self.assessment)


class GraphChangeProposalCreateRequest(BaseModel):
    """Create one mini-graph proposal bundle."""

    model_config = ConfigDict(strict=False)

    concepts: list[GraphChangeConceptRequest] = Field(..., min_length=1)
    claims: list[GraphChangeClaimRequest] = Field(default_factory=list)
    source_ref: str | None = Field(default=None, max_length=1024)


class GraphChangeProposalResponse(BaseModel):
    """Public graph-change proposal response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    status: Literal["READY_FOR_REVIEW", "CHANGES_REQUESTED", "REJECTED", "APPLIED"]
    proposal_payload: JSONObject
    resolution_plan_payload: JSONObject
    warnings_payload: list[str]
    error_payload: list[str]
    applied_concept_member_ids_payload: list[str]
    applied_claim_ids_payload: list[str]
    proposed_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    decision_reason: str | None
    source_ref: str | None
    proposal_hash: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: GraphChangeProposal) -> GraphChangeProposalResponse:
        return cls.model_validate(model.model_dump())


class GraphChangeProposalListResponse(BaseModel):
    """List response for graph-change proposals."""

    model_config = ConfigDict(strict=True)

    graph_change_proposals: list[GraphChangeProposalResponse]
    total: int = Field(..., ge=0)


class AIDecisionSubmitRequest(BaseModel):
    """AI decision envelope submitted to the DB for policy evaluation."""

    model_config = ConfigDict(strict=False, extra="forbid")

    target_type: Literal["concept_proposal", "graph_change_proposal"]
    target_id: UUID
    action: Literal[
        "APPROVE",
        "MERGE",
        "REJECT",
        "REQUEST_CHANGES",
        "APPLY_RESOLUTION_PLAN",
    ]
    ai_principal: str = Field(..., min_length=1, max_length=128)
    confidence_assessment: DecisionConfidenceAssessment
    risk_tier: Literal["low", "medium", "high"]
    input_hash: str = Field(..., min_length=64, max_length=64)
    evidence_payload: JSONObject = Field(default_factory=dict)
    decision_payload: JSONObject = Field(default_factory=dict)


class AIDecisionResponse(BaseModel):
    """Public AI decision response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    target_type: Literal["concept_proposal", "graph_change_proposal"]
    target_id: str
    action: Literal[
        "APPROVE",
        "MERGE",
        "REJECT",
        "REQUEST_CHANGES",
        "APPLY_RESOLUTION_PLAN",
    ]
    status: Literal["SUBMITTED", "REJECTED", "APPLIED"]
    ai_principal: str
    confidence: float
    computed_confidence: float
    confidence_assessment_payload: JSONObject
    confidence_model_version: str | None
    risk_tier: Literal["low", "medium", "high"]
    input_hash: str
    policy_outcome: Literal[
        "human_required",
        "ai_allowed",
        "ai_allowed_when_low_risk",
        "blocked",
    ]
    evidence_payload: JSONObject
    decision_payload: JSONObject
    rejection_reason: str | None
    created_by: str
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: AIDecision) -> AIDecisionResponse:
        return cls.model_validate(model.model_dump())


class AIDecisionListResponse(BaseModel):
    """List response for AI decisions."""

    model_config = ConfigDict(strict=True)

    ai_decisions: list[AIDecisionResponse]
    total: int = Field(..., ge=0)


class ConnectorProposalCreateRequest(BaseModel):
    """Create a metadata-only connector proposal."""

    model_config = ConfigDict(strict=False)

    connector_slug: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    connector_kind: str = Field(..., min_length=1, max_length=64)
    domain_context: str = Field(..., min_length=1, max_length=64)
    metadata_payload: JSONObject = Field(default_factory=dict)
    mapping_payload: JSONObject = Field(default_factory=dict)
    evidence_payload: JSONObject = Field(default_factory=dict)
    rationale: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConnectorProposalResponse(BaseModel):
    """Public connector proposal response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    status: Literal["SUBMITTED", "CHANGES_REQUESTED", "APPROVED", "REJECTED"]
    connector_slug: str
    display_name: str
    connector_kind: str
    domain_context: str
    metadata_payload: JSONObject
    mapping_payload: JSONObject
    validation_payload: JSONObject
    approval_payload: JSONObject
    rationale: str | None
    evidence_payload: JSONObject
    proposed_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    decision_reason: str | None
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ConnectorProposal) -> ConnectorProposalResponse:
        return cls.model_validate(model.model_dump())


class ConnectorProposalListResponse(BaseModel):
    """List response for connector proposals."""

    model_config = ConfigDict(strict=True)

    connector_proposals: list[ConnectorProposalResponse]
    total: int = Field(..., ge=0)


__all__ = [
    "AIDecisionListResponse",
    "AIDecisionResponse",
    "AIDecisionSubmitRequest",
    "ConceptExternalRefRequest",
    "ConceptProposalCreateRequest",
    "ConceptProposalDecisionRequest",
    "ConceptProposalListResponse",
    "ConceptProposalMergeRequest",
    "ConceptProposalRejectRequest",
    "ConceptProposalResponse",
    "ConnectorProposalCreateRequest",
    "ConnectorProposalListResponse",
    "ConnectorProposalResponse",
    "GraphChangeClaimRequest",
    "GraphChangeConceptRequest",
    "GraphChangeProposalCreateRequest",
    "GraphChangeProposalListResponse",
    "GraphChangeProposalResponse",
]
