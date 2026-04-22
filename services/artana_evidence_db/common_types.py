"""Service-local common JSON and settings types for the graph API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, TypedDict

JSONPrimitive = str | int | float | bool | None
type JSONValue = JSONPrimitive | Mapping[str, "JSONValue"] | Sequence["JSONValue"]
JSONObject = dict[str, JSONValue]


class RelationAutoPromotionSettings(TypedDict, total=False):
    """Relation auto-promotion policy controls."""

    enabled: bool
    min_distinct_sources: int
    min_aggregate_confidence: float
    require_distinct_documents: bool
    require_distinct_runs: bool
    block_if_conflicting_evidence: bool
    min_evidence_tier: str
    conflicting_confidence_threshold: float


class ResearchSpaceSourcePreferences(TypedDict, total=False):
    """Per-space discovery source preferences."""

    pubmed: bool
    marrvel: bool
    clinvar: bool
    mondo: bool
    pdf: bool
    text: bool
    drugbank: bool
    alphafold: bool
    uniprot: bool
    hgnc: bool
    clinical_trials: bool
    mgi: bool
    zfin: bool


class AIFullModeSettings(TypedDict, total=False):
    """Per-space policy controls for DB-owned AI decision authority.

    min_confidence is evaluated against DB-computed confidence.
    """

    governance_mode: Literal["human_review", "ai_assisted", "ai_full"]
    trusted_principals: list[str]
    min_confidence: float
    allow_high_risk_actions: bool
    allow_phi_auto_approval: bool
    low_risk_actions: list[str]


class WorkflowPolicySettings(TypedDict, total=False):
    """Per-space controls for unified graph workflow authority.

    min_ai_confidence is evaluated against DB-computed confidence.
    """

    allow_ai_graph_repair: bool
    allow_ai_evidence_decisions: bool
    batch_auto_apply_low_risk: bool
    trusted_ai_principals: list[str]
    min_ai_confidence: float


class OperatingModeSettings(TypedDict, total=False):
    """Per-space product operating mode stored in graph_spaces.settings."""

    mode: Literal[
        "manual",
        "ai_assist_human_batch",
        "human_evidence_ai_graph",
        "ai_full_graph",
        "ai_full_evidence",
        "continuous_learning",
    ]
    workflow_policy: WorkflowPolicySettings


class ResearchSpaceSettings(TypedDict, total=False):
    """Type-safe research space settings."""

    auto_approve: bool
    require_review: bool
    review_threshold: float
    relation_default_review_threshold: float
    relation_review_thresholds: dict[str, float]
    relation_governance_mode: Literal["HUMAN_IN_LOOP", "FULL_AUTO"]
    relation_auto_promotion: RelationAutoPromotionSettings
    claim_non_persistable_baseline_ratio: float
    claim_non_persistable_alert_ratio: float
    dictionary_agent_creation_policy: Literal["ACTIVE", "PENDING_REVIEW"]
    concept_agent_creation_policy: Literal["ACTIVE", "PENDING_REVIEW"]
    concept_policy_mode: Literal["PRECISION", "BALANCED", "DISCOVERY"]
    ai_full_mode: AIFullModeSettings
    operating_mode: OperatingModeSettings
    max_data_sources: int
    allowed_source_types: list[str]
    sources: ResearchSpaceSourcePreferences
    public_read: bool
    allow_invites: bool
    email_notifications: bool
    notification_frequency: str
    custom: dict[str, str | int | float | bool | None]


__all__ = [
    "JSONObject",
    "JSONPrimitive",
    "JSONValue",
    "AIFullModeSettings",
    "OperatingModeSettings",
    "RelationAutoPromotionSettings",
    "ResearchSpaceSourcePreferences",
    "ResearchSpaceSettings",
    "WorkflowPolicySettings",
]
