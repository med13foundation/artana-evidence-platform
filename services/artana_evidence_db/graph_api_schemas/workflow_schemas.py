"""API schemas for unified graph workflow product modes."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.decision_confidence import DecisionConfidenceAssessment
from artana_evidence_db.workflow_models import (
    GraphOperatingMode,
    GraphOperatingModeConfig,
    GraphWorkflow,
    GraphWorkflowAction,
    GraphWorkflowKind,
    GraphWorkflowPolicy,
    GraphWorkflowRiskTier,
    GraphWorkflowStatus,
)
from pydantic import BaseModel, ConfigDict, Field


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

    @classmethod
    def from_config(
        cls,
        *,
        research_space_id: str,
        config: GraphOperatingModeConfig,
        capabilities: JSONObject,
    ) -> OperatingModeResponse:
        return cls(
            research_space_id=research_space_id,
            mode=config.mode,
            workflow_policy=config.workflow_policy,
            capabilities=capabilities,
        )


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

    @classmethod
    def from_model(cls, model: GraphWorkflow) -> GraphWorkflowResponse:
        return cls.model_validate(model.model_dump())


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


__all__ = [
    "ExplanationResponse",
    "GraphWorkflowActionRequest",
    "GraphWorkflowAIDecisionEnvelope",
    "GraphWorkflowCreateRequest",
    "GraphWorkflowListResponse",
    "GraphWorkflowResponse",
    "OperatingModeCapabilitiesResponse",
    "OperatingModeRequest",
    "OperatingModeResponse",
    "ValidationExplanationRequest",
]
