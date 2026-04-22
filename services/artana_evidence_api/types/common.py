"""Common service-local types for graph-harness runtime code."""

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
    computational_min_distinct_sources: int
    computational_min_aggregate_confidence: float
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


class ResearchSpaceSettings(TypedDict, total=False):
    """Type-safe research space settings for harness workflows."""

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
    research_orchestration_mode: Literal[
        "deterministic",
        "full_ai_shadow",
        "full_ai_guarded",
    ]
    full_ai_guarded_rollout_profile: Literal[
        "guarded_dry_run",
        "guarded_chase_only",
        "guarded_source_chase",
        "guarded_low_risk",
    ]
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
    "RelationAutoPromotionSettings",
    "ResearchSpaceSourcePreferences",
    "ResearchSpaceSettings",
]
