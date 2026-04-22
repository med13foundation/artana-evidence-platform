"""Domain models for unified graph workflow product modes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field

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
GraphWorkflowPolicyOutcomeName = Literal[
    "ai_allowed",
    "ai_allowed_when_low_risk",
    "human_required",
    "blocked",
]


class GraphWorkflowPolicy(BaseModel):
    """Per-space workflow policy controls for one operating mode.

    min_ai_confidence is the minimum DB-computed policy confidence, not an
    LLM-authored self score.
    """

    model_config = ConfigDict(strict=True)

    allow_ai_graph_repair: bool = False
    allow_ai_evidence_decisions: bool = False
    batch_auto_apply_low_risk: bool = False
    trusted_ai_principals: list[str] = Field(default_factory=list)
    min_ai_confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class GraphOperatingModeConfig(BaseModel):
    """Operating mode envelope stored under graph_spaces.settings.operating_mode."""

    model_config = ConfigDict(strict=True)

    mode: GraphOperatingMode = "manual"
    workflow_policy: GraphWorkflowPolicy = Field(
        default_factory=GraphWorkflowPolicy,
    )


class GraphWorkflowPolicyOutcome(BaseModel):
    """Decision produced by the workflow policy evaluator."""

    model_config = ConfigDict(strict=True)

    ai_allowed: bool
    ai_allowed_when_low_risk: bool
    human_required: bool
    blocked: bool
    outcome: GraphWorkflowPolicyOutcomeName
    reason: str


class GraphWorkflow(BaseModel):
    """Durable unified workflow state."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

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


class GraphWorkflowEvent(BaseModel):
    """Append-only event for workflow actions and policy outcomes."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: str
    workflow_id: str
    research_space_id: str
    actor: str
    action: str
    before_status: str | None
    after_status: str
    risk_tier: GraphWorkflowRiskTier | None
    confidence: float | None
    computed_confidence: float | None
    confidence_assessment_payload: JSONObject
    confidence_model_version: str | None
    input_hash: str | None
    policy_outcome_payload: JSONObject
    generated_resources_payload: JSONObject
    reason: str | None
    event_payload: JSONObject
    created_at: datetime


__all__ = [
    "GraphOperatingMode",
    "GraphOperatingModeConfig",
    "GraphWorkflow",
    "GraphWorkflowAction",
    "GraphWorkflowEvent",
    "GraphWorkflowKind",
    "GraphWorkflowPolicy",
    "GraphWorkflowPolicyOutcome",
    "GraphWorkflowPolicyOutcomeName",
    "GraphWorkflowRiskTier",
    "GraphWorkflowStatus",
]
