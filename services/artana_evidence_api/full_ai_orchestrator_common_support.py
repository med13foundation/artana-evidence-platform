"""Common action/workspace helpers for the full AI orchestrator."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseSelection,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.research_init_runtime import (
    ResearchInitExecutionResult,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
)
from pydantic import ValidationError

from .run_registry import HarnessRunRecord

_LOGGER = logging.getLogger(__name__)
_PROGRESS_PERSISTENCE_BACKOFF_SECONDS = float(
    os.getenv(
        "ARTANA_EVIDENCE_API_ORCHESTRATOR_PROGRESS_BACKOFF_SECONDS",
        "30.0",
    ).strip()
    or "30.0",
)

_HARNESS_ID = "full-ai-orchestrator"
_ACTION_REGISTRY_ARTIFACT_KEY = "full_ai_orchestrator_action_registry"
_DECISION_HISTORY_ARTIFACT_KEY = "full_ai_orchestrator_decision_history"
_RESULT_ARTIFACT_KEY = "full_ai_orchestrator_result"
_INITIALIZE_ARTIFACT_KEY = "full_ai_orchestrator_initialize_workspace"
_PUBMED_ARTIFACT_KEY = "full_ai_orchestrator_pubmed_summary"
_DRIVEN_TERMS_ARTIFACT_KEY = "full_ai_orchestrator_driven_terms"
_SOURCE_EXECUTION_ARTIFACT_KEY = "full_ai_orchestrator_source_execution_summary"
_BOOTSTRAP_ARTIFACT_KEY = "full_ai_orchestrator_bootstrap_summary"
_CHASE_ROUNDS_ARTIFACT_KEY = "full_ai_orchestrator_chase_rounds"
_BRIEF_METADATA_ARTIFACT_KEY = "full_ai_orchestrator_brief_metadata"
_PUBMED_REPLAY_ARTIFACT_KEY = "full_ai_orchestrator_pubmed_replay_bundle"
_GUARDED_EXECUTION_ARTIFACT_KEY = "full_ai_orchestrator_guarded_execution"
_GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY = (
    "full_ai_orchestrator_guarded_decision_proofs"
)
_GUARDED_DECISION_PROOF_ARTIFACT_PREFIX = "full_ai_orchestrator_guarded_decision_proof"
_SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY = "full_ai_orchestrator_shadow_planner_workspace"
_SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY = (
    "full_ai_orchestrator_shadow_planner_recommendation"
)
_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY = (
    "full_ai_orchestrator_shadow_planner_comparison"
)
_SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY = "full_ai_orchestrator_shadow_planner_timeline"
_STEP_KEY_VERSION = "v1"
_GUARDED_SKIP_CHASE_ROUND_NUMBER = 2
_GUARDED_CHASE_ROLLOUT_ENV = "ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT"
_GUARDED_ROLLOUT_PROFILE_ENV = "ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE"
_GUARDED_ROLLOUT_POLICY_VERSION = "guarded-rollout.v1"
_GUARDED_READINESS_ARTIFACT_KEY = "full_ai_orchestrator_guarded_readiness"
_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
_GUARDED_PROFILE_SHADOW_ONLY = "shadow_only"
_GUARDED_PROFILE_DRY_RUN = FullAIOrchestratorGuardedRolloutProfile.GUARDED_DRY_RUN.value
_GUARDED_PROFILE_CHASE_ONLY = (
    FullAIOrchestratorGuardedRolloutProfile.GUARDED_CHASE_ONLY.value
)
_GUARDED_PROFILE_SOURCE_CHASE = (
    FullAIOrchestratorGuardedRolloutProfile.GUARDED_SOURCE_CHASE.value
)
_GUARDED_PROFILE_LOW_RISK = (
    FullAIOrchestratorGuardedRolloutProfile.GUARDED_LOW_RISK.value
)
_VALID_GUARDED_ROLLOUT_PROFILES = frozenset(
    {
        _GUARDED_PROFILE_SHADOW_ONLY,
        _GUARDED_PROFILE_DRY_RUN,
        _GUARDED_PROFILE_CHASE_ONLY,
        _GUARDED_PROFILE_SOURCE_CHASE,
        _GUARDED_PROFILE_LOW_RISK,
    },
)
_GUARDED_STRATEGY_STRUCTURED_SOURCE = "prioritized_structured_sequence"
_GUARDED_STRATEGY_CHASE_SELECTION = "chase_selection"
_GUARDED_STRATEGY_TERMINAL_CONTROL = "terminal_control_flow"
_GUARDED_STRATEGY_BRIEF_GENERATION = "brief_generation"
_GUARDED_PROFILE_ALLOWED_STRATEGIES = {
    _GUARDED_PROFILE_SHADOW_ONLY: frozenset[str](),
    _GUARDED_PROFILE_DRY_RUN: frozenset[str](),
    _GUARDED_PROFILE_CHASE_ONLY: frozenset(
        {
            _GUARDED_STRATEGY_CHASE_SELECTION,
            _GUARDED_STRATEGY_TERMINAL_CONTROL,
            _GUARDED_STRATEGY_BRIEF_GENERATION,
        },
    ),
    _GUARDED_PROFILE_SOURCE_CHASE: frozenset(
        {
            _GUARDED_STRATEGY_STRUCTURED_SOURCE,
            _GUARDED_STRATEGY_CHASE_SELECTION,
            _GUARDED_STRATEGY_TERMINAL_CONTROL,
        },
    ),
    _GUARDED_PROFILE_LOW_RISK: frozenset(
        {
            _GUARDED_STRATEGY_STRUCTURED_SOURCE,
            _GUARDED_STRATEGY_CHASE_SELECTION,
            _GUARDED_STRATEGY_TERMINAL_CONTROL,
            _GUARDED_STRATEGY_BRIEF_GENERATION,
        },
    ),
}
_CONTROL_ACTIONS = frozenset(
    {
        ResearchOrchestratorActionType.INITIALIZE_WORKSPACE,
        ResearchOrchestratorActionType.DERIVE_DRIVEN_TERMS,
        ResearchOrchestratorActionType.RUN_BOOTSTRAP,
        ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        ResearchOrchestratorActionType.GENERATE_BRIEF,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
        ResearchOrchestratorActionType.STOP,
    },
)
_SOURCE_ACTIONS = frozenset(
    {
        ResearchOrchestratorActionType.QUERY_PUBMED,
        ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
        ResearchOrchestratorActionType.REVIEW_PDF_WORKSET,
        ResearchOrchestratorActionType.REVIEW_TEXT_WORKSET,
        ResearchOrchestratorActionType.LOAD_MONDO_GROUNDING,
        ResearchOrchestratorActionType.RUN_UNIPROT_GROUNDING,
        ResearchOrchestratorActionType.RUN_HGNC_GROUNDING,
        ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
    },
)
_ACTION_REGISTRY: tuple[ResearchOrchestratorActionSpec, ...] = (
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.INITIALIZE_WORKSPACE,
        planner_state="context_only",
        summary="Initialize the durable workspace from request inputs.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="pubmed",
        planner_state="live",
        summary="Run deterministic PubMed discovery queries.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="pubmed",
        planner_state="live",
        summary="Ingest selected PubMed documents and extract evidence-backed proposals.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.DERIVE_DRIVEN_TERMS,
        planner_state="context_only",
        summary="Derive Round 2 driven terms from PubMed findings plus seed terms.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.REVIEW_PDF_WORKSET,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="pdf",
        planner_state="context_only",
        summary="Review the current PDF workset as existing user-supplied evidence.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.REVIEW_TEXT_WORKSET,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="text",
        planner_state="context_only",
        summary="Review the current text workset as existing user-supplied evidence.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.LOAD_MONDO_GROUNDING,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="mondo",
        planner_state="context_only",
        summary="Load MONDO grounding context as a deferred ontology step.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_UNIPROT_GROUNDING,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="uniprot",
        planner_state="reserved",
        summary="Reserve an explicit UniProt grounding action for later phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_HGNC_GROUNDING,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="hgnc",
        planner_state="reserved",
        summary="Reserve an explicit HGNC grounding action for later phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
        source_bound=True,
        requires_enabled_source=True,
        planner_state="live",
        summary="Run deterministic structured enrichment for one enabled source.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
        planner_state="live",
        summary="Queue and execute governed research bootstrap as a child run.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        planner_state="live",
        summary="Run one deterministic chase round over newly created entities.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_GRAPH_CONNECTION,
        planner_state="reserved",
        summary="Reserve a graph-connection action for later planner-led phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_HYPOTHESIS_GENERATION,
        planner_state="reserved",
        summary="Reserve a hypothesis-generation action for later planner-led phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_GRAPH_SEARCH,
        planner_state="reserved",
        summary="Reserve a graph-search action for later planner-led phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.SEARCH_DISCONFIRMING,
        planner_state="reserved",
        summary="Reserve a disconfirming-evidence search action for later phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
        planner_state="live",
        summary="Generate and store the final research brief.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
        planner_state="live",
        summary="Escalate a blocked or risky run to a human operator.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.STOP,
        planner_state="live",
        summary="Record the terminal stop reason for the orchestrator run.",
    ),
)


















_ACTION_SPEC_BY_TYPE = {spec.action_type: spec for spec in _ACTION_REGISTRY}
_STRUCTURED_ENRICHMENT_SOURCES = (
    "clinvar",
    "drugbank",
    "alphafold",
    "clinical_trials",
    "mgi",
    "zfin",
    "marrvel",
)
_SHADOW_PLANNER_CHECKPOINT_ORDER = (
    "before_first_action",
    "after_pubmed_discovery",
    "after_pubmed_ingest_extract",
    "after_driven_terms_ready",
    "after_bootstrap",
    "after_chase_round_1",
    "after_chase_round_2",
    "before_brief_generation",
    "before_terminal_stop",
)


@dataclass(frozen=True, slots=True)
class FullAIOrchestratorExecutionResult:
    """Terminal result for one deterministic full AI orchestrator run."""

    run: HarnessRunRecord
    planner_mode: FullAIOrchestratorPlannerMode
    guarded_rollout_profile: str | None
    guarded_rollout_profile_source: str | None
    research_init_result: ResearchInitExecutionResult
    action_history: tuple[ResearchOrchestratorDecision, ...]
    workspace_summary: JSONObject
    source_execution_summary: JSONObject
    bootstrap_summary: JSONObject | None
    brief_metadata: JSONObject
    shadow_planner: JSONObject | None
    guarded_execution: JSONObject | None
    guarded_decision_proofs: JSONObject | None
    errors: list[str]



def _planner_mode_value(mode: FullAIOrchestratorPlannerMode | str) -> str:
    return mode.value if isinstance(mode, FullAIOrchestratorPlannerMode) else str(mode)

def _workspace_list(
    workspace_snapshot: JSONObject,
    key: str,
) -> list[object]:
    value = workspace_snapshot.get(key)
    return list(value) if isinstance(value, list) else []

def _workspace_object(
    workspace_snapshot: JSONObject,
    key: str,
) -> JSONObject:
    value = workspace_snapshot.get(key)
    return dict(value) if isinstance(value, dict) else {}

def _normalized_source_key_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]

def _pending_chase_round_summary(workspace_snapshot: JSONObject) -> JSONObject:
    pending = workspace_snapshot.get("pending_chase_round")
    return dict(pending) if isinstance(pending, dict) else {}

def _chase_selection_from_summary(
    *,
    summary: JSONObject,
) -> ResearchOrchestratorChaseSelection | None:
    for selection_key in (
        "effective_selection",
        "guarded_selection",
        "deterministic_selection",
    ):
        selection = summary.get(selection_key)
        if not isinstance(selection, dict):
            continue
        try:
            return ResearchOrchestratorChaseSelection.model_validate(selection)
        except ValidationError:
            continue
    return None

def _chase_round_action_input_from_workspace(
    *,
    workspace_snapshot: JSONObject,
    round_number: int,
) -> JSONObject:
    chase_summary = workspace_snapshot.get(f"chase_round_{round_number}")
    if isinstance(chase_summary, dict):
        return {
            "round_number": round_number,
            "selected_entity_ids": _normalized_source_key_list(
                chase_summary.get("selected_entity_ids"),
            ),
            "selected_labels": _normalized_source_key_list(
                chase_summary.get("selected_labels"),
            ),
            "selection_basis": (
                str(chase_summary.get("selection_basis"))
                if isinstance(chase_summary.get("selection_basis"), str)
                else "Deterministic chase-round selection."
            ),
        }
    pending_summary = _pending_chase_round_summary(workspace_snapshot)
    if pending_summary.get("round_number") != round_number:
        return {"round_number": round_number}
    selection = _chase_selection_from_summary(summary=pending_summary)
    if selection is None:
        return {"round_number": round_number}
    return {
        "round_number": round_number,
        "selected_entity_ids": list(selection.selected_entity_ids),
        "selected_labels": list(selection.selected_labels),
        "selection_basis": selection.selection_basis,
    }

def _chase_round_metadata_from_workspace(
    *,
    workspace_snapshot: JSONObject,
    round_number: int,
) -> JSONObject:
    chase_summary = workspace_snapshot.get(f"chase_round_{round_number}")
    if isinstance(chase_summary, dict):
        return dict(chase_summary)
    pending_summary = _pending_chase_round_summary(workspace_snapshot)
    if pending_summary.get("round_number") != round_number:
        return {}
    return dict(pending_summary)

def _chase_round_stop_reason(metadata: JSONObject) -> str:
    selection = _chase_selection_from_summary(summary=metadata)
    if selection is not None and selection.stop_reason:
        return selection.stop_reason
    return "threshold_not_met"

def _source_status(source_results: JSONObject, source_key: str) -> str | None:
    source_summary = source_results.get(source_key)
    if not isinstance(source_summary, dict):
        return None
    status = source_summary.get("status")
    return status if isinstance(status, str) else None

def _guarded_structured_verification_payload(
    *,
    source_results: JSONObject,
    action: JSONObject,
) -> tuple[str, str, JSONObject]:
    guarded_strategy = action.get("guarded_strategy")
    selected_source_key = action.get("applied_source_key")
    if not isinstance(selected_source_key, str):
        return (
            "verification_failed",
            "selected_source_missing",
            {
                "selected_source_key": selected_source_key,
                "source_results_present": bool(source_results),
            },
        )

    ordered_keys = _normalized_source_key_list(action.get("ordered_source_keys"))
    deferred_keys = _normalized_source_key_list(action.get("deferred_source_keys"))
    selected_source_status = _source_status(source_results, selected_source_key)
    ordered_source_statuses = {
        source_key: _source_status(source_results, source_key)
        for source_key in ordered_keys
    }
    deferred_source_statuses = {
        source_key: _source_status(source_results, source_key)
        for source_key in deferred_keys
    }
    incomplete_ordered_sources: list[JSONObject] = []
    unexpected_deferred_sources: list[JSONObject] = []

    if guarded_strategy == _GUARDED_STRATEGY_STRUCTURED_SOURCE:
        for source_key, ordered_status in ordered_source_statuses.items():
            if ordered_status not in {"completed", "failed"}:
                incomplete_ordered_sources.append(
                    {"source_key": source_key, "status": ordered_status},
                )
            source_summary = source_results.get(source_key)
            if (
                isinstance(source_summary, dict)
                and source_summary.get("deferred_reason") == "guarded_source_selection"
            ):
                unexpected_deferred_sources.append(
                    {"source_key": source_key, "status": ordered_status},
                )
    else:
        for source_key, deferred_status in deferred_source_statuses.items():
            if deferred_status not in {"deferred", "skipped"}:
                incomplete_ordered_sources.append(
                    {"source_key": source_key, "status": deferred_status},
                )

    verification_status, verification_reason = _guarded_structured_verification_outcome(
        guarded_strategy=guarded_strategy,
        selected_source_status=selected_source_status,
        incomplete_ordered_sources=incomplete_ordered_sources,
        unexpected_deferred_sources=unexpected_deferred_sources,
    )

    return (
        verification_status,
        verification_reason,
        {
            "guarded_strategy": guarded_strategy,
            "ordered_source_keys": ordered_keys,
            "ordered_source_statuses": ordered_source_statuses,
            "selected_source_key": selected_source_key,
            "selected_source_status": selected_source_status,
            "deferred_source_statuses": deferred_source_statuses,
            "incomplete_ordered_sources": incomplete_ordered_sources,
            "unexpected_deferred_sources": unexpected_deferred_sources,
        },
    )

def _guarded_structured_verification_outcome(
    *,
    guarded_strategy: object,
    selected_source_status: str | None,
    incomplete_ordered_sources: list[JSONObject],
    unexpected_deferred_sources: list[JSONObject],
) -> tuple[str, str]:
    if selected_source_status not in {"completed", "failed"}:
        return "verification_failed", "selected_source_not_completed"
    if guarded_strategy == _GUARDED_STRATEGY_STRUCTURED_SOURCE:
        if incomplete_ordered_sources:
            return "verification_failed", "ordered_sources_not_completed"
        if unexpected_deferred_sources:
            return "verification_failed", "ordered_sources_deferred"
        return "verified", "ordered_sources_completed"
    if incomplete_ordered_sources:
        return "verification_failed", "deferred_sources_executed"
    return "verified", "selected_source_completed"

def _source_decision_status(
    *,
    source_summary: JSONObject,
    pending_status: str,
) -> tuple[str, str | None]:
    source_status = source_summary.get("status")
    if source_status == "completed":
        return "completed", None
    if source_status == "failed":
        return "failed", "source_failed"
    if source_status == "pending":
        return pending_status, None
    if source_status == "deferred":
        deferred_reason = source_summary.get("deferred_reason")
        if deferred_reason == "guarded_source_selection":
            return "skipped", "guarded_source_deferred"
        return "skipped", "source_deferred"
    return "skipped", "source_not_executed"

def orchestrator_action_registry() -> tuple[ResearchOrchestratorActionSpec, ...]:
    """Return the allowlisted Phase 1 action registry."""
    return _ACTION_REGISTRY

def is_source_action(action_type: ResearchOrchestratorActionType) -> bool:
    """Return whether an orchestrator action is source-bound."""
    return action_type in _SOURCE_ACTIONS

def is_control_action(action_type: ResearchOrchestratorActionType) -> bool:
    """Return whether an orchestrator action is pure control flow."""
    return action_type in _CONTROL_ACTIONS

def require_action_enabled_for_sources(
    *,
    action_type: ResearchOrchestratorActionType,
    source_key: str | None,
    sources: ResearchSpaceSourcePreferences,
) -> None:
    """Raise when a source-bound action targets a disabled source."""
    if not is_source_action(action_type):
        return
    resolved_source_key = (
        source_key
        if source_key is not None
        else _ACTION_SPEC_BY_TYPE[action_type].default_source_key
    )
    if resolved_source_key is None:
        return
    if sources.get(resolved_source_key, False):
        return
    msg = (
        f"Action '{action_type.value}' is unavailable because source "
        f"'{resolved_source_key}' is disabled."
    )
    raise ValueError(msg)

def build_step_key(
    *,
    action_type: ResearchOrchestratorActionType,
    round_number: int,
    source_key: str | None = None,
) -> str:
    """Return the stable step key for one deterministic action."""
    normalized_action = action_type.value.casefold()
    source_segment = source_key if source_key is not None else "control"
    return (
        f"{_HARNESS_ID}.{_STEP_KEY_VERSION}.round_{round_number}."
        f"{source_segment}.{normalized_action}"
    )

