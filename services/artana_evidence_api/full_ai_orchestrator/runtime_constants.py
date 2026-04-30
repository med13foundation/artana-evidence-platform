"""Constants for the full-AI orchestrator runtime."""

from __future__ import annotations

import logging
import os

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
)

_LOGGER = logging.getLogger("artana_evidence_api.full_ai_orchestrator_runtime")
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

__all__ = [
    "_ACTION_REGISTRY_ARTIFACT_KEY",
    "_BOOTSTRAP_ARTIFACT_KEY",
    "_BRIEF_METADATA_ARTIFACT_KEY",
    "_CHASE_ROUNDS_ARTIFACT_KEY",
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
    "_SHADOW_PLANNER_CHECKPOINT_ORDER",
    "_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY",
    "_SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY",
    "_SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY",
    "_SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY",
    "_SOURCE_EXECUTION_ARTIFACT_KEY",
    "_STEP_KEY_VERSION",
    "_STRUCTURED_ENRICHMENT_SOURCES",
    "_TRUE_ENV_VALUES",
    "_VALID_GUARDED_ROLLOUT_PROFILES",
]
