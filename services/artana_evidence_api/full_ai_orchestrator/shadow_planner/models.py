"""Shared models and constants for the full-AI shadow planner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, TypedDict

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field

_PERCENT_PATTERN = re.compile(
    r"(\d+(\.\d+)?)\s*%|\b\d+(\.\d+)?\s*percent\b",
    re.IGNORECASE,
)
_CONFIDENCE_SCORE_PATTERN = re.compile(
    r"(\bconfidence\b[^\n]{0,24}\b\d+(\.\d+)?\b)|"
    r"(\b\d+(\.\d+)?\b[^\n]{0,24}\bconfidence\b)|"
    r"(\bscore\b[^\n]{0,16}\b\d+(\.\d+)?\b)|"
    r"(\b\d+(\.\d+)?\b[^\n]{0,16}\bscore\b)|"
    r"\bprobability\b",
    re.IGNORECASE,
)
_RANKING_NUMBER_PATTERN = re.compile(
    r"#\s*\d+|\brank(?:ed|ing)?\s*(?:number\s*)?\d+\b",
    re.IGNORECASE,
)
_NON_STRUCTURED_SOURCE_KEYS = frozenset(
    {"pubmed", "pdf", "text", "mondo", "uniprot", "hgnc"},
)
_LIVE_EVIDENCE_SOURCE_KEY_ORDER = (
    "pubmed",
    "clinvar",
    "drugbank",
    "alphafold",
    "clinical_trials",
    "mgi",
    "zfin",
    "marrvel",
)
_CONTEXT_ONLY_SOURCE_KEY_ORDER = ("pdf", "text")
_GROUNDING_SOURCE_KEY_ORDER = ("mondo",)
_RESERVED_SOURCE_KEY_ORDER = ("uniprot", "hgnc")
_STRUCTURED_ENRICHMENT_SOURCE_PREFERENCE = (
    "clinvar",
    "drugbank",
    "alphafold",
    "clinical_trials",
    "mgi",
    "zfin",
    "marrvel",
)
_PENDING_SOURCE_STATUSES = frozenset({"pending", "queued", "running", "deferred"})
_NON_PENDING_SOURCE_STATUSES = frozenset(
    {"completed", "failed", "skipped", "background"}
)
_PENDING_SOURCE_PREVIEW_LIMIT = 3
_MAX_CHASE_SELECTION_ENTITIES = 10
_MIN_OBJECTIVE_RELEVANCE_TERM_LENGTH = 3
_OBJECTIVE_RELEVANCE_STOPWORDS = frozenset(
    {
        "about",
        "across",
        "after",
        "against",
        "and",
        "between",
        "disease",
        "effect",
        "evidence",
        "for",
        "from",
        "gene",
        "genes",
        "how",
        "impact",
        "in",
        "into",
        "investigate",
        "of",
        "on",
        "or",
        "outcome",
        "pathway",
        "protein",
        "research",
        "response",
        "role",
        "study",
        "the",
        "therapy",
        "to",
        "treatment",
        "variant",
        "variants",
        "with",
    },
)
_PARP_INHIBITOR_OBJECTIVE_ALIASES = frozenset(
    {
        "olaparib",
        "niraparib",
        "rucaparib",
        "talazoparib",
        "veliparib",
        "parpi",
        "parpis",
    },
)
_REPAIRABLE_VALIDATION_ERRORS = frozenset(
    {
        "action_not_live",
        "source_key_required",
        "source_key_not_allowed",
        "unexpected_source_key",
        "pubmed_ingest_required",
        "terminal_stop_required",
        "numeric_style_ranking_not_allowed",
        "stop_reason_required",
        "chase_checkpoint_action_not_allowed",
        "chase_selection_required",
        "chase_selection_unknown_entity",
        "chase_selection_label_mismatch",
        "chase_selection_too_large",
        "objective_relevant_chase_required",
    },
)
_COST_SUMMARY_TYPES: tuple[str, ...] = ("trace::cost", "trace::cost_snapshot")
_COST_PAYLOAD_KEYS: tuple[str, ...] = (
    "total_cost",
    "cost_usd",
    "total_cost_usd",
    "model_cost",
)


class ShadowPlannerRecommendationOutput(BaseModel):
    """Structured planner recommendation used only in shadow mode."""

    model_config = ConfigDict(strict=True)

    action_type: ResearchOrchestratorActionType
    source_key: str | None = Field(default=None, min_length=1, max_length=64)
    evidence_basis: str = Field(..., min_length=1, max_length=4000)
    qualitative_rationale: str = Field(..., min_length=1, max_length=4000)
    expected_value_band: Literal["low", "medium", "high"] | None = None
    risk_level: Literal["low", "medium", "high"] | None = None
    requires_approval: bool = False
    budget_estimate: JSONObject | None = None
    stop_reason: str | None = Field(default=None, min_length=1, max_length=512)
    fallback_reason: str | None = Field(default=None, min_length=1, max_length=512)
    selected_entity_ids: list[str] = Field(default_factory=list, max_length=10)
    selected_labels: list[str] = Field(default_factory=list, max_length=10)
    selection_basis: str | None = Field(default=None, min_length=1, max_length=4000)


@dataclass(frozen=True, slots=True)
class ShadowPlannerRecommendationResult:
    """Final planner result plus transport metadata."""

    decision: ResearchOrchestratorDecision
    planner_status: str
    model_id: str | None
    agent_run_id: str
    prompt_version: str
    used_fallback: bool
    validation_error: str | None
    error: str | None
    initial_validation_error: str | None = None
    repair_attempted: bool = False
    repair_succeeded: bool = False
    telemetry: ShadowPlannerTelemetry | None = None


@dataclass(frozen=True, slots=True)
class ShadowPlannerTelemetry:
    """Aggregated Artana model-terminal telemetry for one planner checkpoint."""

    status: Literal["available", "partial", "unavailable"]
    model_terminal_count: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    latency_seconds: float | None = None
    tool_call_count: int = 0


class _PlannerConstraintsSummary(TypedDict):  # noqa: PYI049
    live_action_types: list[str]
    source_required_action_types: list[str]
    control_action_types_without_source_key: list[str]
    pubmed_source_key: str
    pubmed_ingest_pending: bool
    source_taxonomy: JSONObject
    structured_enrichment_source_keys: list[str]
    pending_structured_enrichment_source_keys: list[str]


class _ObjectiveRoutingHintsSummary(TypedDict):  # noqa: PYI049
    objective_tags: list[str]
    preferred_structured_sources: list[str]
    preferred_pending_structured_sources: list[str]
    summary: str


class _SynthesisReadinessSummary(TypedDict):  # noqa: PYI049
    ready_for_brief: bool
    chase_round_threshold_not_met: bool
    grounded_evidence_present: bool
    no_pending_questions: bool
    no_evidence_gaps: bool
    no_contradictions: bool
    no_errors: bool
    no_pending_structured_sources: bool
    pending_structured_source_keys: list[str]
    summary: str


def _default_stop_reason(
    *,
    action_type: ResearchOrchestratorActionType,
    checkpoint_key: str,
) -> str:
    if action_type is ResearchOrchestratorActionType.ESCALATE_TO_HUMAN:
        return "approval_or_uncertainty_required"
    if checkpoint_key == "before_terminal_stop":
        return "terminal_checkpoint"
    if checkpoint_key == "before_brief_generation":
        return "no_meaningful_next_action_before_brief"
    return "no_meaningful_next_action"


def _int_or_zero(value: object) -> int:
    return value if isinstance(value, int) else 0


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _comparison_reason(*, action_match: bool, source_match: bool) -> str:
    if action_match and source_match:
        return "Planner recommendation matches the deterministic next action."
    if action_match:
        return "Planner agreed on the action family but chose a different source."
    if source_match:
        return "Planner agreed on the source but chose a different action."
    return "Planner recommended a different action and source than the baseline."
