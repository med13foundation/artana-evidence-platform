"""Guarded rollout profile helpers for the full AI orchestrator."""

from __future__ import annotations

import logging
import os

from artana_evidence_api.full_ai_orchestrator.workspace_support import (
    _planner_mode_value,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSettings,
)

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


def _guarded_chase_rollout_enabled() -> bool:
    return os.getenv(_GUARDED_CHASE_ROLLOUT_ENV, "").strip().lower() in _TRUE_ENV_VALUES


def _normalize_guarded_rollout_profile(value: object) -> str | None:
    if isinstance(value, FullAIOrchestratorGuardedRolloutProfile):
        return value.value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _VALID_GUARDED_ROLLOUT_PROFILES:
            return normalized
    return None


def resolve_guarded_rollout_profile(
    *,
    planner_mode: FullAIOrchestratorPlannerMode,
    request_profile: FullAIOrchestratorGuardedRolloutProfile | str | None = None,
    space_settings: ResearchSpaceSettings | None = None,
) -> tuple[str, str]:
    """Resolve guarded planner authority with request > space > env precedence."""
    if planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
        return _GUARDED_PROFILE_SHADOW_ONLY, "planner_mode"
    normalized_request_profile = _normalize_guarded_rollout_profile(request_profile)
    if normalized_request_profile is not None:
        return normalized_request_profile, "request"
    if isinstance(space_settings, dict):
        normalized_space_profile = _normalize_guarded_rollout_profile(
            space_settings.get("full_ai_guarded_rollout_profile"),
        )
        if normalized_space_profile is not None:
            return normalized_space_profile, "space_setting"
    raw_profile = os.getenv(_GUARDED_ROLLOUT_PROFILE_ENV, "").strip().lower()
    if raw_profile in _VALID_GUARDED_ROLLOUT_PROFILES:
        return raw_profile, "environment"
    if _guarded_chase_rollout_enabled():
        return _GUARDED_PROFILE_CHASE_ONLY, "legacy_chase_env"
    return _GUARDED_PROFILE_SOURCE_CHASE, "default"


def _guarded_rollout_profile(
    *,
    planner_mode: FullAIOrchestratorPlannerMode,
) -> str:
    profile, _source = resolve_guarded_rollout_profile(planner_mode=planner_mode)
    return profile


def _guarded_allowed_strategies(*, guarded_rollout_profile: str) -> frozenset[str]:
    return _GUARDED_PROFILE_ALLOWED_STRATEGIES.get(
        guarded_rollout_profile,
        frozenset(),
    )


def _guarded_profile_allows(
    *,
    guarded_rollout_profile: str,
    guarded_strategy: str,
) -> bool:
    return guarded_strategy in _guarded_allowed_strategies(
        guarded_rollout_profile=guarded_rollout_profile,
    )


def _guarded_profile_allows_chase(
    *,
    guarded_rollout_profile: str,
) -> bool:
    return _guarded_profile_allows(
        guarded_rollout_profile=guarded_rollout_profile,
        guarded_strategy=_GUARDED_STRATEGY_CHASE_SELECTION,
    )


def _guarded_rollout_policy_summary(
    *,
    planner_mode: FullAIOrchestratorPlannerMode,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str = "resolved",
) -> JSONObject:
    return {
        "policy_version": _GUARDED_ROLLOUT_POLICY_VERSION,
        "mode": _planner_mode_value(planner_mode),
        "profile": guarded_rollout_profile,
        "profile_source": guarded_rollout_profile_source,
        "fail_closed": True,
        "eligible_guarded_strategies": sorted(
            _guarded_allowed_strategies(
                guarded_rollout_profile=guarded_rollout_profile,
            ),
        ),
        "checks": {
            "reject_invalid_planner_output": True,
            "reject_fallback_recommendations": True,
            "reject_disabled_or_unavailable_actions": True,
            "require_non_empty_qualitative_rationale": True,
            "require_post_execution_verification": True,
        },
    }


__all__ = [
    "_ACTION_REGISTRY",
    "_ACTION_REGISTRY_ARTIFACT_KEY",
    "_BOOTSTRAP_ARTIFACT_KEY",
    "_BRIEF_METADATA_ARTIFACT_KEY",
    "_CHASE_ROUNDS_ARTIFACT_KEY",
    "_CONTROL_ACTIONS",
    "_DECISION_HISTORY_ARTIFACT_KEY",
    "_DRIVEN_TERMS_ARTIFACT_KEY",
    "_GUARDED_CHASE_ROLLOUT_ENV",
    "_GUARDED_DECISION_PROOF_ARTIFACT_PREFIX",
    "_GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY",
    "_GUARDED_EXECUTION_ARTIFACT_KEY",
    "_GUARDED_PROFILE_ALLOWED_STRATEGIES",
    "_GUARDED_PROFILE_CHASE_ONLY",
    "_GUARDED_PROFILE_DRY_RUN",
    "_GUARDED_PROFILE_LOW_RISK",
    "_GUARDED_PROFILE_SHADOW_ONLY",
    "_GUARDED_PROFILE_SOURCE_CHASE",
    "_GUARDED_READINESS_ARTIFACT_KEY",
    "_GUARDED_ROLLOUT_POLICY_VERSION",
    "_GUARDED_ROLLOUT_PROFILE_ENV",
    "_GUARDED_SKIP_CHASE_ROUND_NUMBER",
    "_GUARDED_STRATEGY_BRIEF_GENERATION",
    "_GUARDED_STRATEGY_CHASE_SELECTION",
    "_GUARDED_STRATEGY_STRUCTURED_SOURCE",
    "_GUARDED_STRATEGY_TERMINAL_CONTROL",
    "_HARNESS_ID",
    "_INITIALIZE_ARTIFACT_KEY",
    "_LOGGER",
    "_PROGRESS_PERSISTENCE_BACKOFF_SECONDS",
    "_PUBMED_ARTIFACT_KEY",
    "_PUBMED_REPLAY_ARTIFACT_KEY",
    "_RESULT_ARTIFACT_KEY",
    "_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY",
    "_SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY",
    "_SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY",
    "_SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY",
    "_SOURCE_ACTIONS",
    "_SOURCE_EXECUTION_ARTIFACT_KEY",
    "_STEP_KEY_VERSION",
    "_TRUE_ENV_VALUES",
    "_VALID_GUARDED_ROLLOUT_PROFILES",
    "_guarded_allowed_strategies",
    "_guarded_chase_rollout_enabled",
    "_guarded_profile_allows",
    "_guarded_profile_allows_chase",
    "_guarded_rollout_policy_summary",
    "_guarded_rollout_profile",
    "_normalize_guarded_rollout_profile",
    "resolve_guarded_rollout_profile",
]
