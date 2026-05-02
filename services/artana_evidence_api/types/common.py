"""Common service-local types for graph-harness runtime code."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, TypedDict

JSONPrimitive = str | int | float | bool | None
type JSONValue = JSONPrimitive | Mapping[str, "JSONValue"] | Sequence["JSONValue"]
JSONObject = dict[str, JSONValue]


def json_object(value: object) -> JSONObject | None:
    """Return a JSON object when the runtime value has string keys."""
    if not isinstance(value, Mapping):
        return None
    payload: JSONObject = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            return None
        payload[raw_key] = json_value(raw_value)
    return payload


def json_object_or_empty(value: object) -> JSONObject:
    """Return a JSON object, or an empty object for non-object values."""
    return json_object(value) or {}


def json_array(value: object) -> list[JSONValue] | None:
    """Return a JSON array for non-string sequence values."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        return None
    return [json_value(item) for item in value]


def json_array_or_empty(value: object) -> list[JSONValue]:
    """Return a JSON array, or an empty array for non-array values."""
    return json_array(value) or []


def json_string_list(value: object) -> list[str]:
    """Return only string items from a JSON-ish sequence."""
    return [item for item in json_array_or_empty(value) if isinstance(item, str)]


def json_value(value: object) -> JSONValue:
    """Normalize an arbitrary runtime value into the service JSON type."""
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    object_value = json_object(value)
    if object_value is not None:
        return object_value
    array_value = json_array(value)
    if array_value is not None:
        return array_value
    return str(value)


def json_int(value: object, default: int = 0) -> int:
    """Read an integer from a JSON-ish scalar without accepting containers."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def json_float(value: object, default: float = 0.0) -> float:
    """Read a float from a JSON-ish scalar without accepting containers."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return default


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
    gnomad: bool
    uniprot: bool
    hgnc: bool
    clinical_trials: bool
    mgi: bool
    zfin: bool
    orphanet: bool


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
    "json_array",
    "json_array_or_empty",
    "json_float",
    "json_int",
    "json_object",
    "json_object_or_empty",
    "json_string_list",
    "json_value",
]
