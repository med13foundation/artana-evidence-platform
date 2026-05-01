"""Execution entry point for full-AI orchestrator runs."""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator.action_registry import (
    orchestrator_action_registry,
)
from artana_evidence_api.full_ai_orchestrator.guarded.rollout import (
    _guarded_profile_allows_chase,
    _guarded_rollout_policy_summary,
    resolve_guarded_rollout_profile,
)
from artana_evidence_api.full_ai_orchestrator.guarded.support import (
    _guarded_decision_proof_summary,
    _guarded_execution_summary,
    _guarded_readiness_summary,
    _put_decision_history_artifact,
    _put_guarded_decision_proof_artifacts,
    _put_guarded_execution_artifact,
    _put_guarded_readiness_artifact,
    _put_shadow_planner_artifacts,
)
from artana_evidence_api.full_ai_orchestrator.initial_decisions import (
    _build_initial_decision_history,
)
from artana_evidence_api.full_ai_orchestrator.progress.observer import (
    _FullAIOrchestratorProgressObserver,
)
from artana_evidence_api.full_ai_orchestrator.response import (
    build_full_ai_orchestrator_run_response,
)
from artana_evidence_api.full_ai_orchestrator.response_support import (
    _build_brief_metadata,
    _build_decision_history,
    _build_source_execution_summary,
    _build_workspace_summary,
    _collect_chase_round_summaries,
    _sanitize_replayed_workspace_snapshot,
    _store_action_output_artifacts,
)
from artana_evidence_api.full_ai_orchestrator.runtime_artifacts import (
    load_pubmed_replay_bundle_artifact,
)
from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _ACTION_REGISTRY_ARTIFACT_KEY,
    _BOOTSTRAP_ARTIFACT_KEY,
    _BRIEF_METADATA_ARTIFACT_KEY,
    _CHASE_ROUNDS_ARTIFACT_KEY,
    _DECISION_HISTORY_ARTIFACT_KEY,
    _DRIVEN_TERMS_ARTIFACT_KEY,
    _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY,
    _GUARDED_EXECUTION_ARTIFACT_KEY,
    _GUARDED_READINESS_ARTIFACT_KEY,
    _INITIALIZE_ARTIFACT_KEY,
    _PUBMED_ARTIFACT_KEY,
    _RESULT_ARTIFACT_KEY,
    _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
    _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
    _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
    _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
    _SOURCE_EXECUTION_ARTIFACT_KEY,
)
from artana_evidence_api.full_ai_orchestrator.runtime_models import (
    FullAIOrchestratorExecutionResult,
)
from artana_evidence_api.full_ai_orchestrator.shadow.support import (
    _build_shadow_planner_summary,
)
from artana_evidence_api.full_ai_orchestrator.shadow_planner import (
    build_shadow_planner_workspace_summary,
)
from artana_evidence_api.full_ai_orchestrator.workspace_support import (
    _planner_mode_value,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.queued_run import store_primary_result_artifact
from artana_evidence_api.research_init.source_caps import (
    ResearchInitSourceCaps,
    default_source_caps,
    source_caps_to_json,
)
from artana_evidence_api.research_init_runtime import (
    ResearchInitExecutionResult,
    ResearchInitPubMedReplayBundle,
    ResearchInitStructuredEnrichmentReplayBundle,
)
from artana_evidence_api.research_init_runtime import (
    execute_research_init_run as _default_execute_research_init_run,
)
from artana_evidence_api.research_init_source_results import build_source_results
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_object,
)

if TYPE_CHECKING:
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.run_registry import HarnessRunRecord

_ResearchInitExecutor = Callable[..., Awaitable[ResearchInitExecutionResult]]

__all__ = [
    "_ResearchInitExecutor",
    "execute_full_ai_orchestrator_run",
    "execute_research_init_run",
]


async def execute_research_init_run(**kwargs: object) -> ResearchInitExecutionResult:
    # Preserve old-path monkeypatches while tests and external callers still patch
    # full_ai_orchestrator_runtime.execute_research_init_run.
    facade = sys.modules.get("artana_evidence_api.full_ai_orchestrator_runtime")
    candidate = getattr(facade, "execute_research_init_run", None)
    if candidate is None or candidate is execute_research_init_run:
        candidate = _default_execute_research_init_run
    return await cast("_ResearchInitExecutor", candidate)(**kwargs)


async def execute_full_ai_orchestrator_run(  # noqa: PLR0913, PLR0915
    *,
    space_id: UUID,
    title: str,
    objective: str,
    seed_terms: list[str],
    max_depth: int,
    max_hypotheses: int,
    sources: ResearchSpaceSourcePreferences,
    execution_services: HarnessExecutionServices,
    existing_run: HarnessRunRecord,
    planner_mode: FullAIOrchestratorPlannerMode = (
        FullAIOrchestratorPlannerMode.SHADOW
    ),
    guarded_rollout_profile: (
        FullAIOrchestratorGuardedRolloutProfile | str | None
    ) = None,
    guarded_rollout_profile_source: str | None = None,
    pubmed_replay_bundle: ResearchInitPubMedReplayBundle | None = None,
    structured_enrichment_replay_bundle: (
        ResearchInitStructuredEnrichmentReplayBundle | None
    ) = None,
    source_caps: ResearchInitSourceCaps | None = None,
    replayed_research_init_result: ResearchInitExecutionResult | None = None,
    replayed_workspace_snapshot: JSONObject | None = None,
    replayed_phase_records: dict[str, list[JSONObject]] | None = None,
) -> FullAIOrchestratorExecutionResult:
    """Execute the deterministic Phase 1 orchestrator baseline."""
    effective_source_caps = source_caps or default_source_caps()
    source_caps_payload = source_caps_to_json(effective_source_caps)
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
    effective_pubmed_replay_bundle = pubmed_replay_bundle
    if effective_pubmed_replay_bundle is None:
        effective_pubmed_replay_bundle = load_pubmed_replay_bundle_artifact(
            artifact_store=execution_services.artifact_store,
            space_id=space_id,
            run_id=existing_run.id,
        )
    action_registry = orchestrator_action_registry()
    initial_decisions = _build_initial_decision_history(
        objective=objective,
        seed_terms=seed_terms,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        sources=sources,
    )
    initial_workspace_summary = build_shadow_planner_workspace_summary(
        checkpoint_key="before_first_action",
        mode=_planner_mode_value(planner_mode),
        objective=objective,
        seed_terms=seed_terms,
        sources=sources,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        workspace_snapshot={
            "source_results": build_source_results(sources=sources),
            "source_caps": source_caps_payload,
            "current_round": 0,
            "documents_ingested": 0,
            "proposal_count": 0,
            "pending_questions": [],
            "errors": [],
        },
        prior_decisions=[
            decision.model_dump(mode="json") for decision in initial_decisions
        ],
        action_registry=action_registry,
    )
    progress_observer = _FullAIOrchestratorProgressObserver(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        objective=objective,
        seed_terms=list(seed_terms),
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        sources=sources,
        planner_mode=planner_mode,
        action_registry=action_registry,
        decisions=initial_decisions,
        initial_workspace_summary=initial_workspace_summary,
        phase_records={},
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
        guarded_chase_rollout_enabled=guarded_chase_rollout_enabled,
    )
    progress_observer.enqueue_initial_shadow_checkpoint()
    if replayed_research_init_result is not None:
        running_run = execution_services.run_registry.set_run_status(
            space_id=space_id,
            run_id=existing_run.id,
            status="running",
        )
        sanitized_snapshot = _sanitize_replayed_workspace_snapshot(
            replayed_workspace_snapshot,
        )
        if sanitized_snapshot:
            execution_services.artifact_store.patch_workspace(
                space_id=space_id,
                run_id=existing_run.id,
                patch=sanitized_snapshot,
            )
        research_init_result = replace(
            replayed_research_init_result,
            run=existing_run if running_run is None else running_run,
        )
        if replayed_phase_records is not None:
            progress_observer.phase_records.clear()
            progress_observer.phase_records.update(deepcopy(replayed_phase_records))
    else:
        research_init_result = await execute_research_init_run(
            space_id=space_id,
            title=title,
            objective=objective,
            seed_terms=seed_terms,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            sources=sources,
            execution_services=execution_services,
            existing_run=existing_run,
            progress_observer=progress_observer,
            pubmed_replay_bundle=effective_pubmed_replay_bundle,
            structured_enrichment_replay_bundle=structured_enrichment_replay_bundle,
            source_caps=effective_source_caps,
            complete_run_status=False,
        )
    workspace_record = execution_services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=existing_run.id,
    )
    workspace_snapshot = (
        workspace_record.snapshot if workspace_record is not None else {}
    )
    if planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
        progress_observer.verify_guarded_structured_enrichment(
            workspace_snapshot=workspace_snapshot,
        )
        while progress_observer.verify_guarded_chase_selection(
            workspace_snapshot=workspace_snapshot,
        ):
            pass
        if workspace_snapshot.get("guarded_terminal_control_action") is not None:
            progress_observer.verify_guarded_terminal_control_flow(
                workspace_snapshot=workspace_snapshot,
            )
        elif workspace_snapshot.get("guarded_stop_after_chase_round") == 1:
            progress_observer.verify_guarded_brief_generation(
                workspace_snapshot=workspace_snapshot,
            )
    source_execution_summary = _build_source_execution_summary(
        selected_sources=sources,
        workspace_snapshot=workspace_snapshot,
        research_init_result=research_init_result,
    )
    bootstrap_summary = json_object(workspace_snapshot.get("bootstrap_summary"))
    brief_metadata = _build_brief_metadata(
        workspace_snapshot=workspace_snapshot,
        research_init_result=research_init_result,
    )
    decisions = _build_decision_history(
        objective=objective,
        seed_terms=seed_terms,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        sources=sources,
        workspace_snapshot=workspace_snapshot,
        research_init_result=research_init_result,
        source_execution_summary=source_execution_summary,
        bootstrap_summary=bootstrap_summary,
        brief_metadata=brief_metadata,
    )
    shadow_planner_timeline = await progress_observer.finalize_shadow_planner(
        final_workspace_snapshot=workspace_snapshot,
        final_decisions=decisions,
    )
    shadow_planner_summary = _build_shadow_planner_summary(
        timeline=shadow_planner_timeline,
        mode=_planner_mode_value(planner_mode),
    )
    _put_shadow_planner_artifacts(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        timeline=shadow_planner_timeline,
        latest_summary=shadow_planner_summary,
        mode=_planner_mode_value(planner_mode),
    )
    _put_decision_history_artifact(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        decisions=decisions,
    )
    _store_action_output_artifacts(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        objective=objective,
        seed_terms=seed_terms,
        workspace_snapshot=workspace_snapshot,
        source_execution_summary=source_execution_summary,
        bootstrap_summary=bootstrap_summary,
        brief_metadata=brief_metadata,
    )
    _put_guarded_execution_artifact(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        planner_mode=planner_mode,
        actions=progress_observer.guarded_execution_log,
    )
    guarded_decision_proof_summary = None
    if planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
        _put_guarded_decision_proof_artifacts(
            artifact_store=execution_services.artifact_store,
            space_id=space_id,
            run_id=existing_run.id,
            planner_mode=planner_mode,
            guarded_rollout_profile=resolved_guarded_rollout_profile,
            guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            proofs=progress_observer.guarded_decision_proofs,
        )
        guarded_decision_proof_summary = _guarded_decision_proof_summary(
            planner_mode=planner_mode,
            guarded_rollout_profile=resolved_guarded_rollout_profile,
            guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            proofs=progress_observer.guarded_decision_proofs,
        )
    _put_guarded_readiness_artifact(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        planner_mode=planner_mode,
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
        actions=progress_observer.guarded_execution_log,
        proofs=progress_observer.guarded_decision_proofs,
    )
    workspace_summary = _build_workspace_summary(workspace_snapshot=workspace_snapshot)
    workspace_summary["shadow_planner_mode"] = _planner_mode_value(planner_mode)
    workspace_summary["planner_execution_mode"] = _planner_mode_value(planner_mode)
    workspace_summary["guarded_rollout_profile"] = resolved_guarded_rollout_profile
    workspace_summary["guarded_rollout_profile_source"] = (
        resolved_guarded_rollout_profile_source
    )
    workspace_summary["guarded_rollout_policy"] = _guarded_rollout_policy_summary(
        planner_mode=planner_mode,
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
    )
    workspace_summary["guarded_chase_rollout_enabled"] = guarded_chase_rollout_enabled
    workspace_summary["shadow_planner_timeline_key"] = (
        _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY
    )
    workspace_summary["shadow_planner_recommendation_key"] = (
        _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY
    )
    workspace_summary["shadow_planner_comparison_key"] = (
        _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY
    )
    workspace_summary["guarded_execution_log_key"] = _GUARDED_EXECUTION_ARTIFACT_KEY
    workspace_summary["guarded_readiness_key"] = _GUARDED_READINESS_ARTIFACT_KEY
    workspace_summary["guarded_execution"] = _guarded_execution_summary(
        planner_mode=planner_mode,
        actions=progress_observer.guarded_execution_log,
    )
    workspace_summary["guarded_readiness"] = _guarded_readiness_summary(
        planner_mode=planner_mode,
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
        actions=progress_observer.guarded_execution_log,
        proofs=progress_observer.guarded_decision_proofs,
    )
    if guarded_decision_proof_summary is not None:
        workspace_summary["guarded_decision_proofs_key"] = (
            _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
        )
        workspace_summary["guarded_decision_proofs"] = guarded_decision_proof_summary
    run_record = replace(
        research_init_result.run,
        status="completed",
    )
    result = FullAIOrchestratorExecutionResult(
        run=run_record,
        planner_mode=planner_mode,
        guarded_rollout_profile=(
            resolved_guarded_rollout_profile
            if planner_mode is FullAIOrchestratorPlannerMode.GUARDED
            else None
        ),
        guarded_rollout_profile_source=(
            resolved_guarded_rollout_profile_source
            if planner_mode is FullAIOrchestratorPlannerMode.GUARDED
            else None
        ),
        research_init_result=research_init_result,
        action_history=tuple(decisions),
        workspace_summary=workspace_summary,
        source_execution_summary=source_execution_summary,
        bootstrap_summary=bootstrap_summary,
        brief_metadata=brief_metadata,
        shadow_planner=shadow_planner_summary,
        guarded_execution=_guarded_execution_summary(
            planner_mode=planner_mode,
            actions=progress_observer.guarded_execution_log,
        ),
        guarded_decision_proofs=guarded_decision_proof_summary,
        errors=list(research_init_result.errors),
    )
    response_payload = build_full_ai_orchestrator_run_response(result).model_dump(
        mode="json",
    )
    result_keys = (
        _RESULT_ARTIFACT_KEY,
        "research_init_result",
        _DECISION_HISTORY_ARTIFACT_KEY,
        _ACTION_REGISTRY_ARTIFACT_KEY,
        _INITIALIZE_ARTIFACT_KEY,
        _PUBMED_ARTIFACT_KEY,
        _DRIVEN_TERMS_ARTIFACT_KEY,
        _SOURCE_EXECUTION_ARTIFACT_KEY,
        _BOOTSTRAP_ARTIFACT_KEY,
        _CHASE_ROUNDS_ARTIFACT_KEY,
        _BRIEF_METADATA_ARTIFACT_KEY,
        _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
        _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
        _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
        _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
        _GUARDED_EXECUTION_ARTIFACT_KEY,
        _GUARDED_READINESS_ARTIFACT_KEY,
        *(
            (_GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY,)
            if guarded_decision_proof_summary is not None
            else ()
        ),
    )
    workspace_patch = cast(
        "JSONObject",
        {
            "decision_history_key": _DECISION_HISTORY_ARTIFACT_KEY,
            "action_registry_key": _ACTION_REGISTRY_ARTIFACT_KEY,
            "decision_count": len(decisions),
            "last_decision_id": decisions[-1].decision_id,
            "workspace_summary": workspace_summary,
            "source_execution_summary": source_execution_summary,
            "brief_metadata": brief_metadata,
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
            "shadow_planner_comparison_key": (_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY),
            "shadow_planner_timeline_key": _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
            "shadow_planner": shadow_planner_summary,
            "guarded_execution_log_key": _GUARDED_EXECUTION_ARTIFACT_KEY,
            "guarded_readiness_key": _GUARDED_READINESS_ARTIFACT_KEY,
            "guarded_execution": _guarded_execution_summary(
                planner_mode=planner_mode,
                actions=progress_observer.guarded_execution_log,
            ),
            "guarded_readiness": _guarded_readiness_summary(
                planner_mode=planner_mode,
                guarded_rollout_profile=resolved_guarded_rollout_profile,
                guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
                actions=progress_observer.guarded_execution_log,
                proofs=progress_observer.guarded_decision_proofs,
            ),
            **(
                {
                    "guarded_decision_proofs_key": (
                        _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
                    ),
                    "guarded_decision_proofs": guarded_decision_proof_summary,
                }
                if guarded_decision_proof_summary is not None
                else {}
            ),
            "chase_round_summaries": _collect_chase_round_summaries(
                workspace_snapshot=workspace_snapshot,
            ),
            "full_ai_orchestrator_result": response_payload,
            "brief_result_key": "research_brief",
        },
    )
    store_primary_result_artifact(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=run_record.id,
        artifact_key=_RESULT_ARTIFACT_KEY,
        content=response_payload,
        status_value="completed",
        result_keys=result_keys,
        workspace_patch=workspace_patch,
    )
    completed_run = execution_services.run_registry.set_run_status(
        space_id=space_id,
        run_id=run_record.id,
        status="completed",
    )
    completed_run = run_record if completed_run is None else completed_run
    result = replace(result, run=completed_run)
    response_payload = build_full_ai_orchestrator_run_response(result).model_dump(
        mode="json",
    )
    workspace_patch["full_ai_orchestrator_result"] = response_payload
    store_primary_result_artifact(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=completed_run.id,
        artifact_key=_RESULT_ARTIFACT_KEY,
        content=response_payload,
        status_value="completed",
        result_keys=result_keys,
        workspace_patch=workspace_patch,
    )
    return result
