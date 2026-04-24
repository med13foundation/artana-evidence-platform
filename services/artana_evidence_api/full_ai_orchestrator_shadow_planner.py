"""Harness-backed shadow planner helpers for the full AI orchestrator."""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict, cast

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.runtime_support import (
    GovernanceConfig,
    ModelCapability,
    create_artana_postgres_store,
    get_model_registry,
    has_configured_openai_api_key,
    normalize_litellm_model_id,
    stable_sha256_digest,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_array_or_empty,
    json_int,
    json_object_or_empty,
    json_string_list,
    json_value,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

_PROMPT_PATH = (
    Path(__file__).resolve().parent
    / "prompts"
    / "full_ai_orchestrator_shadow_planner_v1.md"
)
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


class _PlannerConstraintsSummary(TypedDict):
    live_action_types: list[str]
    source_required_action_types: list[str]
    control_action_types_without_source_key: list[str]
    pubmed_source_key: str
    pubmed_ingest_pending: bool
    source_taxonomy: JSONObject
    structured_enrichment_source_keys: list[str]
    pending_structured_enrichment_source_keys: list[str]


class _ObjectiveRoutingHintsSummary(TypedDict):
    objective_tags: list[str]
    preferred_structured_sources: list[str]
    preferred_pending_structured_sources: list[str]
    summary: str


class _SynthesisReadinessSummary(TypedDict):
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


def _planner_source_taxonomy(
    *,
    enabled_sources: dict[str, bool],
) -> JSONObject:
    return {
        "live_evidence": [
            source_key
            for source_key in _LIVE_EVIDENCE_SOURCE_KEY_ORDER
            if enabled_sources.get(source_key, False)
        ],
        "context_only": [
            source_key
            for source_key in _CONTEXT_ONLY_SOURCE_KEY_ORDER
            if enabled_sources.get(source_key, False)
        ],
        "grounding": [
            source_key
            for source_key in _GROUNDING_SOURCE_KEY_ORDER
            if enabled_sources.get(source_key, False)
        ],
        "reserved": [
            source_key
            for source_key in _RESERVED_SOURCE_KEY_ORDER
            if enabled_sources.get(source_key, False)
        ],
    }


def _structured_enrichment_source_keys_from_taxonomy(
    *,
    source_taxonomy: JSONObject,
) -> list[str]:
    live_evidence_source_keys = _string_list(source_taxonomy.get("live_evidence"))
    return [
        source_key
        for source_key in _STRUCTURED_ENRICHMENT_SOURCE_PREFERENCE
        if source_key in live_evidence_source_keys
    ]


def _workspace_chase_candidates(
    *,
    workspace_summary: JSONObject,
) -> list[ResearchOrchestratorChaseCandidate]:
    chase_candidates = workspace_summary.get("chase_candidates")
    if not isinstance(chase_candidates, list):
        return []
    candidates: list[ResearchOrchestratorChaseCandidate] = []
    for candidate_payload in chase_candidates:
        if not isinstance(candidate_payload, dict):
            continue
        try:
            candidates.append(
                ResearchOrchestratorChaseCandidate.model_validate(candidate_payload),
            )
        except ValidationError:
            continue
    return candidates


def _workspace_chase_candidate_map(
    *,
    workspace_summary: JSONObject,
) -> dict[str, ResearchOrchestratorChaseCandidate]:
    return {
        candidate.entity_id: candidate
        for candidate in _workspace_chase_candidates(
            workspace_summary=workspace_summary
        )
    }


def _workspace_chase_selection(
    *,
    workspace_summary: JSONObject,
) -> ResearchOrchestratorChaseSelection | None:
    pending_chase_round = json_object_or_empty(
        workspace_summary.get("pending_chase_round"),
    )
    selection = json_object_or_empty(
        pending_chase_round.get("deterministic_selection"),
    )
    if not selection:
        selection = json_object_or_empty(workspace_summary.get("deterministic_selection"))
    if not selection:
        return None
    try:
        return ResearchOrchestratorChaseSelection.model_validate(selection)
    except Exception:  # noqa: BLE001
        return None


def _objective_relevance_terms(
    *,
    objective: str,
    seed_terms: object,
) -> set[str]:
    terms: set[str] = set()
    seed_texts = (
        [seed_term for seed_term in seed_terms if isinstance(seed_term, str)]
        if isinstance(seed_terms, list)
        else []
    )
    for seed_term in seed_texts:
        normalized_seed = _normalized_objective_text(seed_term)
        if len(normalized_seed) >= _MIN_OBJECTIVE_RELEVANCE_TERM_LENGTH:
            terms.add(normalized_seed)
        terms.update(_objective_relevance_tokens(seed_term))
    terms.update(_objective_relevance_tokens(objective))
    normalized_context = _normalized_objective_text(
        " ".join([objective, *seed_texts]),
    )
    if "parp" in terms and (
        "inhibitor" in terms
        or "inhibition" in terms
        or "parpi" in normalized_context
        or "parpis" in normalized_context
    ):
        terms.update(_PARP_INHIBITOR_OBJECTIVE_ALIASES)
    return terms


def _objective_relevance_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) >= _MIN_OBJECTIVE_RELEVANCE_TERM_LENGTH
        and token not in _OBJECTIVE_RELEVANCE_STOPWORDS
    }


def _normalized_objective_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _objective_relevant_chase_labels(
    *,
    workspace_summary: JSONObject,
) -> list[str]:
    objective = (
        str(workspace_summary.get("objective"))
        if isinstance(workspace_summary.get("objective"), str)
        else ""
    )
    relevance_terms = _objective_relevance_terms(
        objective=objective,
        seed_terms=workspace_summary.get("seed_terms"),
    )
    if not relevance_terms:
        return []

    selection = _workspace_chase_selection(workspace_summary=workspace_summary)
    selected_labels = list(selection.selected_labels) if selection is not None else []
    if not selected_labels:
        selected_labels = [
            candidate.display_label
            for candidate in _workspace_chase_candidates(
                workspace_summary=workspace_summary,
            )
        ]

    relevant_labels: list[str] = []
    for label in selected_labels:
        normalized_label = _normalized_objective_text(label)
        label_tokens = _objective_relevance_tokens(label)
        if any(
            term in label_tokens or (len(term.split()) > 1 and term in normalized_label)
            for term in relevance_terms
        ):
            relevant_labels.append(label)
    return relevant_labels


def _chase_decision_posture(
    *,
    workspace_summary: JSONObject,
) -> JSONObject:
    deterministic_threshold_met = bool(
        workspace_summary.get("deterministic_threshold_met"),
    )
    selection = _workspace_chase_selection(workspace_summary=workspace_summary)
    if selection is None or selection.stop_instead or not deterministic_threshold_met:
        return {
            "posture": "stop_threshold_not_met",
            "basis": (
                "The deterministic chase baseline did not produce a continuing "
                "selection for this checkpoint."
            ),
            "objective_relevant_labels": [],
        }

    relevant_labels = _objective_relevant_chase_labels(
        workspace_summary=workspace_summary,
    )
    if relevant_labels:
        return {
            "posture": "continue_objective_relevant",
            "basis": (
                "The deterministic chase threshold is met and at least one selected "
                "candidate directly overlaps the objective or seed terms."
            ),
            "objective_relevant_labels": relevant_labels[
                :_MAX_CHASE_SELECTION_ENTITIES
            ],
        }
    return {
        "posture": "planner_discretion",
        "basis": (
            "The deterministic chase threshold is met, but the selected labels do "
            "not directly overlap objective or seed terms."
        ),
        "objective_relevant_labels": [],
    }


def _chase_decision_posture_value(
    *,
    workspace_summary: JSONObject,
) -> str:
    posture_payload = workspace_summary.get("chase_decision_posture")
    if isinstance(posture_payload, dict) and isinstance(
        posture_payload.get("posture"),
        str,
    ):
        return str(posture_payload["posture"])
    return str(
        _chase_decision_posture(workspace_summary=workspace_summary).get("posture"),
    )


def load_shadow_planner_prompt() -> str:
    """Return the versioned shadow planner system prompt."""

    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def shadow_planner_prompt_version() -> str:
    """Return a stable prompt version digest for metadata and evaluation."""

    return stable_sha256_digest(load_shadow_planner_prompt(), length=16)


def planner_action_registry_by_state(
    *,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> dict[str, list[JSONObject]]:
    """Group the action registry by planner visibility state."""

    grouped: dict[str, list[JSONObject]] = {
        "live": [],
        "context_only": [],
        "reserved": [],
    }
    for spec in action_registry:
        grouped[spec.planner_state].append(spec.model_dump(mode="json"))
    return grouped


def planner_live_action_types(
    *,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> frozenset[ResearchOrchestratorActionType]:
    """Return planner-selectable action types."""

    return frozenset(
        spec.action_type for spec in action_registry if spec.planner_state == "live"
    )


def _checkpoint_live_action_specs(
    *,
    checkpoint_key: str,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> tuple[ResearchOrchestratorActionSpec, ...]:
    live_specs = tuple(spec for spec in action_registry if spec.planner_state == "live")
    if checkpoint_key in {"after_bootstrap", "after_chase_round_1"}:
        return tuple(
            spec
            for spec in live_specs
            if spec.action_type
            in {
                ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                ResearchOrchestratorActionType.STOP,
            }
        )
    return live_specs


def _structured_enrichment_source_keys(
    *,
    enabled_sources: dict[str, bool],
) -> list[str]:
    source_taxonomy = _planner_source_taxonomy(enabled_sources=enabled_sources)
    structured_source_keys = _structured_enrichment_source_keys_from_taxonomy(
        source_taxonomy=source_taxonomy,
    )
    structured_source_set = set(structured_source_keys)
    remaining_sources = sorted(
        source_key
        for source_key in json_string_list(source_taxonomy.get("live_evidence"))
        if source_key != "pubmed" and source_key not in structured_source_set
    )
    return [*structured_source_keys, *remaining_sources]


def _pubmed_ingest_pending(
    *,
    source_status_summary: JSONObject,
) -> bool:
    pubmed_summary = source_status_summary.get("pubmed")
    if not isinstance(pubmed_summary, dict):
        return False
    documents_discovered = _int_or_zero(pubmed_summary.get("documents_discovered"))
    documents_selected = _int_or_zero(pubmed_summary.get("documents_selected"))
    documents_ingested = _int_or_zero(pubmed_summary.get("documents_ingested"))
    if documents_selected > documents_ingested:
        return True
    return documents_discovered > 0 and documents_ingested == 0


def _objective_routing_tags(objective: str) -> list[str]:
    lowered = objective.casefold()
    tags: list[str] = []
    if any(
        token in lowered
        for token in (
            "drug",
            "therapy",
            "therapeut",
            "treatment",
            "inhibitor",
            "response",
            "repurpos",
            "target",
        )
    ):
        tags.append("drug_mechanism")
    if any(
        token in lowered
        for token in (
            "trial",
            "study",
            "studies",
            "recruit",
            "enrollment",
            "intervention",
            "outcome",
            "human",
        )
    ):
        tags.append("trial_evidence")
    if any(
        token in lowered
        for token in (
            "variant",
            "mutation",
            "pathogenic",
            "allele",
            "clinvar",
        )
    ):
        tags.append("variant_interpretation")
    if any(
        token in lowered
        for token in (
            "structure",
            "structural",
            "fold",
            "domain",
            "interface",
            "protein",
        )
    ):
        tags.append("protein_structure")
    if any(
        token in lowered
        for token in (
            "development",
            "developmental",
            "congenital",
            "phenotype",
            "syndrome",
            "model organism",
            "mouse",
            "mice",
            "zebrafish",
        )
    ):
        tags.append("model_organism")
    return tags


def _objective_preferred_structured_sources(
    *,
    objective: str,
    structured_enrichment_sources: list[str],
) -> list[str]:
    tags = _objective_routing_tags(objective)
    preferred_sources: list[str] = []
    if "trial_evidence" in tags:
        preferred_sources.extend(("clinical_trials", "drugbank"))
    if "drug_mechanism" in tags:
        preferred_sources.extend(("drugbank", "clinical_trials"))
    if "variant_interpretation" in tags:
        preferred_sources.extend(("clinvar", "alphafold", "marrvel"))
    if "protein_structure" in tags:
        preferred_sources.extend(("alphafold", "clinvar"))
    if "model_organism" in tags:
        preferred_sources.extend(("marrvel", "mgi", "zfin", "clinvar"))

    ordered_sources: list[str] = []
    seen_sources: set[str] = set()
    for source_key in [*preferred_sources, *structured_enrichment_sources]:
        if (
            source_key in structured_enrichment_sources
            and source_key not in seen_sources
        ):
            ordered_sources.append(source_key)
            seen_sources.add(source_key)
    return ordered_sources


def _structured_enrichment_pending_source_keys(
    *,
    workspace_summary: JSONObject,
    structured_enrichment_sources: list[str],
) -> list[str]:
    source_status_summary = workspace_summary.get("source_status_summary")
    source_status_lookup = (
        source_status_summary if isinstance(source_status_summary, dict) else {}
    )
    completed_sources: set[str] = set()
    for source_key, summary in source_status_lookup.items():
        if not isinstance(source_key, str) or not isinstance(summary, dict):
            continue
        raw_status = summary.get("status")
        if not isinstance(raw_status, str):
            continue
        if raw_status.casefold() in _NON_PENDING_SOURCE_STATUSES:
            completed_sources.add(source_key)

    for decision in _workspace_prior_decisions(workspace_summary):
        if not _matches_action_type(
            decision.get("action_type"),
            ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
        ):
            continue
        source_key = decision.get("source_key")
        if not isinstance(source_key, str):
            continue
        decision_status = decision.get("status")
        if isinstance(decision_status, str) and (
            decision_status.casefold() in _NON_PENDING_SOURCE_STATUSES
        ):
            completed_sources.add(source_key)

    pending_sources: list[str] = []
    for source_key in structured_enrichment_sources:
        source_summary = source_status_lookup.get(source_key)
        raw_status = (
            source_summary.get("status") if isinstance(source_summary, dict) else None
        )
        normalized_status = (
            raw_status.casefold() if isinstance(raw_status, str) else None
        )
        if normalized_status in _NON_PENDING_SOURCE_STATUSES:
            continue
        if (
            normalized_status in _PENDING_SOURCE_STATUSES
            or source_key not in completed_sources
        ):
            pending_sources.append(source_key)
    return pending_sources


def _objective_routing_hints(
    *,
    objective: str,
    structured_enrichment_sources: list[str],
    pending_structured_sources: list[str],
) -> _ObjectiveRoutingHintsSummary:
    objective_tags = _objective_routing_tags(objective)
    preferred_structured_sources = _objective_preferred_structured_sources(
        objective=objective,
        structured_enrichment_sources=structured_enrichment_sources,
    )
    preferred_pending_structured_sources = [
        source_key
        for source_key in preferred_structured_sources
        if source_key in pending_structured_sources
    ]
    if not preferred_pending_structured_sources:
        preferred_pending_structured_sources = list(pending_structured_sources)

    summary = (
        "No special objective routing hint was detected, so once the run reaches "
        "structured enrichment it should fall back to the deterministic "
        "structured-source order."
    )
    if "trial_evidence" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "trial activity or intervention evidence, so human-study sources should "
            "lead the remaining structured follow-up."
        )
    elif "drug_mechanism" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "therapy or inhibitor questions, so drug and target mechanism sources "
            "should lead the remaining structured follow-up."
        )
    elif "model_organism" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "developmental or phenotype context, so model organism sources should "
            "lead the remaining structured follow-up."
        )
    elif "variant_interpretation" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "variant interpretation, so ClinVar-style evidence should lead the "
            "remaining structured follow-up."
        )
    elif "protein_structure" in objective_tags:
        summary = (
            "Once the run reaches structured enrichment, the objective emphasizes "
            "protein structure or domain context, so structure-grounded sources "
            "should lead the remaining structured follow-up."
        )

    return {
        "objective_tags": objective_tags,
        "preferred_structured_sources": preferred_structured_sources,
        "preferred_pending_structured_sources": preferred_pending_structured_sources,
        "summary": summary,
    }


def _checkpoint_objective_routing_hints(
    *,
    checkpoint_key: str,
    objective: str,
    structured_enrichment_sources: list[str],
    pending_structured_sources: list[str],
    pubmed_ingest_pending: bool,
) -> _ObjectiveRoutingHintsSummary:
    hints = _objective_routing_hints(
        objective=objective,
        structured_enrichment_sources=structured_enrichment_sources,
        pending_structured_sources=pending_structured_sources,
    )
    if checkpoint_key in {"after_pubmed_ingest_extract", "after_driven_terms_ready"}:
        return hints
    if checkpoint_key == "after_pubmed_discovery" and pubmed_ingest_pending:
        return {
            **hints,
            "preferred_pending_structured_sources": [],
            "summary": (
                "Structured-source routing hints are recorded for later, but they "
                "stay inactive until PubMed ingest and extraction are complete."
            ),
        }
    return {
        **hints,
        "preferred_pending_structured_sources": [],
        "summary": (
            "Structured-source routing hints are recorded for later checkpoints and "
            "should not drive the current step selection yet."
        ),
    }


def _workspace_prior_decisions(workspace_summary: JSONObject) -> list[JSONObject]:
    raw_prior_decisions = workspace_summary.get("prior_decisions")
    if not isinstance(raw_prior_decisions, list):
        return []
    return [
        cast("JSONObject", decision)
        for decision in raw_prior_decisions
        if isinstance(decision, dict)
    ]


def _matches_action_type(
    raw_action_type: object,
    action_type: ResearchOrchestratorActionType,
) -> bool:
    return raw_action_type in {action_type, action_type.value}


def _preferred_structured_enrichment_source_from_workspace(
    *,
    workspace_summary: JSONObject,
    structured_enrichment_sources: list[str],
) -> str | None:
    objective_routing_hints = _workspace_objective_routing_hints(
        workspace_summary=workspace_summary,
    )
    for source_key in objective_routing_hints["preferred_pending_structured_sources"]:
        if source_key in structured_enrichment_sources:
            return source_key
    pending_sources = _structured_enrichment_pending_source_keys(
        workspace_summary=workspace_summary,
        structured_enrichment_sources=structured_enrichment_sources,
    )
    if pending_sources:
        return pending_sources[0]
    if structured_enrichment_sources:
        return structured_enrichment_sources[0]
    return None


def _chase_round_threshold_not_met(workspace_summary: JSONObject) -> bool:
    for decision in _workspace_prior_decisions(workspace_summary):
        if not _matches_action_type(
            decision.get("action_type"),
            ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        ):
            continue
        if decision.get("status") != "skipped":
            continue
        if decision.get("stop_reason") == "threshold_not_met":
            return True
    return False


def shadow_planner_synthesis_readiness(
    *,
    workspace_summary: JSONObject,
) -> _SynthesisReadinessSummary:
    """Summarize whether the workspace is ready to move to synthesis."""

    counts = json_object_or_empty(workspace_summary.get("counts"))
    documents_ingested = _int_or_zero(counts.get("documents_ingested"))
    proposal_count = _int_or_zero(counts.get("proposal_count"))
    pending_question_count = _int_or_zero(counts.get("pending_question_count"))
    evidence_gap_count = _int_or_zero(counts.get("evidence_gap_count"))
    contradiction_count = _int_or_zero(counts.get("contradiction_count"))
    error_count = _int_or_zero(counts.get("error_count"))
    pending_structured_source_keys = (
        _workspace_pending_structured_enrichment_source_keys(
            workspace_summary=workspace_summary,
        )
    )
    grounded_evidence_present = documents_ingested > 0 and proposal_count > 0
    no_pending_questions = pending_question_count == 0
    no_evidence_gaps = evidence_gap_count == 0
    no_contradictions = contradiction_count == 0
    no_errors = error_count == 0
    no_pending_structured_sources = len(pending_structured_source_keys) == 0
    chase_round_threshold_not_met = _chase_round_threshold_not_met(workspace_summary)
    ready_for_brief = (
        grounded_evidence_present
        and no_pending_questions
        and no_evidence_gaps
        and no_contradictions
        and no_errors
        and no_pending_structured_sources
    )
    if chase_round_threshold_not_met:
        summary = (
            "A chase round was already skipped because the threshold was not met, so "
            "the workflow should synthesize instead of opening another chase round."
        )
    elif ready_for_brief:
        summary = (
            "Grounded evidence is already present, structured enrichment is exhausted, "
            "and there are no recorded pending questions, evidence gaps, "
            "contradictions, or errors."
        )
    else:
        missing_signals: list[str] = []
        if not grounded_evidence_present:
            missing_signals.append("grounded evidence is still limited")
        if not no_pending_structured_sources:
            pending_text = ", ".join(
                pending_structured_source_keys[:_PENDING_SOURCE_PREVIEW_LIMIT]
            )
            if len(pending_structured_source_keys) > _PENDING_SOURCE_PREVIEW_LIMIT:
                pending_text = f"{pending_text}, ..."
            missing_signals.append(
                f"structured sources remain pending ({pending_text})",
            )
        if not no_pending_questions:
            missing_signals.append("pending questions remain open")
        if not no_evidence_gaps:
            missing_signals.append("evidence gaps remain open")
        if not no_contradictions:
            missing_signals.append("active contradictions still need review")
        if not no_errors:
            missing_signals.append("errors are still recorded in the workspace")
        blockers_text = (
            "; ".join(missing_signals)
            or "another bounded retrieval step may still help"
        )
        summary = (
            "Another bounded retrieval step still has qualitative value because "
            f"{blockers_text}."
        )
    return {
        "ready_for_brief": ready_for_brief,
        "chase_round_threshold_not_met": chase_round_threshold_not_met,
        "grounded_evidence_present": grounded_evidence_present,
        "no_pending_questions": no_pending_questions,
        "no_evidence_gaps": no_evidence_gaps,
        "no_contradictions": no_contradictions,
        "no_errors": no_errors,
        "no_pending_structured_sources": no_pending_structured_sources,
        "pending_structured_source_keys": pending_structured_source_keys,
        "summary": summary,
    }


def build_shadow_planner_workspace_summary(  # noqa: PLR0913
    *,
    checkpoint_key: str,
    mode: str = "shadow",
    objective: str,
    seed_terms: list[str],
    sources: ResearchSpaceSourcePreferences,
    max_depth: int,
    max_hypotheses: int,
    workspace_snapshot: JSONObject,
    prior_decisions: list[JSONObject],
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> JSONObject:
    """Build the planner-readable workspace snapshot for one planner mode."""

    source_results = workspace_snapshot.get("source_results")
    enabled_sources = {
        key: value for key, value in sources.items() if isinstance(value, bool)
    }
    source_taxonomy = _planner_source_taxonomy(enabled_sources=enabled_sources)
    checkpoint_round = workspace_snapshot.get("current_round", 0)
    source_status_summary: JSONObject = {}
    if isinstance(source_results, dict):
        for source_key, source_summary in source_results.items():
            if not isinstance(source_key, str) or not isinstance(source_summary, dict):
                continue
            source_status_summary[source_key] = {
                "status": source_summary.get("status"),
                "documents_discovered": source_summary.get("documents_discovered"),
                "documents_selected": source_summary.get("documents_selected"),
                "documents_ingested": source_summary.get("documents_ingested"),
                "records_processed": source_summary.get("records_processed"),
                "observations_created": source_summary.get("observations_created"),
            }

    pending_questions = workspace_snapshot.get("pending_questions")
    errors = workspace_snapshot.get("errors")
    evidence_gaps = workspace_snapshot.get("evidence_gaps")
    contradictions = workspace_snapshot.get("contradictions")
    grouped_actions = planner_action_registry_by_state(action_registry=action_registry)
    checkpoint_live_specs = _checkpoint_live_action_specs(
        checkpoint_key=checkpoint_key,
        action_registry=action_registry,
    )
    live_action_types = [spec.action_type.value for spec in checkpoint_live_specs]
    source_required_action_types = [
        spec.action_type.value for spec in checkpoint_live_specs if spec.source_bound
    ]
    control_action_types_without_source_key = [
        spec.action_type.value
        for spec in checkpoint_live_specs
        if not spec.source_bound
    ]
    structured_enrichment_source_keys = _structured_enrichment_source_keys(
        enabled_sources=enabled_sources,
    )
    pending_structured_enrichment_source_keys = (
        _structured_enrichment_pending_source_keys(
            workspace_summary=workspace_snapshot,
            structured_enrichment_sources=structured_enrichment_source_keys,
        )
    )
    pubmed_ingest_pending = _pubmed_ingest_pending(
        source_status_summary=source_status_summary,
    )
    objective_routing_hints = _checkpoint_objective_routing_hints(
        checkpoint_key=checkpoint_key,
        objective=objective,
        structured_enrichment_sources=structured_enrichment_source_keys,
        pending_structured_sources=pending_structured_enrichment_source_keys,
        pubmed_ingest_pending=pubmed_ingest_pending,
    )
    pending_chase_round = json_object_or_empty(
        workspace_snapshot.get("pending_chase_round"),
    )
    chase_candidates = json_array_or_empty(pending_chase_round.get("chase_candidates"))
    filtered_chase_candidates = json_array_or_empty(
        pending_chase_round.get("filtered_chase_candidates"),
    )
    deterministic_chase_threshold = (
        json_int(pending_chase_round.get("deterministic_chase_threshold"))
        if isinstance(pending_chase_round.get("deterministic_chase_threshold"), int)
        else 0
    )
    deterministic_candidate_count = (
        json_int(pending_chase_round.get("deterministic_candidate_count"))
        if isinstance(pending_chase_round.get("deterministic_candidate_count"), int)
        else 0
    )
    deterministic_threshold_met = bool(
        pending_chase_round.get("deterministic_threshold_met"),
    )
    available_chase_source_keys = json_string_list(
        pending_chase_round.get("available_chase_source_keys"),
    )
    filtered_chase_candidate_count = (
        json_int(pending_chase_round.get("filtered_chase_candidate_count"))
        if isinstance(pending_chase_round.get("filtered_chase_candidate_count"), int)
        else 0
    )
    filtered_chase_filter_reason_counts = json_object_or_empty(
        pending_chase_round.get("filtered_chase_filter_reason_counts"),
    )
    deterministic_selection = json_object_or_empty(
        pending_chase_round.get("deterministic_selection"),
    )

    summary: JSONObject = {
        "mode": mode,
        "checkpoint_key": checkpoint_key,
        "objective": objective,
        "seed_terms": list(seed_terms),
        "enabled_sources": enabled_sources,
        "current_round": checkpoint_round if isinstance(checkpoint_round, int) else 0,
        "counts": {
            "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
            "proposal_count": workspace_snapshot.get("proposal_count", 0),
            "pending_question_count": (
                len(pending_questions) if isinstance(pending_questions, list) else 0
            ),
            "error_count": len(errors) if isinstance(errors, list) else 0,
            "evidence_gap_count": (
                len(evidence_gaps) if isinstance(evidence_gaps, list) else 0
            ),
            "contradiction_count": (
                len(contradictions) if isinstance(contradictions, list) else 0
            ),
        },
        "source_status_summary": source_status_summary,
        "top_evidence_gaps": (
            list(evidence_gaps[:5]) if isinstance(evidence_gaps, list) else []
        ),
        "active_contradictions": (
            list(contradictions[:5]) if isinstance(contradictions, list) else []
        ),
        "prior_decisions": list(prior_decisions[-10:]),
        "remaining_hard_limits": {
            "max_total_rounds": min(max_depth, 2) + 1,
            "max_chase_rounds": min(max_depth, 2),
            "max_hypotheses": max_hypotheses,
        },
        "source_taxonomy": source_taxonomy,
        "chase_candidates": chase_candidates,
        "filtered_chase_candidates": filtered_chase_candidates,
        "deterministic_chase_threshold": deterministic_chase_threshold,
        "deterministic_candidate_count": deterministic_candidate_count,
        "filtered_chase_candidate_count": filtered_chase_candidate_count,
        "filtered_chase_filter_reason_counts": filtered_chase_filter_reason_counts,
        "deterministic_threshold_met": deterministic_threshold_met,
        "available_chase_source_keys": available_chase_source_keys,
        "deterministic_selection": deterministic_selection,
        "planner_actions": grouped_actions,
        "planner_constraints": {
            "live_action_types": live_action_types,
            "source_required_action_types": source_required_action_types,
            "control_action_types_without_source_key": (
                control_action_types_without_source_key
            ),
            "pubmed_source_key": "pubmed",
            "pubmed_ingest_pending": pubmed_ingest_pending,
            "source_taxonomy": source_taxonomy,
            "structured_enrichment_source_keys": structured_enrichment_source_keys,
            "pending_structured_enrichment_source_keys": (
                pending_structured_enrichment_source_keys
            ),
        },
        "objective_routing_hints": json_value(objective_routing_hints),
    }
    summary["chase_decision_posture"] = _chase_decision_posture(
        workspace_summary=summary,
    )
    summary["synthesis_readiness"] = json_value(
        shadow_planner_synthesis_readiness(
            workspace_summary=summary,
        ),
    )
    return summary


async def recommend_shadow_planner_action(  # noqa: PLR0913, PLR0915
    *,
    checkpoint_key: str,
    objective: str,
    workspace_summary: JSONObject,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
    harness_id: str,
    step_key_version: str,
) -> ShadowPlannerRecommendationResult:
    """Recommend the next action while leaving execution to the baseline."""

    prompt_version = shadow_planner_prompt_version()
    normalized_workspace_summary = _normalize_shadow_planner_workspace_summary(
        checkpoint_key=checkpoint_key,
        objective=objective,
        workspace_summary=workspace_summary,
        sources=sources,
        action_registry=action_registry,
    )
    fallback_output = _build_fallback_output(
        checkpoint_key=checkpoint_key,
        workspace_summary=normalized_workspace_summary,
        sources=sources,
        action_registry=action_registry,
    )
    agent_run_id = _build_agent_run_id(
        objective=objective,
        checkpoint_key=checkpoint_key,
        workspace_summary=normalized_workspace_summary,
    )
    telemetry = _unavailable_shadow_planner_telemetry()
    if not has_configured_openai_api_key():
        return ShadowPlannerRecommendationResult(
            decision=_build_shadow_decision(
                output=fallback_output,
                checkpoint_key=checkpoint_key,
                planner_status="unavailable",
                model_id=None,
                agent_run_id=agent_run_id,
                prompt_version=prompt_version,
                harness_id=harness_id,
                step_key_version=step_key_version,
                telemetry=telemetry,
            ),
            planner_status="unavailable",
            model_id=None,
            agent_run_id=agent_run_id,
            prompt_version=prompt_version,
            used_fallback=True,
            validation_error=None,
            error=None,
            telemetry=telemetry,
        )

    store = None
    kernel = None
    model_id: str | None = None
    repair_run_id: str | None = None
    initial_validation_error: str | None = None
    repair_attempted = False
    repair_succeeded = False
    try:
        from artana.harness import StrongModelAgentHarness
        from artana.kernel import ArtanaKernel
        from artana.models import TenantContext
        from artana.ports.model import LiteLLMAdapter

        registry = get_model_registry()
        model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
        model_id = normalize_litellm_model_id(model_spec.model_id)
        timeout_seconds = float(model_spec.timeout_seconds)
        budget_limit = GovernanceConfig.from_environment().usage_limits.total_cost_usd
        tenant = TenantContext(
            tenant_id="full_ai_orchestrator_shadow_planner",
            capabilities=frozenset(),
            budget_usd_limit=max(float(budget_limit or 0.25), 0.01),
        )
        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(timeout_seconds=timeout_seconds),
        )
        harness = StrongModelAgentHarness(
            kernel=kernel,
            tenant=tenant,
            default_model=model_id,
            draft_model=model_id,
            verify_model=model_id,
            replay_policy="fork_on_drift",
            agent_system_prompt=load_shadow_planner_prompt(),
            max_iterations=2,
        )
        output_schema = _build_shadow_planner_output_schema(
            checkpoint_key=checkpoint_key,
            action_registry=action_registry,
        )
        output = await harness.run_agent(
            run_id=agent_run_id,
            prompt=_build_shadow_planner_prompt(
                workspace_summary=normalized_workspace_summary
            ),
            output_schema=output_schema,
            workspace_aware=False,
        )
        output = _coerce_shadow_planner_output(output)
        output = _normalize_shadow_planner_output(
            output=output,
            workspace_summary=normalized_workspace_summary,
            sources=sources,
            action_registry=action_registry,
        )
        validation_error = validate_shadow_planner_output(
            output=output,
            workspace_summary=normalized_workspace_summary,
            sources=sources,
            action_registry=action_registry,
        )
        initial_validation_error = validation_error
        if validation_error in _REPAIRABLE_VALIDATION_ERRORS:
            repair_attempted = True
            repair_run_id = f"{agent_run_id}:repair"
            repaired_output = await harness.run_agent(
                run_id=repair_run_id,
                prompt=_build_shadow_planner_repair_prompt(
                    workspace_summary=normalized_workspace_summary,
                    invalid_output=output,
                    validation_error=validation_error,
                ),
                output_schema=output_schema,
                workspace_aware=False,
            )
            output = _coerce_shadow_planner_output(repaired_output)
            output = _normalize_shadow_planner_output(
                output=output,
                workspace_summary=normalized_workspace_summary,
                sources=sources,
                action_registry=action_registry,
            )
            validation_error = validate_shadow_planner_output(
                output=output,
                workspace_summary=normalized_workspace_summary,
                sources=sources,
                action_registry=action_registry,
            )
            repair_succeeded = validation_error is None
        telemetry = await _collect_shadow_planner_telemetry(
            store=store,
            run_ids=tuple(
                run_id
                for run_id in (agent_run_id, repair_run_id)
                if isinstance(run_id, str)
            ),
        )
        planner_status = "completed" if validation_error is None else "invalid"
        if validation_error is not None:
            output = fallback_output.model_copy(
                update={"fallback_reason": validation_error},
            )
        return ShadowPlannerRecommendationResult(
            decision=_build_shadow_decision(
                output=output,
                checkpoint_key=checkpoint_key,
                planner_status=planner_status,
                model_id=model_id,
                agent_run_id=agent_run_id,
                prompt_version=prompt_version,
                harness_id=harness_id,
                step_key_version=step_key_version,
                initial_validation_error=initial_validation_error,
                repair_attempted=repair_attempted,
                repair_succeeded=repair_succeeded,
                telemetry=telemetry,
            ),
            planner_status=planner_status,
            model_id=model_id,
            agent_run_id=agent_run_id,
            prompt_version=prompt_version,
            used_fallback=validation_error is not None,
            validation_error=validation_error,
            error=None,
            initial_validation_error=initial_validation_error,
            repair_attempted=repair_attempted,
            repair_succeeded=repair_succeeded,
            telemetry=telemetry,
        )
    except Exception as exc:  # noqa: BLE001
        telemetry = await _collect_shadow_planner_telemetry(
            store=store,
            run_ids=tuple(
                run_id
                for run_id in (agent_run_id, repair_run_id)
                if isinstance(run_id, str)
            ),
        )
        return ShadowPlannerRecommendationResult(
            decision=_build_shadow_decision(
                output=fallback_output.model_copy(
                    update={"fallback_reason": "shadow_planner_execution_failed"},
                ),
                checkpoint_key=checkpoint_key,
                planner_status="failed",
                model_id=model_id,
                agent_run_id=agent_run_id,
                prompt_version=prompt_version,
                harness_id=harness_id,
                step_key_version=step_key_version,
                telemetry=telemetry,
            ),
            planner_status="failed",
            model_id=model_id,
            agent_run_id=agent_run_id,
            prompt_version=prompt_version,
            used_fallback=True,
            validation_error=None,
            error=str(exc),
            initial_validation_error=initial_validation_error,
            repair_attempted=repair_attempted,
            repair_succeeded=repair_succeeded,
            telemetry=telemetry,
        )
    finally:
        if kernel is not None:
            with suppress(Exception):
                await kernel.close()
        if store is not None:
            with suppress(Exception):
                await store.close()


def validate_shadow_planner_output(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject | None = None,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> str | None:
    """Return a validation error when the planner output is not acceptable."""

    action_spec = next(
        (spec for spec in action_registry if spec.action_type == output.action_type),
        None,
    )
    live_types = planner_live_action_types(action_registry=action_registry)
    validations = (
        _validate_allowlisted_action(
            action_spec=action_spec,
            output=output,
            live_types=live_types,
        ),
        _validate_action_source(
            action_spec=action_spec,
            output=output,
            sources=sources,
        ),
        _validate_checkpoint_stage_semantics(
            output=output,
            workspace_summary=workspace_summary or {},
        ),
        _validate_chase_selection(
            output=output,
            workspace_summary=workspace_summary or {},
        ),
        _validate_stop_reason(output=output),
        _validate_qualitative_rationale(output=output),
    )
    for error in validations:
        if error is not None:
            return error
    return None


def _build_shadow_planner_output_schema(
    *,
    checkpoint_key: str,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> type[BaseModel]:
    live_action_types = tuple(
        spec.action_type
        for spec in _checkpoint_live_action_specs(
            checkpoint_key=checkpoint_key,
            action_registry=action_registry,
        )
    )
    if not live_action_types:
        return ShadowPlannerRecommendationOutput
    action_literal = Literal.__getitem__(live_action_types)
    return cast(
        "type[BaseModel]",
        create_model(
            "ShadowPlannerLiveRecommendationOutput",
            __base__=ShadowPlannerRecommendationOutput,
            action_type=(action_literal, ...),
        ),
    )


def _coerce_shadow_planner_output(output: object) -> ShadowPlannerRecommendationOutput:
    if isinstance(output, BaseModel):
        return ShadowPlannerRecommendationOutput.model_validate(
            output.model_dump(mode="python"),
        )
    return ShadowPlannerRecommendationOutput.model_validate(output)


def _normalize_shadow_planner_output(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> ShadowPlannerRecommendationOutput:
    action_spec = next(
        (spec for spec in action_registry if spec.action_type == output.action_type),
        None,
    )
    if action_spec is None:
        return output

    updates: JSONObject = {}
    if (
        output.source_key is None
        and action_spec.default_source_key is not None
        and sources.get(action_spec.default_source_key, False)
    ):
        updates["source_key"] = action_spec.default_source_key

    if (
        output.action_type is ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT
        and output.source_key is None
    ):
        structured_sources = _workspace_structured_enrichment_source_keys(
            workspace_summary=workspace_summary,
        )
        if len(structured_sources) == 1 and sources.get(structured_sources[0], False):
            updates["source_key"] = structured_sources[0]

    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        else ""
    )
    if output.action_type in {
        ResearchOrchestratorActionType.STOP,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
    } and (output.stop_reason is None or output.stop_reason.strip() == ""):
        updates["stop_reason"] = _default_stop_reason(
            action_type=output.action_type,
            checkpoint_key=checkpoint_key,
        )

    if not updates:
        return output
    return output.model_copy(update=updates)


def _contains_forbidden_numeric_style(text: str) -> bool:
    normalized = text.strip()
    if normalized == "":
        return False
    return any(
        pattern.search(normalized) is not None
        for pattern in (
            _PERCENT_PATTERN,
            _CONFIDENCE_SCORE_PATTERN,
            _RANKING_NUMBER_PATTERN,
        )
    )


def _validate_allowlisted_action(
    *,
    action_spec: ResearchOrchestratorActionSpec | None,
    output: ShadowPlannerRecommendationOutput,
    live_types: frozenset[ResearchOrchestratorActionType],
) -> str | None:
    if action_spec is None:
        return "action_not_allowlisted"
    if output.action_type not in live_types:
        return "action_not_live"
    return None


def _validate_action_source(
    *,
    action_spec: ResearchOrchestratorActionSpec | None,
    output: ShadowPlannerRecommendationOutput,
    sources: ResearchSpaceSourcePreferences,
) -> str | None:
    if action_spec is None:
        return None
    if action_spec.source_bound and output.source_key is None:
        return "source_key_required"
    if not action_spec.source_bound and output.source_key is not None:
        return "source_key_not_allowed"
    if (
        action_spec.default_source_key is not None
        and output.source_key is not None
        and output.source_key != action_spec.default_source_key
    ):
        return "unexpected_source_key"
    if output.source_key is not None and not sources.get(output.source_key, False):
        return "source_disabled"
    return None


def _validate_checkpoint_stage_semantics(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject,
) -> str | None:
    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        and str(workspace_summary.get("checkpoint_key")).strip()
        else None
    )
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    if (
        checkpoint_key == "after_pubmed_discovery"
        and planner_constraints["pubmed_ingest_pending"]
        and output.action_type
        is not ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED
    ):
        return "pubmed_ingest_required"
    if checkpoint_key == "before_terminal_stop" and output.action_type not in {
        ResearchOrchestratorActionType.STOP,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
    }:
        return "terminal_stop_required"
    return None


def _validate_stop_reason(
    *,
    output: ShadowPlannerRecommendationOutput,
) -> str | None:
    if output.action_type not in {
        ResearchOrchestratorActionType.STOP,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
    }:
        return None
    if output.stop_reason is None or output.stop_reason.strip() == "":
        return "stop_reason_required"
    return None


def _validate_chase_selection(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject,
) -> str | None:
    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        else ""
    )
    if checkpoint_key not in {"after_bootstrap", "after_chase_round_1"}:
        return None
    if output.action_type not in {
        ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        ResearchOrchestratorActionType.STOP,
    }:
        return "chase_checkpoint_action_not_allowed"
    if output.action_type is ResearchOrchestratorActionType.STOP:
        if (
            _chase_decision_posture_value(workspace_summary=workspace_summary)
            == "continue_objective_relevant"
        ):
            return "objective_relevant_chase_required"
        return (
            None
            if output.stop_reason is not None and output.stop_reason.strip() != ""
            else "stop_reason_required"
        )
    if output.action_type is not ResearchOrchestratorActionType.RUN_CHASE_ROUND:
        return None
    return _validate_run_chase_round_selection(
        output=output,
        workspace_summary=workspace_summary,
    )


def _validate_run_chase_round_selection(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject,
) -> str | None:
    shape_error = _validate_run_chase_round_selection_shape(output=output)
    if shape_error is not None:
        return shape_error

    candidate_map = _workspace_chase_candidate_map(workspace_summary=workspace_summary)
    if not candidate_map:
        return "chase_selection_unknown_entity"
    return _validate_run_chase_round_selection_membership(
        output=output,
        candidate_map=candidate_map,
    )


def _validate_run_chase_round_selection_shape(
    *,
    output: ShadowPlannerRecommendationOutput,
) -> str | None:
    if (
        not output.selected_entity_ids
        or not output.selected_labels
        or output.selection_basis is None
        or output.selection_basis.strip() == ""
    ):
        return "chase_selection_required"
    if (
        len(output.selected_entity_ids) > _MAX_CHASE_SELECTION_ENTITIES
        or len(output.selected_labels) > _MAX_CHASE_SELECTION_ENTITIES
    ):
        return "chase_selection_too_large"
    if len(output.selected_entity_ids) != len(output.selected_labels):
        return "chase_selection_label_mismatch"
    return None


def _validate_run_chase_round_selection_membership(
    *,
    output: ShadowPlannerRecommendationOutput,
    candidate_map: dict[str, ResearchOrchestratorChaseCandidate],
) -> str | None:
    for entity_id, selected_label in zip(
        output.selected_entity_ids,
        output.selected_labels,
        strict=True,
    ):
        candidate = candidate_map.get(entity_id)
        if candidate is None:
            return "chase_selection_unknown_entity"
        if candidate.display_label != selected_label:
            return "chase_selection_label_mismatch"
    return None


def _validate_qualitative_rationale(
    *,
    output: ShadowPlannerRecommendationOutput,
) -> str | None:
    if output.qualitative_rationale.strip() == "":
        return "qualitative_rationale_missing"
    if _contains_forbidden_numeric_style(output.qualitative_rationale):
        return "numeric_style_ranking_not_allowed"
    return None


def _decision_chase_selection(
    *,
    decision: ResearchOrchestratorDecision,
) -> ResearchOrchestratorChaseSelection | None:
    if decision.action_type is ResearchOrchestratorActionType.RUN_CHASE_ROUND:
        selected_entity_ids = decision.action_input.get("selected_entity_ids")
        selected_labels = decision.action_input.get("selected_labels")
        selection_basis = decision.action_input.get("selection_basis")
        if (
            isinstance(selected_entity_ids, list)
            and isinstance(selected_labels, list)
            and isinstance(selection_basis, str)
        ):
            try:
                return ResearchOrchestratorChaseSelection(
                    selected_entity_ids=[
                        item for item in selected_entity_ids if isinstance(item, str)
                    ],
                    selected_labels=[
                        item for item in selected_labels if isinstance(item, str)
                    ],
                    stop_instead=decision.status == "skipped",
                    stop_reason=decision.stop_reason,
                    selection_basis=selection_basis,
                )
            except Exception:  # noqa: BLE001
                return None
    if decision.action_type is ResearchOrchestratorActionType.STOP:
        return ResearchOrchestratorChaseSelection(
            selected_entity_ids=[],
            selected_labels=[],
            stop_instead=True,
            stop_reason=decision.stop_reason,
            selection_basis=decision.evidence_basis,
        )
    return None


def _build_chase_selection_comparison(
    *,
    checkpoint_key: str,
    planner_result: ShadowPlannerRecommendationResult,
    deterministic_target: ResearchOrchestratorDecision,
    workspace_summary: JSONObject,
) -> JSONObject:
    target_selection = _workspace_chase_selection(
        workspace_summary=workspace_summary,
    ) or _decision_chase_selection(decision=deterministic_target)
    planner_selection = _decision_chase_selection(decision=planner_result.decision)
    deterministic_labels = (
        list(target_selection.selected_labels) if target_selection is not None else []
    )
    planner_labels = (
        list(planner_selection.selected_labels) if planner_selection is not None else []
    )
    deterministic_ids = (
        list(target_selection.selected_entity_ids)
        if target_selection is not None
        else []
    )
    planner_ids = (
        list(planner_selection.selected_entity_ids)
        if planner_selection is not None
        else []
    )
    deterministic_stop_expected = bool(
        target_selection is not None and target_selection.stop_instead,
    )
    planner_recommended_stop = (
        planner_result.decision.action_type is ResearchOrchestratorActionType.STOP
    )
    stop_match = (deterministic_stop_expected and planner_recommended_stop) or (
        not deterministic_stop_expected
        and planner_result.decision.action_type
        is ResearchOrchestratorActionType.RUN_CHASE_ROUND
    )
    chase_selection_available = (
        target_selection is not None
        and planner_selection is not None
        and not deterministic_stop_expected
        and (
            bool(target_selection.selected_entity_ids)
            or bool(planner_selection.selected_entity_ids)
        )
    )
    deterministic_only_labels = [
        label for label in deterministic_labels if label not in set(planner_labels)
    ]
    planner_only_labels = [
        label for label in planner_labels if label not in set(deterministic_labels)
    ]
    exact_selection_match = (
        chase_selection_available
        and not deterministic_stop_expected
        and planner_result.decision.action_type
        is ResearchOrchestratorActionType.RUN_CHASE_ROUND
        and planner_ids == deterministic_ids
        and planner_labels == deterministic_labels
    )
    selected_entity_overlap_count = len(set(deterministic_ids) & set(planner_ids))
    comparison_status = (
        "matched"
        if (deterministic_stop_expected and planner_recommended_stop)
        or exact_selection_match
        or (
            not chase_selection_available
            and planner_result.decision.action_type
            is ResearchOrchestratorActionType.RUN_CHASE_ROUND
            and deterministic_target.action_type
            is ResearchOrchestratorActionType.RUN_CHASE_ROUND
        )
        else "diverged"
    )
    return {
        "checkpoint_key": checkpoint_key,
        "deterministic_selected_entity_ids": deterministic_ids,
        "deterministic_selected_labels": deterministic_labels,
        "recommended_selected_entity_ids": planner_ids,
        "recommended_selected_labels": planner_labels,
        "deterministic_stop_expected": deterministic_stop_expected,
        "recommended_stop": planner_recommended_stop,
        "stop_match": stop_match,
        "chase_selection_available": chase_selection_available,
        "exact_selection_match": exact_selection_match,
        "selected_entity_overlap_count": selected_entity_overlap_count,
        "deterministic_only_labels": deterministic_only_labels,
        "planner_only_labels": planner_only_labels,
        "planner_conservative_stop": (
            planner_recommended_stop and not deterministic_stop_expected
        ),
        "planner_continued_when_threshold_stop": (
            not planner_recommended_stop and deterministic_stop_expected
        ),
        "comparison_status": comparison_status,
    }


def build_shadow_planner_comparison(
    *,
    checkpoint_key: str,
    planner_result: ShadowPlannerRecommendationResult,
    deterministic_target: ResearchOrchestratorDecision | None,
    workspace_summary: JSONObject | None = None,
    mode: str = "shadow",
) -> JSONObject:
    """Compare the planner recommendation against the deterministic baseline."""

    fallback_reason = planner_result.decision.fallback_reason
    qualitative_rationale = planner_result.decision.qualitative_rationale
    qualitative_rationale_present = bool(
        isinstance(qualitative_rationale, str) and qualitative_rationale.strip(),
    )
    budget_violation = fallback_reason == "budget_violation"
    if deterministic_target is None:
        return {
            "checkpoint_key": checkpoint_key,
            "mode": mode,
            "planner_status": planner_result.planner_status,
            "comparison_status": "no_target",
            "recommended_step_key": planner_result.decision.step_key,
            "recommended_action_type": planner_result.decision.action_type.value,
            "recommended_source_key": planner_result.decision.source_key,
            "used_fallback": planner_result.used_fallback,
            "fallback_reason": fallback_reason,
            "validation_error": planner_result.validation_error,
            "initial_validation_error": planner_result.initial_validation_error,
            "repair_attempted": planner_result.repair_attempted,
            "repair_succeeded": planner_result.repair_succeeded,
            "qualitative_rationale_present": qualitative_rationale_present,
            "budget_violation": budget_violation,
            "comparison_reason": "Deterministic run did not expose a comparable action.",
        }

    action_match = (
        planner_result.decision.action_type == deterministic_target.action_type
    )
    source_match = planner_result.decision.source_key == deterministic_target.source_key
    comparison: JSONObject = {
        "checkpoint_key": checkpoint_key,
        "mode": mode,
        "planner_status": planner_result.planner_status,
        "comparison_status": "matched" if action_match and source_match else "diverged",
        "target_step_key": deterministic_target.step_key,
        "target_action_type": deterministic_target.action_type.value,
        "target_source_key": deterministic_target.source_key,
        "recommended_step_key": planner_result.decision.step_key,
        "recommended_action_type": planner_result.decision.action_type.value,
        "recommended_source_key": planner_result.decision.source_key,
        "used_fallback": planner_result.used_fallback,
        "fallback_reason": fallback_reason,
        "validation_error": planner_result.validation_error,
        "initial_validation_error": planner_result.initial_validation_error,
        "repair_attempted": planner_result.repair_attempted,
        "repair_succeeded": planner_result.repair_succeeded,
        "qualitative_rationale_present": qualitative_rationale_present,
        "budget_violation": budget_violation,
        "action_match": action_match,
        "source_match": source_match,
        "comparison_reason": _comparison_reason(
            action_match=action_match,
            source_match=source_match,
        ),
    }
    if checkpoint_key in {"after_bootstrap", "after_chase_round_1"}:
        comparison.update(
            _build_chase_selection_comparison(
                checkpoint_key=checkpoint_key,
                planner_result=planner_result,
                deterministic_target=deterministic_target,
                workspace_summary=workspace_summary or {},
            ),
        )
    return comparison


def _build_shadow_planner_prompt(*, workspace_summary: JSONObject) -> str:
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        else "unknown"
    )
    live_action_types = ", ".join(planner_constraints["live_action_types"]) or "none"
    source_required = (
        ", ".join(planner_constraints["source_required_action_types"]) or "none"
    )
    control_actions = (
        ", ".join(planner_constraints["control_action_types_without_source_key"])
        or "none"
    )
    source_taxonomy = planner_constraints["source_taxonomy"]
    live_evidence_sources = (
        ", ".join(_string_list(source_taxonomy.get("live_evidence"))) or "none"
    )
    context_only_sources = (
        ", ".join(_string_list(source_taxonomy.get("context_only"))) or "none"
    )
    reserved_sources = (
        ", ".join(_string_list(source_taxonomy.get("reserved"))) or "none"
    )
    grounding_sources = (
        ", ".join(_string_list(source_taxonomy.get("grounding"))) or "none"
    )
    structured_sources = (
        ", ".join(planner_constraints["structured_enrichment_source_keys"]) or "none"
    )
    checkpoint_guidance = _checkpoint_guidance_text(
        checkpoint_key=checkpoint_key,
        structured_sources=planner_constraints["structured_enrichment_source_keys"],
    )
    return (
        "Shadow-planner workspace summary follows.\n"
        "Recommend exactly one next action.\n\n"
        f"Checkpoint guidance:\n{checkpoint_guidance}\n\n"
        "Output rules:\n"
        f"- action_type must be exactly one of: {live_action_types}\n"
        f"- source_key is required only for: {source_required}\n"
        f"- source_key must be omitted for: {control_actions}\n"
        f"- Source taxonomy: live_evidence={live_evidence_sources}; "
        f"context_only={context_only_sources}; grounding={grounding_sources}; "
        f"reserved={reserved_sources}\n"
        "- qualitative_rationale must lead with qualitative assessment grounded in the "
        "workspace summary.\n"
        "- Do not use percentages, scores, probabilities, ranked-number language, or "
        "numeric confidence claims in qualitative_rationale.\n"
        f"- QUERY_PUBMED must use source_key "
        f'"{planner_constraints["pubmed_source_key"]}".\n'
        f"- INGEST_AND_EXTRACT_PUBMED must use source_key "
        f'"{planner_constraints["pubmed_source_key"]}".\n'
        f"- RUN_STRUCTURED_ENRICHMENT may use only one of: {structured_sources}\n\n"
        f"{json.dumps(workspace_summary, sort_keys=True, indent=2, default=str)}\n"
    )


def _build_shadow_planner_repair_prompt(
    *,
    workspace_summary: JSONObject,
    invalid_output: ShadowPlannerRecommendationOutput,
    validation_error: str,
) -> str:
    repair_guidance = _shadow_planner_repair_guidance(
        workspace_summary=workspace_summary,
        validation_error=validation_error,
    )
    return (
        f"{_build_shadow_planner_prompt(workspace_summary=workspace_summary)}\n"
        "The previous recommendation was rejected.\n"
        f"validation_error: {validation_error}\n"
        f"{repair_guidance}"
        "Return a corrected recommendation that keeps the same intent where possible "
        "but follows every output rule exactly.\n"
        "Rejected recommendation:\n"
        f"{json.dumps(invalid_output.model_dump(mode='json'), sort_keys=True, indent=2)}\n"
    )


def _shadow_planner_repair_guidance(
    *,
    workspace_summary: JSONObject,
    validation_error: str,
) -> str:
    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        else ""
    )
    if checkpoint_key not in {"after_bootstrap", "after_chase_round_1"}:
        return ""
    if validation_error not in {
        "chase_checkpoint_action_not_allowed",
        "chase_selection_required",
        "chase_selection_label_mismatch",
        "chase_selection_too_large",
        "chase_selection_unknown_entity",
        "objective_relevant_chase_required",
    }:
        return ""
    deterministic_selection = _workspace_chase_selection(
        workspace_summary=workspace_summary,
    )
    if deterministic_selection is not None and not deterministic_selection.stop_instead:
        return (
            "Repair guidance:\n"
            "- At this chase checkpoint, return RUN_CHASE_ROUND or STOP, not GENERATE_BRIEF.\n"
            "- selected_entity_ids and selected_labels must stay inside the supplied chase_candidates.\n"
            "- Choose STOP only when the supplied candidates are weak, repetitive, or off-objective.\n"
            "- If chase_decision_posture.posture is continue_objective_relevant, return RUN_CHASE_ROUND with a bounded subset of deterministic_selection.\n"
        )
    return (
        "Repair guidance:\n"
        "- At this chase checkpoint, only RUN_CHASE_ROUND or STOP is valid.\n"
        "- If deterministic_selection.stop_instead is true, return STOP with a non-empty stop_reason.\n"
    )


def _checkpoint_fallback_output(
    *,
    checkpoint_key: str,
    live_types: frozenset[ResearchOrchestratorActionType],
    planner_constraints: _PlannerConstraintsSummary,
    sources: ResearchSpaceSourcePreferences,
    structured_enrichment_sources: list[str],
    workspace_summary: JSONObject,
) -> dict[str, object] | None:
    output_kwargs: dict[str, object] | None = None
    synthesis_readiness = shadow_planner_synthesis_readiness(
        workspace_summary=workspace_summary,
    )
    preferred_structured_source = (
        _preferred_structured_enrichment_source_from_workspace(
            workspace_summary=workspace_summary,
            structured_enrichment_sources=structured_enrichment_sources,
        )
    )
    deterministic_chase_selection = _workspace_chase_selection(
        workspace_summary=workspace_summary,
    )
    if checkpoint_key == "before_terminal_stop":
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.STOP,
            "source_key": None,
            "evidence_basis": "The run is at the terminal checkpoint in shadow mode.",
            "qualitative_rationale": (
                "Stop because the deterministic workflow has already reached its final "
                "terminal checkpoint."
            ),
            "expected_value_band": "low",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "none",
                "basis": "terminal_checkpoint",
            },
            "stop_reason": "terminal_checkpoint",
            "fallback_reason": "openai_api_key_not_configured",
        }
    elif checkpoint_key == "before_brief_generation":
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.GENERATE_BRIEF,
            "source_key": None,
            "evidence_basis": (
                "The run is at the final synthesis checkpoint in shadow mode."
            ),
            "qualitative_rationale": (
                "Generate the brief because the deterministic workflow has already "
                "gathered evidence and reached the final synthesis boundary."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "brief_checkpoint",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    elif (
        checkpoint_key == "after_pubmed_discovery"
        and ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED in live_types
        and sources.get("pubmed", False)
        and planner_constraints["pubmed_ingest_pending"]
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
            "source_key": "pubmed",
            "evidence_basis": (
                "PubMed discovery has already surfaced grounded literature, but the "
                "documents have not been ingested and extracted yet."
            ),
            "qualitative_rationale": (
                "Ingest and extract the PubMed papers now because the run already "
                "found grounded literature and should turn that discovery step into "
                "usable evidence before branching into structured follow-up."
            ),
            "expected_value_band": "high",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "pubmed_ingest_after_discovery",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    elif (
        checkpoint_key in {"after_pubmed_ingest_extract", "after_driven_terms_ready"}
        and ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT in live_types
        and preferred_structured_source is not None
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
            "source_key": preferred_structured_source,
            "evidence_basis": (
                "PubMed ingest and extraction have already completed, so the next "
                "step is to broaden coverage through the strongest still-pending "
                "structured source for this objective."
            ),
            "qualitative_rationale": (
                f"Use {preferred_structured_source} structured enrichment now because "
                "the literature pass is already grounded and the workspace summary "
                "indicates that this source is the best remaining qualitative fit "
                "for the current research objective."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "post_pubmed_structured_enrichment",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    if (
        output_kwargs is None
        and checkpoint_key in {"after_bootstrap", "after_chase_round_1"}
        and ResearchOrchestratorActionType.STOP in live_types
        and (
            (
                deterministic_chase_selection is not None
                and deterministic_chase_selection.stop_instead
            )
            or (
                deterministic_chase_selection is None
                and synthesis_readiness["ready_for_brief"]
            )
        )
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.STOP,
            "source_key": None,
            "evidence_basis": (
                synthesis_readiness["summary"]
                if deterministic_chase_selection is None
                else (
                    "The deterministic chase candidate set does not clear the "
                    "bounded threshold for another chase round."
                )
            ),
            "qualitative_rationale": (
                "Stop here because the run is already synthesis-ready and the chase "
                "checkpoint does not justify another bounded retrieval step."
                if deterministic_chase_selection is None
                else (
                    "Stop here because the available chase candidates are too weak "
                    "or too few to justify another bounded chase round."
                )
            ),
            "expected_value_band": "low",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "none",
                "basis": (
                    "synthesis_ready_no_chase_selection"
                    if deterministic_chase_selection is None
                    else "threshold_not_met"
                ),
            },
            "stop_reason": (
                "synthesis_ready"
                if deterministic_chase_selection is None
                else "threshold_not_met"
            ),
            "fallback_reason": "openai_api_key_not_configured",
        }
    if (
        output_kwargs is None
        and checkpoint_key in {"after_bootstrap", "after_chase_round_1"}
        and ResearchOrchestratorActionType.RUN_CHASE_ROUND in live_types
        and deterministic_chase_selection is not None
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.RUN_CHASE_ROUND,
            "source_key": None,
            "evidence_basis": (
                "The bounded chase candidate set already clears the deterministic "
                "threshold for another chase round."
            ),
            "qualitative_rationale": (
                "Continue with a bounded chase round because the workspace already "
                "contains specific newly surfaced entities that are worth testing as "
                "the next discovery step."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "single_chase_round",
            },
            "selected_entity_ids": list(
                deterministic_chase_selection.selected_entity_ids,
            ),
            "selected_labels": list(deterministic_chase_selection.selected_labels),
            "selection_basis": deterministic_chase_selection.selection_basis,
            "fallback_reason": "openai_api_key_not_configured",
        }
    if (
        output_kwargs is None
        and checkpoint_key == "after_chase_round_2"
        and ResearchOrchestratorActionType.GENERATE_BRIEF in live_types
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.GENERATE_BRIEF,
            "source_key": None,
            "evidence_basis": (
                "Two chase rounds have already been attempted, so the next bounded "
                "step is synthesis."
            ),
            "qualitative_rationale": (
                "Move to brief generation because the bounded chase budget has been "
                "used and the workflow should now synthesize what it has learned."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "post_chase_brief",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    return output_kwargs


def _default_fallback_output(
    *,
    live_types: frozenset[ResearchOrchestratorActionType],
    sources: ResearchSpaceSourcePreferences,
    structured_enrichment_sources: list[str],
) -> dict[str, object]:
    preferred_structured_source = (
        structured_enrichment_sources[0] if structured_enrichment_sources else None
    )
    if ResearchOrchestratorActionType.QUERY_PUBMED in live_types and sources.get(
        "pubmed", False
    ):
        return {
            "action_type": ResearchOrchestratorActionType.QUERY_PUBMED,
            "source_key": "pubmed",
            "evidence_basis": (
                "PubMed discovery is the deterministic first evidence-gathering step."
            ),
            "qualitative_rationale": (
                "Start with literature discovery to ground the run in retrieved "
                "evidence before deciding which structured sources deserve follow-up."
            ),
            "expected_value_band": "high",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "single_source_query",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    if (
        ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT in live_types
        and preferred_structured_source is not None
    ):
        return {
            "action_type": ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
            "source_key": preferred_structured_source,
            "evidence_basis": (
                "A structured source is enabled, so the planner can still gather "
                "grounded records without free-form action selection."
            ),
            "qualitative_rationale": (
                f"Move to {preferred_structured_source} to broaden evidence coverage "
                "while the deterministic baseline remains in control."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "single_source_enrichment",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    if ResearchOrchestratorActionType.GENERATE_BRIEF in live_types:
        return {
            "action_type": ResearchOrchestratorActionType.GENERATE_BRIEF,
            "source_key": None,
            "evidence_basis": (
                "The available shadow-mode action set contains no usable source step."
            ),
            "qualitative_rationale": (
                "Move toward brief generation because the planner cannot open a "
                "grounded source step from the current live action set."
            ),
            "expected_value_band": "low",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "brief_only",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    return {
        "action_type": ResearchOrchestratorActionType.STOP,
        "source_key": None,
        "evidence_basis": (
            "No enabled or planner-selectable sources are available for the run."
        ),
        "qualitative_rationale": (
            "Stop because there is no live action capable of adding grounded evidence."
        ),
        "expected_value_band": "low",
        "risk_level": "low",
        "requires_approval": False,
        "budget_estimate": {
            "relative_size": "none",
            "basis": "no_live_actions",
        },
        "stop_reason": "no_live_actions",
        "fallback_reason": "openai_api_key_not_configured",
    }


def _build_fallback_output(
    *,
    checkpoint_key: str,
    workspace_summary: JSONObject,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> ShadowPlannerRecommendationOutput:
    live_types = planner_live_action_types(action_registry=action_registry)
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    structured_enrichment_sources = _structured_enrichment_source_keys(
        enabled_sources={
            key: value for key, value in sources.items() if isinstance(value, bool)
        },
    )
    output_kwargs = _checkpoint_fallback_output(
        checkpoint_key=checkpoint_key,
        live_types=live_types,
        planner_constraints=planner_constraints,
        sources=sources,
        structured_enrichment_sources=structured_enrichment_sources,
        workspace_summary=workspace_summary,
    )
    if output_kwargs is None:
        output_kwargs = _default_fallback_output(
            live_types=live_types,
            sources=sources,
            structured_enrichment_sources=structured_enrichment_sources,
        )
    return ShadowPlannerRecommendationOutput.model_validate(output_kwargs)


def _build_shadow_decision(
    *,
    output: ShadowPlannerRecommendationOutput,
    checkpoint_key: str,
    planner_status: str,
    model_id: str | None,
    agent_run_id: str,
    prompt_version: str,
    harness_id: str,
    step_key_version: str,
    initial_validation_error: str | None = None,
    repair_attempted: bool = False,
    repair_succeeded: bool = False,
    telemetry: ShadowPlannerTelemetry | None = None,
) -> ResearchOrchestratorDecision:
    step_key = _build_shadow_step_key(
        checkpoint_key=checkpoint_key,
        action_type=output.action_type,
        source_key=output.source_key,
        harness_id=harness_id,
        step_key_version=step_key_version,
    )
    payload = json.dumps(
        {
            "checkpoint_key": checkpoint_key,
            "action_type": output.action_type.value,
            "source_key": output.source_key,
            "step_key": step_key,
            "agent_run_id": agent_run_id,
        },
        sort_keys=True,
    )
    return ResearchOrchestratorDecision(
        decision_id=f"shadow-planner:{stable_sha256_digest(payload, length=24)}",
        round_number=0,
        action_type=output.action_type,
        action_input=_shadow_action_input(
            output=output,
            checkpoint_key=checkpoint_key,
            agent_run_id=agent_run_id,
        ),
        source_key=output.source_key,
        evidence_basis=output.evidence_basis,
        stop_reason=output.stop_reason,
        step_key=step_key,
        status="recommended",
        expected_value_band=output.expected_value_band,
        qualitative_rationale=output.qualitative_rationale,
        risk_level=output.risk_level,
        requires_approval=output.requires_approval,
        budget_estimate=output.budget_estimate,
        fallback_reason=output.fallback_reason,
        metadata={
            "checkpoint_key": checkpoint_key,
            "planner_status": planner_status,
            "model_id": model_id,
            "agent_run_id": agent_run_id,
            "prompt_version": prompt_version,
            "initial_validation_error": initial_validation_error,
            "repair_attempted": repair_attempted,
            "repair_succeeded": repair_succeeded,
            "telemetry": _shadow_planner_telemetry_payload(telemetry),
        },
    )


def _shadow_action_input(
    *,
    output: ShadowPlannerRecommendationOutput,
    checkpoint_key: str,
    agent_run_id: str,
) -> JSONObject:
    action_input: JSONObject = {
        "mode": "shadow",
        "checkpoint_key": checkpoint_key,
        "agent_run_id": agent_run_id,
    }
    if output.action_type is ResearchOrchestratorActionType.RUN_CHASE_ROUND:
        action_input["selected_entity_ids"] = list(output.selected_entity_ids)
        action_input["selected_labels"] = list(output.selected_labels)
        if output.selection_basis is not None:
            action_input["selection_basis"] = output.selection_basis
    return action_input


def _unavailable_shadow_planner_telemetry() -> ShadowPlannerTelemetry:
    return ShadowPlannerTelemetry(
        status="unavailable",
        model_terminal_count=0,
    )


def _shadow_planner_telemetry_payload(
    telemetry: ShadowPlannerTelemetry | None,
) -> JSONObject:
    if telemetry is None:
        telemetry = _unavailable_shadow_planner_telemetry()
    return {
        "status": telemetry.status,
        "model_terminal_count": telemetry.model_terminal_count,
        "prompt_tokens": telemetry.prompt_tokens,
        "completion_tokens": telemetry.completion_tokens,
        "total_tokens": telemetry.total_tokens,
        "cost_usd": telemetry.cost_usd,
        "latency_seconds": telemetry.latency_seconds,
        "tool_call_count": telemetry.tool_call_count,
    }


async def _collect_shadow_planner_telemetry(  # noqa: PLR0912, PLR0915
    *,
    store: object,
    run_ids: tuple[str, ...],
) -> ShadowPlannerTelemetry:
    get_events_for_run = getattr(store, "get_events_for_run", None)
    if not callable(get_events_for_run) or not run_ids:
        return _unavailable_shadow_planner_telemetry()

    from artana.events import EventType, ModelTerminalPayload

    model_terminal_count = 0
    prompt_tokens_total = 0
    completion_tokens_total = 0
    cost_total = 0.0
    latency_ms_total = 0
    tool_call_count = 0
    prompt_tokens_seen = False
    completion_tokens_seen = False
    cost_seen = False
    latency_seen = False

    for run_id in run_ids:
        events = await get_events_for_run(run_id)
        if not isinstance(events, list):
            continue
        run_cost_total = 0.0
        run_cost_seen = False
        for event in events:
            event_type = getattr(event, "event_type", None)
            payload = getattr(event, "payload", None)
            if event_type not in {
                EventType.MODEL_TERMINAL,
                EventType.MODEL_TERMINAL.value,
            }:
                continue
            if not isinstance(payload, ModelTerminalPayload):
                continue
            model_terminal_count += 1
            latency_ms_total += payload.elapsed_ms
            latency_seen = True
            tool_call_count += len(payload.tool_calls)
            if payload.prompt_tokens is not None:
                prompt_tokens_total += payload.prompt_tokens
                prompt_tokens_seen = True
            if payload.completion_tokens is not None:
                completion_tokens_total += payload.completion_tokens
                completion_tokens_seen = True
            model_terminal_cost_usd = _effective_shadow_planner_model_terminal_cost_usd(
                payload,
            )
            if model_terminal_cost_usd is not None:
                run_cost_total += model_terminal_cost_usd
                run_cost_seen = True

        summary_cost_usd = await _read_shadow_planner_run_cost_summary(
            store=store,
            run_id=run_id,
        )
        selected_cost_usd = _select_shadow_planner_run_cost_usd(
            summary_cost_usd=summary_cost_usd,
            model_terminal_cost_usd=run_cost_total if run_cost_seen else None,
        )
        if selected_cost_usd is not None:
            cost_total += selected_cost_usd
            cost_seen = True

    if model_terminal_count == 0 and not cost_seen:
        return _unavailable_shadow_planner_telemetry()

    prompt_tokens = prompt_tokens_total if prompt_tokens_seen else None
    completion_tokens = completion_tokens_total if completion_tokens_seen else None
    total_tokens = None
    if prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    status: Literal["available", "partial", "unavailable"] = "partial"
    if prompt_tokens is not None and completion_tokens is not None and cost_seen:
        status = "available"
    return ShadowPlannerTelemetry(
        status=status,
        model_terminal_count=model_terminal_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=round(cost_total, 8) if cost_seen else None,
        latency_seconds=round(latency_ms_total / 1000.0, 6) if latency_seen else None,
        tool_call_count=tool_call_count,
    )


async def _read_shadow_planner_run_cost_summary(
    *,
    store: object,
    run_id: str,
) -> float | None:
    get_latest_run_summary = getattr(store, "get_latest_run_summary", None)
    if not callable(get_latest_run_summary):
        return None

    for summary_type in _COST_SUMMARY_TYPES:
        with suppress(Exception):
            summary = await get_latest_run_summary(run_id, summary_type)
        if summary is None:
            continue
        payload = _shadow_planner_summary_payload(summary)
        if payload is None:
            continue
        cost_usd = _shadow_planner_cost_from_summary_payload(payload)
        if cost_usd is not None:
            return cost_usd
    return None


def _shadow_planner_summary_payload(summary: object) -> JSONObject | None:
    summary_json = getattr(summary, "summary_json", None)
    if not isinstance(summary_json, str):
        return None
    with suppress(json.JSONDecodeError):
        payload = json.loads(summary_json)
        if isinstance(payload, dict):
            return cast("JSONObject", payload)
    return None


def _shadow_planner_cost_from_summary_payload(payload: JSONObject) -> float | None:
    for key in _COST_PAYLOAD_KEYS:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            return round(float(value), 8)
    return None


def _select_shadow_planner_run_cost_usd(
    *,
    summary_cost_usd: float | None,
    model_terminal_cost_usd: float | None,
) -> float | None:
    if summary_cost_usd is not None and summary_cost_usd > 0.0:
        return round(summary_cost_usd, 8)
    if model_terminal_cost_usd is not None and model_terminal_cost_usd > 0.0:
        return round(model_terminal_cost_usd, 8)
    if summary_cost_usd == 0.0:
        return 0.0
    if model_terminal_cost_usd == 0.0:
        return 0.0
    return None


def _effective_shadow_planner_model_terminal_cost_usd(payload: object) -> float | None:
    reported_cost_usd = getattr(payload, "cost_usd", None)
    if isinstance(reported_cost_usd, int | float) and not isinstance(
        reported_cost_usd,
        bool,
    ):
        normalized_reported_cost = round(float(reported_cost_usd), 8)
        if normalized_reported_cost > 0.0:
            return normalized_reported_cost
        derived_cost_usd = _derive_shadow_planner_model_terminal_cost_usd(payload)
        if derived_cost_usd is not None:
            return derived_cost_usd
        return 0.0
    return _derive_shadow_planner_model_terminal_cost_usd(payload)


def _derive_shadow_planner_model_terminal_cost_usd(payload: object) -> float | None:
    model_id = getattr(payload, "model", None)
    prompt_tokens = getattr(payload, "prompt_tokens", None)
    completion_tokens = getattr(payload, "completion_tokens", None)
    if not isinstance(model_id, str):
        return None
    if not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool):
        return None
    if not isinstance(completion_tokens, int) or isinstance(completion_tokens, bool):
        return None

    normalized_model_id = _normalize_shadow_planner_cost_model_id(model_id)
    if ":" in normalized_model_id and not normalized_model_id.startswith("openai:"):
        return None

    from artana_evidence_api.llm_costs import calculate_openai_usage_cost_usd

    with suppress(Exception):
        cost_usd = calculate_openai_usage_cost_usd(
            model_id=normalized_model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        if cost_usd > 0.0:
            return cost_usd
    return None


def _normalize_shadow_planner_cost_model_id(model_id: str) -> str:
    normalized = model_id.strip()
    if normalized == "":
        return normalized
    if ":" in normalized:
        return normalized
    if "/" in normalized:
        provider, model_name = normalized.split("/", 1)
        if provider.strip() and model_name.strip():
            return f"{provider.strip()}:{model_name.strip()}"
    return normalized


def _build_shadow_step_key(
    *,
    checkpoint_key: str,
    action_type: ResearchOrchestratorActionType,
    source_key: str | None,
    harness_id: str,
    step_key_version: str,
) -> str:
    source_segment = source_key if source_key is not None else "control"
    return (
        f"{harness_id}.{step_key_version}.shadow.{checkpoint_key}."
        f"{source_segment}.{action_type.value.casefold()}"
    )


def _build_agent_run_id(
    *,
    objective: str,
    checkpoint_key: str,
    workspace_summary: JSONObject,
) -> str:
    digest = stable_sha256_digest(
        json.dumps(
            {
                "objective": objective,
                "checkpoint_key": checkpoint_key,
                "workspace_summary": workspace_summary,
            },
            sort_keys=True,
            default=str,
        ),
        length=24,
    )
    return f"full-ai-shadow-planner:{digest}"


def _normalize_shadow_planner_workspace_summary(
    *,
    checkpoint_key: str,
    objective: str,
    workspace_summary: JSONObject,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> JSONObject:
    normalized = dict(workspace_summary)
    enabled_sources = {
        key: value
        for key, value in sources.items()
        if isinstance(key, str) and isinstance(value, bool)
    }
    normalized["checkpoint_key"] = checkpoint_key
    normalized.setdefault("objective", objective)
    normalized.setdefault("enabled_sources", enabled_sources)

    raw_counts = normalized.get("counts")
    counts = dict(raw_counts) if isinstance(raw_counts, dict) else {}
    normalized["counts"] = {
        "documents_ingested": _int_or_zero(counts.get("documents_ingested")),
        "proposal_count": _int_or_zero(counts.get("proposal_count")),
        "pending_question_count": _int_or_zero(counts.get("pending_question_count")),
        "error_count": _int_or_zero(counts.get("error_count")),
        "evidence_gap_count": _int_or_zero(counts.get("evidence_gap_count")),
        "contradiction_count": _int_or_zero(counts.get("contradiction_count")),
    }
    normalized.setdefault("source_status_summary", {})
    normalized.setdefault("top_evidence_gaps", [])
    normalized.setdefault("active_contradictions", [])
    normalized.setdefault("prior_decisions", [])
    normalized.setdefault("remaining_hard_limits", {})
    source_taxonomy = _planner_source_taxonomy(enabled_sources=enabled_sources)
    normalized["source_taxonomy"] = source_taxonomy
    normalized.setdefault(
        "planner_actions",
        planner_action_registry_by_state(action_registry=action_registry),
    )
    normalized.setdefault(
        "planner_constraints",
        json_object_or_empty(
            _planner_constraints_from_action_registry(
                action_registry=action_registry,
                enabled_sources=enabled_sources,
            )
        ),
    )
    normalized["objective_routing_hints"] = json_value(
        _checkpoint_objective_routing_hints(
            checkpoint_key=checkpoint_key,
            objective=str(normalized.get("objective", objective)),
            structured_enrichment_sources=_structured_enrichment_source_keys(
                enabled_sources=enabled_sources,
            ),
            pending_structured_sources=_structured_enrichment_pending_source_keys(
                workspace_summary=normalized,
                structured_enrichment_sources=_structured_enrichment_source_keys(
                    enabled_sources=enabled_sources,
                ),
            ),
            pubmed_ingest_pending=_pubmed_ingest_pending(
                source_status_summary=(
                    normalized["source_status_summary"]
                    if isinstance(normalized["source_status_summary"], dict)
                    else {}
                ),
            ),
        )
    )
    normalized["planner_constraints"] = {
        **json_object_or_empty(_workspace_planner_constraints(workspace_summary=normalized)),
        "source_taxonomy": source_taxonomy,
        "pubmed_ingest_pending": _pubmed_ingest_pending(
            source_status_summary=(
                normalized["source_status_summary"]
                if isinstance(normalized["source_status_summary"], dict)
                else {}
            ),
        ),
        "pending_structured_enrichment_source_keys": (
            _structured_enrichment_pending_source_keys(
                workspace_summary=normalized,
                structured_enrichment_sources=_workspace_structured_enrichment_source_keys(
                    workspace_summary=normalized,
                ),
            )
        ),
    }
    normalized["synthesis_readiness"] = json_value(
        shadow_planner_synthesis_readiness(
            workspace_summary=normalized,
        ),
    )
    return normalized


def _workspace_planner_constraints(
    *,
    workspace_summary: JSONObject,
) -> _PlannerConstraintsSummary:
    raw_constraints = workspace_summary.get("planner_constraints")
    if not isinstance(raw_constraints, dict):
        return {
            "live_action_types": [],
            "source_required_action_types": [],
            "control_action_types_without_source_key": [],
            "pubmed_source_key": "pubmed",
            "pubmed_ingest_pending": False,
            "source_taxonomy": {
                "live_evidence": [],
                "context_only": [],
                "grounding": [],
                "reserved": [],
            },
            "structured_enrichment_source_keys": [],
            "pending_structured_enrichment_source_keys": [],
        }
    raw_source_taxonomy = raw_constraints.get("source_taxonomy")
    source_taxonomy = (
        {
            "live_evidence": _string_list(raw_source_taxonomy.get("live_evidence")),
            "context_only": _string_list(raw_source_taxonomy.get("context_only")),
            "grounding": _string_list(raw_source_taxonomy.get("grounding")),
            "reserved": _string_list(raw_source_taxonomy.get("reserved")),
        }
        if isinstance(raw_source_taxonomy, dict)
        else {
            "live_evidence": [],
            "context_only": [],
            "grounding": [],
            "reserved": [],
        }
    )
    return {
        "live_action_types": _string_list(
            raw_constraints.get("live_action_types"),
        ),
        "source_required_action_types": _string_list(
            raw_constraints.get("source_required_action_types"),
        ),
        "control_action_types_without_source_key": _string_list(
            raw_constraints.get("control_action_types_without_source_key"),
        ),
        "pubmed_source_key": (
            str(raw_constraints.get("pubmed_source_key"))
            if isinstance(raw_constraints.get("pubmed_source_key"), str)
            else "pubmed"
        ),
        "pubmed_ingest_pending": bool(
            raw_constraints.get("pubmed_ingest_pending", False)
        ),
        "source_taxonomy": json_object_or_empty(source_taxonomy),
        "structured_enrichment_source_keys": _string_list(
            raw_constraints.get("structured_enrichment_source_keys"),
        ),
        "pending_structured_enrichment_source_keys": _string_list(
            raw_constraints.get("pending_structured_enrichment_source_keys"),
        ),
    }


def _workspace_structured_enrichment_source_keys(
    *,
    workspace_summary: JSONObject,
) -> list[str]:
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    return planner_constraints["structured_enrichment_source_keys"]


def _workspace_pending_structured_enrichment_source_keys(
    *,
    workspace_summary: JSONObject,
) -> list[str]:
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    return planner_constraints["pending_structured_enrichment_source_keys"]


def _workspace_objective_routing_hints(
    *,
    workspace_summary: JSONObject,
) -> _ObjectiveRoutingHintsSummary:
    raw_hints = workspace_summary.get("objective_routing_hints")
    if not isinstance(raw_hints, dict):
        structured_sources = _workspace_structured_enrichment_source_keys(
            workspace_summary=workspace_summary,
        )
        pending_sources = _structured_enrichment_pending_source_keys(
            workspace_summary=workspace_summary,
            structured_enrichment_sources=structured_sources,
        )
        return _objective_routing_hints(
            objective=str(workspace_summary.get("objective", "")),
            structured_enrichment_sources=structured_sources,
            pending_structured_sources=pending_sources,
        )
    return {
        "objective_tags": _string_list(raw_hints.get("objective_tags")),
        "preferred_structured_sources": _string_list(
            raw_hints.get("preferred_structured_sources"),
        ),
        "preferred_pending_structured_sources": _string_list(
            raw_hints.get("preferred_pending_structured_sources"),
        ),
        "summary": (
            str(raw_hints.get("summary"))
            if isinstance(raw_hints.get("summary"), str)
            else ""
        ),
    }


def _planner_constraints_from_action_registry(
    *,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
    enabled_sources: dict[str, bool],
) -> _PlannerConstraintsSummary:
    source_taxonomy = _planner_source_taxonomy(enabled_sources=enabled_sources)
    structured_enrichment_source_keys = (
        _structured_enrichment_source_keys_from_taxonomy(
            source_taxonomy=source_taxonomy,
        )
    )
    return {
        "live_action_types": [
            spec.action_type.value
            for spec in action_registry
            if spec.planner_state == "live"
        ],
        "source_required_action_types": [
            spec.action_type.value
            for spec in action_registry
            if spec.planner_state == "live" and spec.source_bound
        ],
        "control_action_types_without_source_key": [
            spec.action_type.value
            for spec in action_registry
            if spec.planner_state == "live" and not spec.source_bound
        ],
        "pubmed_source_key": "pubmed",
        "pubmed_ingest_pending": False,
        "source_taxonomy": source_taxonomy,
        "structured_enrichment_source_keys": structured_enrichment_source_keys,
        "pending_structured_enrichment_source_keys": (
            structured_enrichment_source_keys
        ),
    }


def _checkpoint_guidance_text(
    *,
    checkpoint_key: str,
    structured_sources: list[str],
) -> str:
    structured_sources_text = ", ".join(structured_sources) or "none"
    guidance_map = {
        "before_first_action": (
            "- This is the opening checkpoint. If PubMed is enabled, favor "
            "QUERY_PUBMED unless the summary explicitly says grounded evidence is "
            "already present."
        ),
        "after_pubmed_discovery": (
            "- PubMed discovery has already happened, so do not treat this like the "
            "opening checkpoint.\n"
            "- If PubMed documents were discovered or selected and they have not been "
            "ingested yet, prefer INGEST_AND_EXTRACT_PUBMED before structured "
            "enrichment.\n"
            "- Do not apply objective_routing_hints to structured-source selection "
            "until PubMed ingest/extract is complete.\n"
            "- Do not choose STOP unless the summary explicitly says there are no "
            "usable documents or no meaningful live action remains."
        ),
        "after_pubmed_ingest_extract": (
            "- Literature ingest and extraction are already complete.\n"
            f"- If structured enrichment sources are enabled ({structured_sources_text}), "
            "prefer RUN_STRUCTURED_ENRICHMENT rather than STOP unless the summary "
            "explicitly says evidence is sufficient or all structured options are exhausted.\n"
            "- If you choose RUN_STRUCTURED_ENRICHMENT, start from "
            "planner_constraints.pending_structured_enrichment_source_keys, then use "
            "objective_routing_hints.preferred_pending_structured_sources to choose "
            "a later source only when the workspace summary gives a stronger "
            "qualitative reason."
        ),
        "after_driven_terms_ready": (
            "- Driven terms are ready, so the workflow should usually broaden coverage "
            "through one enabled structured source before stopping.\n"
            "- When several structured sources are still pending, use the deterministic "
            "pending-source order as the default, but prefer the objective_routing_hints "
            "ordering when the objective clearly points to a better source family."
        ),
        "after_bootstrap": (
            "- Bootstrap has completed.\n"
            "- At this checkpoint, the only valid action types are RUN_CHASE_ROUND and STOP.\n"
            "- Treat chase_decision_posture as the backend-derived qualitative guardrail for this checkpoint.\n"
            "- If chase_decision_posture.posture is continue_objective_relevant, choose RUN_CHASE_ROUND with a bounded subset of deterministic_selection.\n"
            "- If chase_decision_posture.posture is stop_threshold_not_met, choose STOP with a clear stop_reason.\n"
            "- If deterministic_threshold_met is true, treat that only as permission to continue, "
            "not as a command to continue.\n"
            "- Prefer STOP when the supplied chase_candidates are weak, repetitive, off-objective, "
            "or mostly broaden away from the objective.\n"
            "- Prefer one bounded RUN_CHASE_ROUND when deterministic_threshold_met is true, "
            "deterministic_selection.stop_instead is false, and deterministic selected labels "
            "directly match the objective terms, disease area, mechanism, therapy, or model-organism focus.\n"
            "- Do not use synthesis_readiness.ready_for_brief by itself as a stop signal when "
            "the candidate set is still objective-relevant and bounded.\n"
            "- If you choose RUN_CHASE_ROUND, keep the selection inside the supplied chase_candidates.\n"
            "- If the workspace summary already shows the threshold was not met, prefer STOP with "
            'stop_reason="threshold_not_met".\n'
            "- If synthesis_readiness.ready_for_brief is true and the candidate set is weak, repetitive, "
            "or off-objective, fold that readiness into a STOP rationale instead of switching to GENERATE_BRIEF."
        ),
        "after_chase_round_1": (
            "- One chase round has completed.\n"
            "- At this checkpoint, the only valid action types are RUN_CHASE_ROUND and STOP.\n"
            "- Treat chase_decision_posture as the backend-derived qualitative guardrail for this checkpoint.\n"
            "- If chase_decision_posture.posture is continue_objective_relevant, choose RUN_CHASE_ROUND with a bounded subset of deterministic_selection.\n"
            "- If chase_decision_posture.posture is stop_threshold_not_met, choose STOP with a clear stop_reason.\n"
            "- If the workspace summary says the chase threshold was not met, prefer STOP with "
            'stop_reason="threshold_not_met".\n'
            "- If the remaining chase_candidates are weak, repetitive, off-objective, or mostly "
            "broaden away from the objective, prefer STOP even when the deterministic threshold is met.\n"
            "- If deterministic_threshold_met is true, deterministic_selection.stop_instead is false, "
            "and the remaining selected labels directly match the objective, prefer a bounded RUN_CHASE_ROUND.\n"
            "- Do not use synthesis_readiness.ready_for_brief by itself as a stop signal when "
            "the candidate set is still objective-relevant and bounded.\n"
            "- Otherwise, use a bounded RUN_CHASE_ROUND only for candidates that are clearly "
            "worth chasing next."
        ),
        "after_chase_round_2": (
            "- The bounded chase rounds are exhausted. Prefer GENERATE_BRIEF over "
            "opening more retrieval."
        ),
        "before_brief_generation": (
            "- The workflow is at the synthesis boundary. If evidence has already "
            "been gathered, prefer GENERATE_BRIEF rather than STOP."
        ),
        "before_terminal_stop": (
            "- The workflow is already at the terminal checkpoint. Prefer STOP "
            "unless the summary explicitly identifies an unresolved blocker that "
            "requires escalation."
        ),
    }
    return guidance_map.get(
        checkpoint_key,
        "- Use the checkpoint name and workspace summary to choose the single best next bounded action.",
    )


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


__all__ = [
    "ShadowPlannerRecommendationOutput",
    "ShadowPlannerRecommendationResult",
    "build_shadow_planner_comparison",
    "build_shadow_planner_workspace_summary",
    "load_shadow_planner_prompt",
    "planner_action_registry_by_state",
    "planner_live_action_types",
    "recommend_shadow_planner_action",
    "shadow_planner_prompt_version",
    "validate_shadow_planner_output",
]
