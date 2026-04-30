"""Workflow and hypothesis API contract models for the graph service boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .common import JSONObject
from .graph_decision_contracts import DecisionConfidenceAssessment

GraphOperatingMode = Literal[
    "manual",
    "ai_assist_human_batch",
    "human_evidence_ai_graph",
    "ai_full_graph",
    "ai_full_evidence",
    "continuous_learning",
]
GraphWorkflowKind = Literal[
    "evidence_approval",
    "batch_review",
    "ai_evidence_decision",
    "conflict_resolution",
    "continuous_learning_review",
    "bootstrap_review",
]
GraphWorkflowStatus = Literal[
    "SUBMITTED",
    "PLAN_READY",
    "WAITING_REVIEW",
    "APPLIED",
    "REJECTED",
    "CHANGES_REQUESTED",
    "BLOCKED",
    "FAILED",
]
GraphWorkflowAction = Literal[
    "apply_plan",
    "approve",
    "reject",
    "request_changes",
    "split",
    "defer_to_human",
    "mark_resolved",
]
GraphWorkflowRiskTier = Literal["low", "medium", "high"]


class GraphWorkflowPolicy(BaseModel):
    """Per-space workflow policy controls for one operating mode."""

    model_config = ConfigDict(strict=True)

    allow_ai_graph_repair: bool = False
    allow_ai_evidence_decisions: bool = False
    batch_auto_apply_low_risk: bool = False
    trusted_ai_principals: list[str] = Field(default_factory=list)
    min_ai_confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class OperatingModeRequest(BaseModel):
    """Request payload for updating one graph space operating mode."""

    model_config = ConfigDict(strict=True)

    mode: GraphOperatingMode
    workflow_policy: GraphWorkflowPolicy = Field(
        default_factory=GraphWorkflowPolicy,
    )


class OperatingModeResponse(BaseModel):
    """Public operating mode response."""

    model_config = ConfigDict(strict=True)

    research_space_id: str
    mode: GraphOperatingMode
    workflow_policy: GraphWorkflowPolicy
    capabilities: JSONObject


class OperatingModeCapabilitiesResponse(BaseModel):
    """Public capabilities for the active operating mode."""

    model_config = ConfigDict(strict=True)

    research_space_id: str
    mode: GraphOperatingMode
    capabilities: JSONObject


class GraphWorkflowCreateRequest(BaseModel):
    """Request payload for creating a unified graph workflow."""

    model_config = ConfigDict(strict=False)

    kind: GraphWorkflowKind
    input_payload: JSONObject = Field(default_factory=dict)
    decision_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class GraphWorkflowAIDecisionEnvelope(BaseModel):
    """Trusted AI actor envelope for workflow actions."""

    model_config = ConfigDict(strict=False)

    ai_principal: str = Field(..., min_length=1, max_length=128)
    model_id: str | None = Field(default=None, max_length=128)
    model_version: str | None = Field(default=None, max_length=128)
    prompt_id: str | None = Field(default=None, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=128)
    evidence_locator: str | None = Field(default=None, max_length=1024)
    rationale: str = Field(..., min_length=1, max_length=4000)


class GraphWorkflowActionRequest(BaseModel):
    """Request payload for acting on one unified graph workflow."""

    model_config = ConfigDict(strict=False, extra="forbid")

    action: GraphWorkflowAction
    input_hash: str | None = Field(default=None, min_length=64, max_length=64)
    risk_tier: GraphWorkflowRiskTier = "low"
    confidence_assessment: DecisionConfidenceAssessment | None = None
    reason: str | None = Field(default=None, max_length=4096)
    decision_payload: JSONObject = Field(default_factory=dict)
    generated_resources_payload: JSONObject = Field(default_factory=dict)
    ai_decision: GraphWorkflowAIDecisionEnvelope | None = None


class GraphWorkflowResponse(BaseModel):
    """Public unified graph workflow response."""

    model_config = ConfigDict(strict=True)

    id: str
    research_space_id: str
    kind: GraphWorkflowKind
    status: GraphWorkflowStatus
    operating_mode: GraphOperatingMode
    input_payload: JSONObject
    plan_payload: JSONObject
    generated_resources_payload: JSONObject
    decision_payload: JSONObject
    policy_payload: JSONObject
    explanation_payload: JSONObject
    source_ref: str | None
    workflow_hash: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class GraphWorkflowListResponse(BaseModel):
    """List response for unified graph workflows."""

    model_config = ConfigDict(strict=True)

    workflows: list[GraphWorkflowResponse]
    total: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)


class ExplanationResponse(BaseModel):
    """Human-readable explanation for graph workflow resources."""

    model_config = ConfigDict(strict=True)

    research_space_id: str
    resource_type: str
    resource_id: str
    why_this_exists: str
    approved_by: str | None = None
    evidence: JSONObject = Field(default_factory=dict)
    policy: JSONObject = Field(default_factory=dict)
    generated_resources: JSONObject = Field(default_factory=dict)
    validation: JSONObject = Field(default_factory=dict)
    next_action: JSONObject = Field(default_factory=dict)
    details: JSONObject = Field(default_factory=dict)


class ValidationExplanationRequest(BaseModel):
    """Request payload for explainable validation preflight."""

    model_config = ConfigDict(strict=False)

    validation_payload: JSONObject = Field(default_factory=dict)
    context_payload: JSONObject = Field(default_factory=dict)


class CreateManualHypothesisRequest(BaseModel):
    """Request payload for manually logging one hypothesis."""

    model_config = ConfigDict(strict=True)

    statement: str = Field(..., min_length=1, max_length=4000)
    rationale: str = Field(..., min_length=1, max_length=4000)
    seed_entity_ids: list[str] = Field(default_factory=list, max_length=100)
    source_type: str = Field(default="manual", min_length=1, max_length=64)


class HypothesisResponse(BaseModel):
    """Serialized hypothesis row derived from relation-claim ledger."""

    model_config = ConfigDict(strict=True)

    claim_id: UUID
    polarity: str
    claim_status: str
    validation_state: str
    persistability: str
    confidence: float
    source_label: str | None
    relation_type: str
    target_label: str | None
    claim_text: str | None
    linked_relation_id: UUID | None
    origin: str
    seed_entity_ids: list[str]
    supporting_provenance_ids: list[str]
    reasoning_path_id: UUID | None
    supporting_claim_ids: list[str]
    direct_supporting_claim_ids: list[str]
    transferred_supporting_claim_ids: list[str]
    transferred_from_entities: list[str]
    transfer_basis: list[str]
    contradiction_claim_ids: list[str]
    explanation: str | None
    path_confidence: float | None
    path_length: int | None
    created_at: datetime
    metadata: JSONObject


class HypothesisListResponse(BaseModel):
    """List response for hypotheses in one research space."""

    model_config = ConfigDict(strict=True)

    hypotheses: list[HypothesisResponse]
    total: int
    offset: int
    limit: int

__all__ = [
    "CreateManualHypothesisRequest",
    "ExplanationResponse",
    "GraphOperatingMode",
    "GraphWorkflowAIDecisionEnvelope",
    "GraphWorkflowAction",
    "GraphWorkflowActionRequest",
    "GraphWorkflowCreateRequest",
    "GraphWorkflowKind",
    "GraphWorkflowListResponse",
    "GraphWorkflowPolicy",
    "GraphWorkflowResponse",
    "GraphWorkflowRiskTier",
    "GraphWorkflowStatus",
    "HypothesisListResponse",
    "HypothesisResponse",
    "OperatingModeCapabilitiesResponse",
    "OperatingModeRequest",
    "OperatingModeResponse",
    "ValidationExplanationRequest",
]
