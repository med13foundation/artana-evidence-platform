"""Typed contracts for the deterministic full AI orchestrator baseline."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchOrchestratorActionType(str, Enum):
    """Allowlisted deterministic actions for the Phase 1 orchestrator."""

    INITIALIZE_WORKSPACE = "INITIALIZE_WORKSPACE"
    QUERY_PUBMED = "QUERY_PUBMED"
    INGEST_AND_EXTRACT_PUBMED = "INGEST_AND_EXTRACT_PUBMED"
    DERIVE_DRIVEN_TERMS = "DERIVE_DRIVEN_TERMS"
    REVIEW_PDF_WORKSET = "REVIEW_PDF_WORKSET"
    REVIEW_TEXT_WORKSET = "REVIEW_TEXT_WORKSET"
    LOAD_MONDO_GROUNDING = "LOAD_MONDO_GROUNDING"
    RUN_UNIPROT_GROUNDING = "RUN_UNIPROT_GROUNDING"
    RUN_HGNC_GROUNDING = "RUN_HGNC_GROUNDING"
    RUN_STRUCTURED_ENRICHMENT = "RUN_STRUCTURED_ENRICHMENT"
    RUN_BOOTSTRAP = "RUN_BOOTSTRAP"
    RUN_CHASE_ROUND = "RUN_CHASE_ROUND"
    RUN_GRAPH_CONNECTION = "RUN_GRAPH_CONNECTION"
    RUN_HYPOTHESIS_GENERATION = "RUN_HYPOTHESIS_GENERATION"
    RUN_GRAPH_SEARCH = "RUN_GRAPH_SEARCH"
    SEARCH_DISCONFIRMING = "SEARCH_DISCONFIRMING"
    GENERATE_BRIEF = "GENERATE_BRIEF"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    STOP = "STOP"


class FullAIOrchestratorPlannerMode(str, Enum):
    """Planner execution posture for one orchestrator run."""

    SHADOW = "shadow"
    GUARDED = "guarded"


class FullAIOrchestratorGuardedRolloutProfile(str, Enum):
    """Guarded planner authority profile for one orchestrator run."""

    GUARDED_DRY_RUN = "guarded_dry_run"
    GUARDED_CHASE_ONLY = "guarded_chase_only"
    GUARDED_SOURCE_CHASE = "guarded_source_chase"
    GUARDED_LOW_RISK = "guarded_low_risk"


class ResearchOrchestratorActionSpec(BaseModel):
    """Declarative metadata for one orchestrator action."""

    model_config = ConfigDict(strict=True)

    action_type: ResearchOrchestratorActionType
    source_bound: bool = False
    requires_enabled_source: bool = False
    default_source_key: str | None = Field(default=None, min_length=1, max_length=64)
    planner_state: Literal["live", "context_only", "reserved"] = "live"
    summary: str = Field(..., min_length=1, max_length=400)


class ResearchOrchestratorDecision(BaseModel):
    """One durable action decision recorded by the deterministic baseline."""

    model_config = ConfigDict(strict=True)

    decision_id: str = Field(..., min_length=1, max_length=255)
    round_number: int = Field(..., ge=0, le=100)
    action_type: ResearchOrchestratorActionType
    action_input: JSONObject = Field(default_factory=dict)
    source_key: str | None = Field(default=None, min_length=1, max_length=64)
    evidence_basis: str = Field(..., min_length=1, max_length=4000)
    stop_reason: str | None = Field(default=None, min_length=1, max_length=512)
    step_key: str = Field(..., min_length=1, max_length=255)
    status: str = Field(..., min_length=1, max_length=32)
    expected_value_band: Literal["low", "medium", "high"] | None = None
    qualitative_rationale: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
    )
    risk_level: Literal["low", "medium", "high"] | None = None
    requires_approval: bool | None = None
    budget_estimate: JSONObject | None = None
    fallback_reason: str | None = Field(default=None, min_length=1, max_length=512)
    metadata: JSONObject = Field(default_factory=dict)


class ResearchOrchestratorChaseCandidate(BaseModel):
    """One bounded candidate entity for a planner-reviewed chase round."""

    model_config = ConfigDict(strict=True)

    entity_id: str = Field(..., min_length=1, max_length=255)
    display_label: str = Field(..., min_length=1, max_length=512)
    normalized_label: str = Field(..., min_length=1, max_length=512)
    candidate_rank: int = Field(..., ge=1, le=10)
    observed_round: int = Field(..., ge=1, le=2)
    available_source_keys: list[str] = Field(default_factory=list, max_length=16)
    evidence_basis: str = Field(..., min_length=1, max_length=4000)
    novelty_basis: Literal["not_in_previous_seed_terms"]


class ResearchOrchestratorChaseSelection(BaseModel):
    """One planner-readable selection outcome for a chase checkpoint."""

    model_config = ConfigDict(strict=True)

    selected_entity_ids: list[str] = Field(default_factory=list, max_length=10)
    selected_labels: list[str] = Field(default_factory=list, max_length=10)
    stop_instead: bool = False
    stop_reason: str | None = Field(default=None, min_length=1, max_length=512)
    selection_basis: str = Field(..., min_length=1, max_length=4000)


class ResearchOrchestratorGuardedDecisionProof(BaseModel):
    """Durable audit receipt for one guarded planner decision checkpoint."""

    model_config = ConfigDict(strict=True)

    proof_id: str = Field(..., min_length=1, max_length=255)
    artifact_key: str = Field(..., min_length=1, max_length=255)
    checkpoint_key: str = Field(..., min_length=1, max_length=255)
    guarded_strategy: str = Field(..., min_length=1, max_length=255)
    planner_mode: Literal["shadow", "guarded"]
    guarded_rollout_profile: str = Field(..., min_length=1, max_length=255)
    guarded_rollout_profile_source: str = Field(..., min_length=1, max_length=255)
    guarded_policy_version: str = Field(..., min_length=1, max_length=255)
    decision_outcome: Literal["allowed", "blocked", "ignored"]
    outcome_reason: str = Field(..., min_length=1, max_length=512)
    deterministic_action_type: str | None = Field(default=None, max_length=128)
    deterministic_source_key: str | None = Field(default=None, max_length=128)
    recommended_action_type: str | None = Field(default=None, max_length=128)
    recommended_source_key: str | None = Field(default=None, max_length=128)
    applied_action_type: str | None = Field(default=None, max_length=128)
    applied_source_key: str | None = Field(default=None, max_length=128)
    planner_status: str | None = Field(default=None, max_length=128)
    used_fallback: bool
    fallback_reason: str | None = Field(default=None, max_length=512)
    validation_error: str | None = Field(default=None, max_length=4000)
    qualitative_rationale_present: bool
    budget_violation: bool
    disabled_source_violation: bool
    policy_allowed: bool
    comparison_status: str | None = Field(default=None, max_length=128)
    verification_status: str | None = Field(default=None, max_length=128)
    verification_reason: str | None = Field(default=None, max_length=512)
    model_id: str | None = Field(default=None, max_length=255)
    prompt_version: str | None = Field(default=None, max_length=255)
    agent_run_id: str | None = Field(default=None, max_length=255)
    decision_id: str | None = Field(default=None, max_length=255)
    step_key: str | None = Field(default=None, max_length=255)
    qualitative_rationale: str | None = Field(default=None, max_length=4000)
    evidence_basis: str | None = Field(default=None, max_length=4000)
    comparison: JSONObject = Field(default_factory=dict)
    recommendation: JSONObject = Field(default_factory=dict)
    guarded_action: JSONObject | None = None


class ResearchOrchestratorFilteredChaseCandidate(BaseModel):
    """One chase candidate dropped before deterministic selection."""

    model_config = ConfigDict(strict=True)

    entity_id: str = Field(..., min_length=1, max_length=255)
    display_label: str = Field(..., min_length=1, max_length=512)
    normalized_label: str = Field(..., min_length=1, max_length=512)
    observed_rank: int = Field(..., ge=1, le=20)
    observed_round: int = Field(..., ge=1, le=2)
    filter_reason: Literal[
        "generic_result_label",
        "clinical_significance_bucket",
        "accession_like_placeholder",
        "taxonomic_spillover",
        "underanchored_fragment_label",
    ]


class FullAIOrchestratorRunRequest(BaseModel):
    """Request payload for one deterministic full AI orchestrator run."""

    model_config = ConfigDict(strict=True)

    objective: str = Field(..., min_length=1, max_length=4000)
    seed_terms: list[str] | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    sources: ResearchSpaceSourcePreferences | None = None
    max_depth: int = Field(default=2, ge=1, le=4)
    max_hypotheses: int = Field(default=20, ge=1, le=100)
    planner_mode: FullAIOrchestratorPlannerMode = FullAIOrchestratorPlannerMode.SHADOW
    guarded_rollout_profile: FullAIOrchestratorGuardedRolloutProfile | None = Field(
        default=None,
        strict=False,
    )
    pubmed_replay_bundle: JSONObject | None = Field(
        default=None,
        description=(
            "Internal/testing only. Reuse one precomputed PubMed replay bundle "
            "so paired runs can share the exact same candidate selection."
        ),
    )

    @field_validator("planner_mode", mode="before")
    @classmethod
    def _coerce_planner_mode(
        cls,
        value: object,
    ) -> FullAIOrchestratorPlannerMode | object:
        if isinstance(value, str):
            return FullAIOrchestratorPlannerMode(value)
        return value

    @field_validator("guarded_rollout_profile", mode="before")
    @classmethod
    def _coerce_guarded_rollout_profile(
        cls,
        value: object,
    ) -> FullAIOrchestratorGuardedRolloutProfile | object:
        if isinstance(value, str):
            return FullAIOrchestratorGuardedRolloutProfile(value)
        return value


class FullAIOrchestratorRunResponse(BaseModel):
    """Completed deterministic full AI orchestrator result."""

    model_config = ConfigDict(strict=True)

    planner_mode: FullAIOrchestratorPlannerMode = FullAIOrchestratorPlannerMode.SHADOW
    guarded_rollout_profile: FullAIOrchestratorGuardedRolloutProfile | None = Field(
        default=None,
        strict=False,
    )
    run: JSONObject
    action_history: list[ResearchOrchestratorDecision]
    workspace_summary: JSONObject
    source_execution_summary: JSONObject
    bootstrap_summary: JSONObject | None = None
    brief_metadata: JSONObject
    shadow_planner: JSONObject | None = None
    guarded_execution: JSONObject | None = None
    guarded_decision_proofs: JSONObject | None = None
    errors: list[str]

    @field_validator("guarded_rollout_profile", mode="before")
    @classmethod
    def _coerce_guarded_rollout_profile(
        cls,
        value: object,
    ) -> FullAIOrchestratorGuardedRolloutProfile | object:
        if isinstance(value, str):
            return FullAIOrchestratorGuardedRolloutProfile(value)
        return value


__all__ = [
    "FullAIOrchestratorGuardedRolloutProfile",
    "FullAIOrchestratorPlannerMode",
    "ResearchOrchestratorChaseCandidate",
    "ResearchOrchestratorFilteredChaseCandidate",
    "ResearchOrchestratorChaseSelection",
    "ResearchOrchestratorGuardedDecisionProof",
    "FullAIOrchestratorRunRequest",
    "FullAIOrchestratorRunResponse",
    "ResearchOrchestratorActionSpec",
    "ResearchOrchestratorActionType",
    "ResearchOrchestratorDecision",
]
