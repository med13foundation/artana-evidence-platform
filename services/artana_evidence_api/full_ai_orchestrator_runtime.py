"""Deterministic Phase 1 full AI orchestrator runtime.

This module is kept as the compatibility facade. Implementation details live in
smaller runtime modules grouped by queueing, execution, observer state, guarded
selection, shadow checkpoints, artifacts, and response serialization.
"""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator_common_support import (
    build_step_key,
    is_control_action,
    is_source_action,
    orchestrator_action_registry,
    require_action_enabled_for_sources,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorChaseCandidate,
)
from artana_evidence_api.full_ai_orchestrator_execute import (
    execute_full_ai_orchestrator_run,
)
from artana_evidence_api.full_ai_orchestrator_guarded_rollout import (
    resolve_guarded_rollout_profile,
)
from artana_evidence_api.full_ai_orchestrator_guarded_support import (
    _guarded_readiness_summary,
)
from artana_evidence_api.full_ai_orchestrator_initial_decisions import (
    _build_initial_decision_history,
)
from artana_evidence_api.full_ai_orchestrator_progress_observer import (
    _FullAIOrchestratorProgressObserver,
)
from artana_evidence_api.full_ai_orchestrator_queue import (
    queue_full_ai_orchestrator_run,
)
from artana_evidence_api.full_ai_orchestrator_response import (
    build_full_ai_orchestrator_run_response,
)
from artana_evidence_api.full_ai_orchestrator_runtime_artifacts import (
    load_pubmed_replay_bundle_artifact,
    store_pubmed_replay_bundle_artifact,
)
from artana_evidence_api.full_ai_orchestrator_runtime_constants import (
    _GUARDED_CHASE_ROLLOUT_ENV,
    _GUARDED_PROFILE_CHASE_ONLY,
    _GUARDED_PROFILE_DRY_RUN,
    _GUARDED_PROFILE_LOW_RISK,
    _GUARDED_PROFILE_SOURCE_CHASE,
    _GUARDED_ROLLOUT_PROFILE_ENV,
    _STRUCTURED_ENRICHMENT_SOURCES,
)
from artana_evidence_api.full_ai_orchestrator_runtime_models import (
    FullAIOrchestratorExecutionResult,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    recommend_shadow_planner_action,
)
from artana_evidence_api.full_ai_orchestrator_shadow_support import (
    _accepted_guarded_chase_selection_action,
    _accepted_guarded_control_flow_action,
    _accepted_guarded_generate_brief_action,
    _accepted_guarded_structured_source_action,
    _checkpoint_target_decision,
)
from artana_evidence_api.research_init_runtime import execute_research_init_run
from artana_evidence_api.transparency import ensure_run_transparency_seed

__all__ = [
    "FullAIOrchestratorExecutionResult",
    "ResearchOrchestratorChaseCandidate",
    "_FullAIOrchestratorProgressObserver",
    "_GUARDED_CHASE_ROLLOUT_ENV",
    "_GUARDED_PROFILE_CHASE_ONLY",
    "_GUARDED_PROFILE_DRY_RUN",
    "_GUARDED_PROFILE_LOW_RISK",
    "_GUARDED_PROFILE_SOURCE_CHASE",
    "_GUARDED_ROLLOUT_PROFILE_ENV",
    "_STRUCTURED_ENRICHMENT_SOURCES",
    "_accepted_guarded_chase_selection_action",
    "_accepted_guarded_control_flow_action",
    "_accepted_guarded_generate_brief_action",
    "_accepted_guarded_structured_source_action",
    "_build_initial_decision_history",
    "_checkpoint_target_decision",
    "_guarded_readiness_summary",
    "build_full_ai_orchestrator_run_response",
    "build_step_key",
    "execute_full_ai_orchestrator_run",
    "execute_research_init_run",
    "ensure_run_transparency_seed",
    "is_control_action",
    "is_source_action",
    "load_pubmed_replay_bundle_artifact",
    "orchestrator_action_registry",
    "queue_full_ai_orchestrator_run",
    "recommend_shadow_planner_action",
    "require_action_enabled_for_sources",
    "resolve_guarded_rollout_profile",
    "store_pubmed_replay_bundle_artifact",
]
