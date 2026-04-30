"""Queueing entry point for full-AI orchestrator runs."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator_common_support import (
    _planner_mode_value,
    orchestrator_action_registry,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.full_ai_orchestrator_guarded_rollout import (
    _guarded_profile_allows_chase,
    _guarded_rollout_policy_summary,
    resolve_guarded_rollout_profile,
)
from artana_evidence_api.full_ai_orchestrator_guarded_support import (
    _guarded_decision_proof_summary,
    _guarded_execution_summary,
    _guarded_readiness_summary,
    _put_decision_history_artifact,
    _put_guarded_decision_proof_artifacts,
    _put_guarded_execution_artifact,
    _put_guarded_readiness_artifact,
)
from artana_evidence_api.full_ai_orchestrator_initial_decisions import (
    _build_initial_decision_history,
)
from artana_evidence_api.full_ai_orchestrator_runtime_artifacts import (
    _store_pending_action_output_artifacts,
)
from artana_evidence_api.full_ai_orchestrator_runtime_constants import (
    _ACTION_REGISTRY_ARTIFACT_KEY,
    _DECISION_HISTORY_ARTIFACT_KEY,
    _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY,
    _GUARDED_EXECUTION_ARTIFACT_KEY,
    _GUARDED_READINESS_ARTIFACT_KEY,
    _HARNESS_ID,
    _INITIALIZE_ARTIFACT_KEY,
    _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
    _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
    _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
    _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
    _STEP_KEY_VERSION,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    build_shadow_planner_workspace_summary,
)
from artana_evidence_api.research_init_source_results import build_source_results
from artana_evidence_api.transparency import (
    ensure_run_transparency_seed as _default_ensure_run_transparency_seed,
)
from artana_evidence_api.types.common import (
    ResearchSpaceSourcePreferences,
    json_object_or_empty,
)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

_TransparencySeeder = Callable[..., None]


def ensure_run_transparency_seed(**kwargs: object) -> None:
    facade = sys.modules.get("artana_evidence_api.full_ai_orchestrator_runtime")
    candidate = getattr(facade, "ensure_run_transparency_seed", None)
    if candidate is None or candidate is ensure_run_transparency_seed:
        candidate = _default_ensure_run_transparency_seed
    cast("_TransparencySeeder", candidate)(**kwargs)


def queue_full_ai_orchestrator_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    objective: str,
    seed_terms: list[str],
    sources: ResearchSpaceSourcePreferences,
    max_depth: int,
    max_hypotheses: int,
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    execution_services: HarnessExecutionServices,
    planner_mode: FullAIOrchestratorPlannerMode = (
        FullAIOrchestratorPlannerMode.SHADOW
    ),
    guarded_rollout_profile: (
        FullAIOrchestratorGuardedRolloutProfile | str | None
    ) = None,
    guarded_rollout_profile_source: str | None = None,
) -> HarnessRunRecord:
    """Create a queued full AI orchestrator run without executing it inline."""
    resolved_guarded_rollout_profile, resolved_guarded_rollout_profile_source = (
        resolve_guarded_rollout_profile(
            planner_mode=planner_mode,
            request_profile=guarded_rollout_profile,
        )
    )
    if guarded_rollout_profile_source is not None:
        resolved_guarded_rollout_profile_source = guarded_rollout_profile_source
    guarded_chase_rollout_enabled = _guarded_profile_allows_chase(
        guarded_rollout_profile=resolved_guarded_rollout_profile,
    )
    source_results = build_source_results(sources=sources)
    shadow_workspace_summary = build_shadow_planner_workspace_summary(
        checkpoint_key="before_first_action",
        mode=_planner_mode_value(planner_mode),
        objective=objective,
        seed_terms=seed_terms,
        sources=sources,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        workspace_snapshot={
            "source_results": source_results,
            "current_round": 0,
            "documents_ingested": 0,
            "proposal_count": 0,
            "pending_questions": [],
            "errors": [],
        },
        prior_decisions=[],
        action_registry=orchestrator_action_registry(),
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id=_HARNESS_ID,
        title=title,
        input_payload={
            "objective": objective,
            "seed_terms": list(seed_terms),
            "sources": json_object_or_empty(sources),
            "planner_mode": _planner_mode_value(planner_mode),
            "guarded_rollout_profile": resolved_guarded_rollout_profile,
            "guarded_rollout_profile_source": resolved_guarded_rollout_profile_source,
            "guarded_chase_rollout_enabled": guarded_chase_rollout_enabled,
            "max_depth": max_depth,
            "max_hypotheses": max_hypotheses,
        },
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=_ACTION_REGISTRY_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "harness_id": _HARNESS_ID,
            "version": _STEP_KEY_VERSION,
            "actions": [
                spec.model_dump(mode="json") for spec in orchestrator_action_registry()
            ],
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=_INITIALIZE_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "objective": objective,
            "seed_terms": list(seed_terms),
            "sources": json_object_or_empty(sources),
            "planner_mode": _planner_mode_value(planner_mode),
            "guarded_rollout_profile": resolved_guarded_rollout_profile,
            "guarded_rollout_profile_source": resolved_guarded_rollout_profile_source,
            "guarded_rollout_policy": _guarded_rollout_policy_summary(
                planner_mode=planner_mode,
                guarded_rollout_profile=resolved_guarded_rollout_profile,
                guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            ),
            "guarded_chase_rollout_enabled": guarded_chase_rollout_enabled,
            "max_depth": max_depth,
            "max_hypotheses": max_hypotheses,
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=_SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
        media_type="application/json",
        content=shadow_workspace_summary,
    )
    initial_decisions = _build_initial_decision_history(
        objective=objective,
        seed_terms=seed_terms,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        sources=sources,
    )
    _put_decision_history_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        decisions=initial_decisions,
    )
    _put_guarded_execution_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        planner_mode=planner_mode,
        actions=[],
    )
    _put_guarded_readiness_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        planner_mode=planner_mode,
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
        actions=[],
    )
    if planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
        _put_guarded_decision_proof_artifacts(
            artifact_store=artifact_store,
            space_id=space_id,
            run_id=run.id,
            planner_mode=planner_mode,
            guarded_rollout_profile=resolved_guarded_rollout_profile,
            guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            proofs=[],
        )
    _store_pending_action_output_artifacts(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        objective=objective,
        seed_terms=seed_terms,
        sources=sources,
        planner_mode=planner_mode,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "objective": objective,
            "seed_terms": list(seed_terms),
            "enabled_sources": json_object_or_empty(sources),
            "sources": json_object_or_empty(sources),
            "current_round": 0,
            "source_results": source_results,
            "documents_ingested": 0,
            "proposal_count": 0,
            "pending_questions": [],
            "errors": [],
            "bootstrap_run_id": None,
            "bootstrap_summary": None,
            "chase_round_summaries": [],
            "brief_result_key": "research_brief",
            "decision_history_key": _DECISION_HISTORY_ARTIFACT_KEY,
            "action_registry_key": _ACTION_REGISTRY_ARTIFACT_KEY,
            "shadow_planner_mode": _planner_mode_value(planner_mode),
            "planner_execution_mode": _planner_mode_value(planner_mode),
            "guarded_rollout_profile": resolved_guarded_rollout_profile,
            "guarded_rollout_profile_source": resolved_guarded_rollout_profile_source,
            "guarded_rollout_policy": _guarded_rollout_policy_summary(
                planner_mode=planner_mode,
                guarded_rollout_profile=resolved_guarded_rollout_profile,
                guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            ),
            "guarded_chase_rollout_enabled": guarded_chase_rollout_enabled,
            "shadow_planner_workspace_key": _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
            "shadow_planner_recommendation_key": (
                _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY
            ),
            "shadow_planner_comparison_key": _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
            "shadow_planner_timeline_key": _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
            "guarded_execution_log_key": _GUARDED_EXECUTION_ARTIFACT_KEY,
            "guarded_readiness_key": _GUARDED_READINESS_ARTIFACT_KEY,
            "guarded_execution": _guarded_execution_summary(
                planner_mode=planner_mode,
                actions=[],
            ),
            "guarded_readiness": _guarded_readiness_summary(
                planner_mode=planner_mode,
                guarded_rollout_profile=resolved_guarded_rollout_profile,
                guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
                actions=[],
            ),
            "decision_count": len(initial_decisions),
            "last_decision_id": initial_decisions[-1].decision_id,
        },
    )
    if planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "guarded_decision_proofs_key": (
                    _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
                ),
                "guarded_decision_proofs": _guarded_decision_proof_summary(
                    planner_mode=planner_mode,
                    guarded_rollout_profile=resolved_guarded_rollout_profile,
                    guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
                    proofs=[],
                ),
            },
        )
    return run
