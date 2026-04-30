"""In-process side-by-side comparison for research-init and Phase 1 orchestrator."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Final, Literal
from uuid import UUID, uuid4

from artana_evidence_api.database import SessionLocal, set_session_rls_context
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_chat_session_store,
    get_document_binary_store,
    get_document_store,
    get_graph_api_gateway,
    get_graph_api_gateway_factory,
    get_graph_chat_runner,
    get_graph_connection_runner,
    get_graph_harness_kernel_runtime,
    get_graph_search_runner,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_proposal_store,
    get_pubmed_discovery_service_factory,
    get_research_onboarding_runner,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
)
from artana_evidence_api.full_ai_orchestrator.guarded.rollout import (
    _GUARDED_PROFILE_CHASE_ONLY,
    _GUARDED_PROFILE_DRY_RUN,
    _GUARDED_PROFILE_LOW_RISK,
    _GUARDED_PROFILE_SOURCE_CHASE,
    _guarded_profile_allows_chase,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    _FullAIOrchestratorProgressObserver,
    execute_full_ai_orchestrator_run,
    queue_full_ai_orchestrator_run,
)
from artana_evidence_api.phase1_compare_progress import (
    _await_compare_phase,
    _build_compare_orchestrator_progress_observer,
    _CompareProgressObserver,
    _CompositeProgressObserver,
    _emit_compare_progress,
    _progress_event_payload,
)
from artana_evidence_api.phase1_compare_summaries import (
    _GUARDED_CHASE_ROLLOUT_ENV,
    _GUARDED_ROLLOUT_PROFILE_ENV,
    _dict_value,
    _int_value,
    _normalize_pending_questions,
    _source_payload,
    _source_settings,
    _temporary_env_setting,
    _workspace_chase_candidates,
    _workspace_deterministic_chase_selection,
    build_compare_advisories,
    build_guarded_evaluation,
    build_phase1_source_preferences,
    compare_workspace_summaries,
    resolve_compare_environment,
    summarize_guarded_execution,
    summarize_workspace,
)
from artana_evidence_api.phase1_compare_telemetry import (
    _build_phase1_cost_comparison,
    _collect_baseline_telemetry_for_compare,
    _collect_run_ids_from_payload,
    _collect_shadow_planner_run_ids,
    _expand_run_lineage_from_events,
)
from artana_evidence_api.phase1_rollout_proof_helpers import (
    _available_structured_sources_from_workspace,
    _checkpoint_workspace_summary,
    _rollout_proof_summary,
)
from artana_evidence_api.research_init_runtime import (
    build_pubmed_replay_bundle_with_document_outputs,
    build_structured_enrichment_replay_bundle,
    execute_research_init_run,
    prepare_pubmed_replay_bundle,
    queue_research_init_run,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_object,
)

Phase1CompareMode = Literal["shared_baseline_replay", "dual_live_guarded"]

_COMPARE_OWNER_ID: Final[UUID] = UUID("00000000-0000-4000-a000-00000000c0de")
_COMPARE_OWNER_EMAIL: Final[str] = "phase1-compare@artana.org"
_SHARED_BASELINE_REPLAY_MODE: Final[Phase1CompareMode] = "shared_baseline_replay"
_DUAL_LIVE_GUARDED_MODE: Final[Phase1CompareMode] = "dual_live_guarded"


@dataclass(frozen=True, slots=True)
class Phase1CompareRequest:
    objective: str
    seed_terms: tuple[str, ...]
    title: str
    sources: ResearchSpaceSourcePreferences
    max_depth: int
    max_hypotheses: int
    planner_mode: FullAIOrchestratorPlannerMode = FullAIOrchestratorPlannerMode.SHADOW
    compare_mode: Phase1CompareMode = _SHARED_BASELINE_REPLAY_MODE
    compare_timeout_seconds: float | None = None


async def run_phase1_comparison(  # noqa: PLR0915
    request: Phase1CompareRequest,
) -> JSONObject:
    """Execute both flows in-process and return a compact comparison payload."""
    session = SessionLocal()
    set_session_rls_context(
        session,
        current_user_id=_COMPARE_OWNER_ID,
        is_admin=True,
        bypass_rls=True,
    )
    runtime = get_graph_harness_kernel_runtime()
    research_space_store = get_research_space_store(session)
    services = get_harness_execution_services(
        runtime=runtime,
        run_registry=get_run_registry(session, runtime),
        artifact_store=get_artifact_store(runtime),
        chat_session_store=get_chat_session_store(session),
        document_store=get_document_store(session),
        proposal_store=get_proposal_store(session),
        approval_store=get_approval_store(session),
        research_state_store=get_research_state_store(session),
        graph_snapshot_store=get_graph_snapshot_store(session),
        schedule_store=get_schedule_store(session),
        graph_connection_runner=get_graph_connection_runner(),
        graph_search_runner=get_graph_search_runner(),
        graph_chat_runner=get_graph_chat_runner(),
        research_onboarding_runner=get_research_onboarding_runner(),
        graph_api_gateway_factory=get_graph_api_gateway_factory(),
        pubmed_discovery_service_factory=get_pubmed_discovery_service_factory(),
        document_binary_store=get_document_binary_store(),
    )
    try:
        graph_api_gateway = get_graph_api_gateway()
        try:
            graph_health = graph_api_gateway.get_health()
        finally:
            graph_api_gateway.close()

        pubmed_replay_bundle = (
            await prepare_pubmed_replay_bundle(
                objective=request.objective,
                seed_terms=list(request.seed_terms),
            )
            if request.sources.get("pubmed", True)
            else None
        )
        if request.compare_mode == _DUAL_LIVE_GUARDED_MODE:
            baseline_space = research_space_store.create_space(
                owner_id=_COMPARE_OWNER_ID,
                owner_email=_COMPARE_OWNER_EMAIL,
                name=f"{request.title} baseline {uuid4().hex[:8]}",
                description="Phase 1 live guarded compare baseline space",
                settings=_source_settings(request.sources),
            )
            orchestrator_space = research_space_store.create_space(
                owner_id=_COMPARE_OWNER_ID,
                owner_email=_COMPARE_OWNER_EMAIL,
                name=f"{request.title} guarded {uuid4().hex[:8]}",
                description="Phase 1 live guarded compare orchestrator space",
                settings=_source_settings(request.sources),
            )
            baseline_run = queue_research_init_run(
                space_id=UUID(baseline_space.id),
                title=request.title,
                objective=request.objective,
                seed_terms=list(request.seed_terms),
                sources=request.sources,
                max_depth=request.max_depth,
                max_hypotheses=request.max_hypotheses,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                execution_services=services,
            )
            _emit_compare_progress(
                flow="baseline",
                phase="run_started",
                message="Starting deterministic baseline research-init execution.",
                progress_percent=0.0,
                completed_steps=0,
                metadata={
                    "space_id": baseline_space.id,
                    "run_id": baseline_run.id,
                    "mode": _DUAL_LIVE_GUARDED_MODE,
                },
            )
            baseline_result = await _await_compare_phase(
                awaitable=execute_research_init_run(
                    space_id=UUID(baseline_space.id),
                    title=request.title,
                    objective=request.objective,
                    seed_terms=list(request.seed_terms),
                    max_depth=request.max_depth,
                    max_hypotheses=request.max_hypotheses,
                    sources=request.sources,
                    execution_services=services,
                    existing_run=baseline_run,
                    progress_observer=_CompareProgressObserver(flow="baseline"),
                    pubmed_replay_bundle=pubmed_replay_bundle,
                ),
                timeout_seconds=request.compare_timeout_seconds,
                flow="baseline",
                phase="research_init_execution",
                message="Deterministic baseline research-init execution",
                metadata={
                    "space_id": baseline_space.id,
                    "run_id": baseline_run.id,
                    "mode": _DUAL_LIVE_GUARDED_MODE,
                },
            )
            _emit_compare_progress(
                flow="baseline",
                phase="run_completed",
                message="Deterministic baseline research-init execution completed.",
                progress_percent=1.0,
                completed_steps=999,
                metadata={
                    "space_id": baseline_space.id,
                    "run_id": baseline_run.id,
                    "status": baseline_result.run.status,
                    "mode": _DUAL_LIVE_GUARDED_MODE,
                },
            )
            baseline_workspace = services.artifact_store.get_workspace(
                space_id=baseline_space.id,
                run_id=baseline_run.id,
            )
            if pubmed_replay_bundle is not None:
                pubmed_replay_bundle = build_pubmed_replay_bundle_with_document_outputs(
                    replay_bundle=pubmed_replay_bundle,
                    space_id=UUID(baseline_space.id),
                    run_id=baseline_run.id,
                    document_store=services.document_store,
                    proposal_store=services.proposal_store,
                )
            structured_enrichment_replay_bundle = (
                build_structured_enrichment_replay_bundle(
                    space_id=UUID(baseline_space.id),
                    run_id=baseline_run.id,
                    document_store=services.document_store,
                    proposal_store=services.proposal_store,
                    workspace_snapshot=(
                        None
                        if baseline_workspace is None
                        else baseline_workspace.snapshot
                    ),
                )
            )
            orchestrator_run = queue_full_ai_orchestrator_run(
                space_id=UUID(orchestrator_space.id),
                title=request.title,
                objective=request.objective,
                seed_terms=list(request.seed_terms),
                sources=request.sources,
                max_depth=request.max_depth,
                max_hypotheses=request.max_hypotheses,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                execution_services=services,
                planner_mode=request.planner_mode,
            )
            _emit_compare_progress(
                flow="orchestrator",
                phase="run_started",
                message="Starting live guarded orchestrator execution.",
                progress_percent=0.0,
                completed_steps=0,
                metadata={
                    "space_id": orchestrator_space.id,
                    "run_id": orchestrator_run.id,
                    "mode": _DUAL_LIVE_GUARDED_MODE,
                    "planner_mode": request.planner_mode.value,
                },
            )
            orchestrator_result = await _await_compare_phase(
                awaitable=execute_full_ai_orchestrator_run(
                    space_id=UUID(orchestrator_space.id),
                    title=request.title,
                    objective=request.objective,
                    seed_terms=list(request.seed_terms),
                    max_depth=request.max_depth,
                    max_hypotheses=request.max_hypotheses,
                    sources=request.sources,
                    execution_services=services,
                    existing_run=orchestrator_run,
                    planner_mode=request.planner_mode,
                    pubmed_replay_bundle=pubmed_replay_bundle,
                    structured_enrichment_replay_bundle=(
                        structured_enrichment_replay_bundle
                    ),
                ),
                timeout_seconds=request.compare_timeout_seconds,
                flow="orchestrator",
                phase="full_ai_orchestrator_execution",
                message="Live guarded orchestrator execution",
                metadata={
                    "space_id": orchestrator_space.id,
                    "run_id": orchestrator_run.id,
                    "mode": _DUAL_LIVE_GUARDED_MODE,
                    "planner_mode": request.planner_mode.value,
                },
            )
            _emit_compare_progress(
                flow="orchestrator",
                phase="run_completed",
                message="Live guarded orchestrator execution completed.",
                progress_percent=1.0,
                completed_steps=999,
                metadata={
                    "space_id": orchestrator_space.id,
                    "run_id": orchestrator_run.id,
                    "status": orchestrator_result.run.status,
                    "decision_count": len(orchestrator_result.action_history),
                    "mode": _DUAL_LIVE_GUARDED_MODE,
                    "planner_mode": request.planner_mode.value,
                },
            )
            baseline_space_id = baseline_space.id
            orchestrator_space_id = orchestrator_space.id
        else:
            compare_space = research_space_store.create_space(
                owner_id=_COMPARE_OWNER_ID,
                owner_email=_COMPARE_OWNER_EMAIL,
                name=f"{request.title} compare {uuid4().hex[:8]}",
                description="Phase 1 shared compare space",
                settings=_source_settings(request.sources),
            )

            baseline_run = queue_research_init_run(
                space_id=UUID(compare_space.id),
                title=request.title,
                objective=request.objective,
                seed_terms=list(request.seed_terms),
                sources=request.sources,
                max_depth=request.max_depth,
                max_hypotheses=request.max_hypotheses,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                execution_services=services,
            )
            _emit_compare_progress(
                flow="baseline",
                phase="run_started",
                message="Starting baseline research-init execution.",
                progress_percent=0.0,
                completed_steps=0,
                metadata={
                    "space_id": compare_space.id,
                    "run_id": baseline_run.id,
                },
            )
            orchestrator_run = queue_full_ai_orchestrator_run(
                space_id=UUID(compare_space.id),
                title=request.title,
                objective=request.objective,
                seed_terms=list(request.seed_terms),
                sources=request.sources,
                max_depth=request.max_depth,
                max_hypotheses=request.max_hypotheses,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                execution_services=services,
                planner_mode=request.planner_mode,
            )
            services.run_registry.set_run_status(
                space_id=compare_space.id,
                run_id=orchestrator_run.id,
                status="compare_pending",
            )
            orchestrator_progress_observer = (
                _build_compare_orchestrator_progress_observer(
                    artifact_store=services.artifact_store,
                    space_id=UUID(compare_space.id),
                    run_id=orchestrator_run.id,
                    request=request,
                )
            )
            baseline_result = await _await_compare_phase(
                awaitable=execute_research_init_run(
                    space_id=UUID(compare_space.id),
                    title=request.title,
                    objective=request.objective,
                    seed_terms=list(request.seed_terms),
                    max_depth=request.max_depth,
                    max_hypotheses=request.max_hypotheses,
                    sources=request.sources,
                    execution_services=services,
                    existing_run=baseline_run,
                    progress_observer=_CompositeProgressObserver(
                        observers=(
                            _CompareProgressObserver(flow="baseline"),
                            orchestrator_progress_observer,
                        ),
                    ),
                    pubmed_replay_bundle=pubmed_replay_bundle,
                ),
                timeout_seconds=request.compare_timeout_seconds,
                flow="baseline",
                phase="research_init_execution",
                message="Baseline research-init execution",
                metadata={
                    "space_id": compare_space.id,
                    "run_id": baseline_run.id,
                    "mode": _SHARED_BASELINE_REPLAY_MODE,
                },
            )
            await _await_compare_phase(
                awaitable=orchestrator_progress_observer.wait_for_shadow_planner_updates(),
                timeout_seconds=request.compare_timeout_seconds,
                flow="orchestrator",
                phase="shadow_checkpoint_flush",
                message="Shared-baseline shadow checkpoint flush",
                metadata={
                    "space_id": compare_space.id,
                    "run_id": orchestrator_run.id,
                    "mode": _SHARED_BASELINE_REPLAY_MODE,
                    "planner_mode": request.planner_mode.value,
                },
            )
            _emit_compare_progress(
                flow="baseline",
                phase="run_completed",
                message="Baseline research-init execution completed.",
                progress_percent=1.0,
                completed_steps=999,
                metadata={
                    "space_id": compare_space.id,
                    "run_id": baseline_run.id,
                    "status": baseline_result.run.status,
                },
            )
            _emit_compare_progress(
                flow="orchestrator",
                phase="run_started",
                message="Finalizing Phase 1 orchestrator from the shared baseline execution.",
                progress_percent=0.0,
                completed_steps=0,
                metadata={
                    "space_id": compare_space.id,
                    "run_id": orchestrator_run.id,
                    "mode": _SHARED_BASELINE_REPLAY_MODE,
                    "planner_mode": request.planner_mode.value,
                },
            )
            baseline_workspace = services.artifact_store.get_workspace(
                space_id=compare_space.id,
                run_id=baseline_run.id,
            )
            orchestrator_result = await _await_compare_phase(
                awaitable=execute_full_ai_orchestrator_run(
                    space_id=UUID(compare_space.id),
                    title=request.title,
                    objective=request.objective,
                    seed_terms=list(request.seed_terms),
                    max_depth=request.max_depth,
                    max_hypotheses=request.max_hypotheses,
                    sources=request.sources,
                    execution_services=services,
                    existing_run=orchestrator_run,
                    planner_mode=request.planner_mode,
                    pubmed_replay_bundle=pubmed_replay_bundle,
                    replayed_research_init_result=baseline_result,
                    replayed_workspace_snapshot=(
                        None
                        if baseline_workspace is None
                        else baseline_workspace.snapshot
                    ),
                    replayed_phase_records=deepcopy(
                        orchestrator_progress_observer.phase_records
                    ),
                ),
                timeout_seconds=request.compare_timeout_seconds,
                flow="orchestrator",
                phase="full_ai_orchestrator_replay",
                message="Phase 1 orchestrator replay",
                metadata={
                    "space_id": compare_space.id,
                    "run_id": orchestrator_run.id,
                    "mode": _SHARED_BASELINE_REPLAY_MODE,
                    "planner_mode": request.planner_mode.value,
                },
            )
            _emit_compare_progress(
                flow="orchestrator",
                phase="run_completed",
                message="Phase 1 orchestrator replay completed.",
                progress_percent=1.0,
                completed_steps=999,
                metadata={
                    "space_id": compare_space.id,
                    "run_id": orchestrator_run.id,
                    "status": orchestrator_result.run.status,
                    "decision_count": len(orchestrator_result.action_history),
                    "mode": _SHARED_BASELINE_REPLAY_MODE,
                    "planner_mode": request.planner_mode.value,
                },
            )
            baseline_space_id = compare_space.id
            orchestrator_space_id = compare_space.id

        baseline_workspace = services.artifact_store.get_workspace(
            space_id=baseline_space_id,
            run_id=baseline_run.id,
        )
        orchestrator_workspace = services.artifact_store.get_workspace(
            space_id=orchestrator_space_id,
            run_id=orchestrator_run.id,
        )
        orchestrator_pubmed_artifact = services.artifact_store.get_artifact(
            space_id=orchestrator_space_id,
            run_id=orchestrator_run.id,
            artifact_key="full_ai_orchestrator_pubmed_summary",
        )
        orchestrator_decision_history = services.artifact_store.get_artifact(
            space_id=orchestrator_space_id,
            run_id=orchestrator_run.id,
            artifact_key="full_ai_orchestrator_decision_history",
        )
        orchestrator_shadow_timeline = services.artifact_store.get_artifact(
            space_id=orchestrator_space_id,
            run_id=orchestrator_run.id,
            artifact_key="full_ai_orchestrator_shadow_planner_timeline",
        )
        baseline_artifacts = services.artifact_store.list_artifacts(
            space_id=baseline_space_id,
            run_id=baseline_run.id,
        )
        baseline_artifact_contents = [
            artifact.content
            for artifact in baseline_artifacts
            if isinstance(artifact.content, dict)
        ]
        shadow_planner_summary = (
            orchestrator_result.shadow_planner
            if isinstance(orchestrator_result.shadow_planner, dict)
            else None
        )
        shadow_cost_tracking_value = (
            shadow_planner_summary.get("cost_tracking")
            if isinstance(shadow_planner_summary, dict)
            else None
        )
        shadow_cost_tracking = (
            dict(shadow_cost_tracking_value)
            if isinstance(shadow_cost_tracking_value, dict)
            else None
        )
        shadow_planner_run_ids = _collect_shadow_planner_run_ids(
            decision_history=(
                orchestrator_decision_history.content
                if orchestrator_decision_history is not None
                else None
            ),
            latest_shadow_planner_summary=shadow_planner_summary,
        )
        (
            baseline_telemetry_run_ids,
            baseline_telemetry,
        ) = await _collect_baseline_telemetry_for_compare(
            space_id=baseline_space_id,
            baseline_run_id=baseline_run.id,
            workspace_snapshot=(
                None if baseline_workspace is None else baseline_workspace.snapshot
            ),
            artifact_contents=baseline_artifact_contents,
        )

        baseline_summary = summarize_workspace(
            None if baseline_workspace is None else baseline_workspace.snapshot,
        )
        orchestrator_summary = summarize_workspace(
            None if orchestrator_workspace is None else orchestrator_workspace.snapshot,
        )
        mismatches = compare_workspace_summaries(
            baseline=baseline_summary,
            orchestrator=orchestrator_summary,
        )
        guarded_evaluation = build_guarded_evaluation(
            planner_mode=request.planner_mode,
            orchestrator_workspace=orchestrator_summary,
            shadow_planner_summary=shadow_planner_summary,
        )
        environment = resolve_compare_environment()
        environment["compare_mode"] = request.compare_mode
        environment["planner_mode"] = request.planner_mode.value
        if pubmed_replay_bundle is not None:
            environment["pubmed_replay_mode"] = "selected_candidates"
            environment["pubmed_replay_query_count"] = len(
                pubmed_replay_bundle.query_executions,
            )
            environment["pubmed_replay_selected_count"] = len(
                pubmed_replay_bundle.selected_candidates,
            )
        cost_comparison = _build_phase1_cost_comparison(
            baseline_telemetry=baseline_telemetry,
            shadow_cost_tracking=shadow_cost_tracking,
        )
        return {
            "request": {
                "objective": request.objective,
                "seed_terms": list(request.seed_terms),
                "title": request.title,
                "sources": _source_payload(request.sources),
                "max_depth": request.max_depth,
                "max_hypotheses": request.max_hypotheses,
                "planner_mode": request.planner_mode.value,
                "compare_mode": request.compare_mode,
            },
            "environment": environment,
            "baseline": {
                "space_id": baseline_space_id,
                "run_id": baseline_run.id,
                "status": baseline_result.run.status,
                "workspace": baseline_summary,
                "telemetry_run_ids": baseline_telemetry_run_ids,
                "telemetry": baseline_telemetry,
            },
            "orchestrator": {
                "space_id": orchestrator_space_id,
                "run_id": orchestrator_run.id,
                "status": orchestrator_result.run.status,
                "workspace": orchestrator_summary,
                "decision_count": len(orchestrator_result.action_history),
                "pubmed_artifact": (
                    orchestrator_pubmed_artifact.content
                    if orchestrator_pubmed_artifact is not None
                    else None
                ),
                "decision_history": (
                    orchestrator_decision_history.content
                    if orchestrator_decision_history is not None
                    else None
                ),
                "shadow_planner_timeline": (
                    orchestrator_shadow_timeline.content
                    if orchestrator_shadow_timeline is not None
                    else None
                ),
                "shadow_planner_run_ids": shadow_planner_run_ids,
                "shadow_planner": shadow_planner_summary,
            },
            "cost_comparison": cost_comparison,
            "guarded_evaluation": guarded_evaluation,
            "mismatches": mismatches,
            "advisories": build_compare_advisories(
                mismatches=mismatches,
                environment=environment,
                guarded_evaluation=guarded_evaluation,
            ),
        }
    finally:
        session.close()


async def _probe_guarded_structured_rollout_seam(
    *,
    observer: _FullAIOrchestratorProgressObserver,
    workspace_snapshot: JSONObject,
) -> list[JSONObject]:
    checkpoint_key = "after_driven_terms_ready"
    checkpoint_workspace_summary = _checkpoint_workspace_summary(
        shadow_timeline=observer.shadow_timeline,
        checkpoint_key=checkpoint_key,
    )
    available_source_keys = _available_structured_sources_from_workspace(
        workspace_snapshot,
    )
    if checkpoint_workspace_summary is None or len(available_source_keys) <= 1:
        return []
    selected_sources = await observer.maybe_select_structured_enrichment_sources(
        available_source_keys=available_source_keys,
        workspace_snapshot=workspace_snapshot,
    )
    persisted_workspace = observer.artifact_store.get_workspace(
        space_id=str(observer.space_id),
        run_id=observer.run_id,
    )
    persisted_snapshot = (
        persisted_workspace.snapshot if persisted_workspace is not None else {}
    )
    return [
        {
            "checkpoint_key": checkpoint_key,
            "available_source_keys": list(available_source_keys),
            "selection_returned": selected_sources is not None,
            "selected_source_order": (
                list(selected_sources) if selected_sources is not None else []
            ),
            "guarded_execution_count": len(observer.guarded_execution_log),
            "persisted_guarded_structured_enrichment_selection": (
                json_object(
                    persisted_snapshot.get("guarded_structured_enrichment_selection")
                )
            ),
        },
    ]


async def _probe_guarded_chase_rollout_seam(
    *,
    observer: _FullAIOrchestratorProgressObserver,
    workspace_snapshot: JSONObject,
) -> list[JSONObject]:
    seam_results: list[JSONObject] = []
    for checkpoint_key, round_number in (
        ("after_bootstrap", 1),
        ("after_chase_round_1", 2),
    ):
        checkpoint_workspace_summary = _checkpoint_workspace_summary(
            shadow_timeline=observer.shadow_timeline,
            checkpoint_key=checkpoint_key,
        )
        if checkpoint_workspace_summary is None:
            continue
        chase_candidates = _workspace_chase_candidates(checkpoint_workspace_summary)
        deterministic_selection = _workspace_deterministic_chase_selection(
            checkpoint_workspace_summary,
        )
        if not chase_candidates or deterministic_selection is None:
            continue
        selection = await observer.maybe_select_chase_round_selection(
            round_number=round_number,
            chase_candidates=chase_candidates,
            deterministic_selection=deterministic_selection,
            workspace_snapshot=workspace_snapshot,
        )
        persisted_workspace = observer.artifact_store.get_workspace(
            space_id=str(observer.space_id),
            run_id=observer.run_id,
        )
        persisted_snapshot = (
            persisted_workspace.snapshot if persisted_workspace is not None else {}
        )
        seam_results.append(
            {
                "checkpoint_key": checkpoint_key,
                "round_number": round_number,
                "candidate_count": len(chase_candidates),
                "deterministic_selected_labels": list(
                    deterministic_selection.selected_labels,
                ),
                "selection_returned": selection is not None,
                "selection_stop_instead": (
                    selection.stop_instead if selection is not None else False
                ),
                "selected_labels": (
                    list(selection.selected_labels) if selection is not None else []
                ),
                "selected_entity_ids": (
                    list(selection.selected_entity_ids) if selection is not None else []
                ),
                "selection_basis": (
                    selection.selection_basis if selection is not None else None
                ),
                "guarded_execution_count": len(observer.guarded_execution_log),
                "persisted_guarded_chase_round": (
                    json_object(
                        persisted_snapshot.get(
                            f"guarded_chase_round_{round_number}",
                            {},
                        ),
                    )
                    if isinstance(
                        persisted_snapshot.get(f"guarded_chase_round_{round_number}"),
                        dict,
                    )
                    else None
                ),
            },
        )
    return seam_results


async def run_guarded_chase_rollout_proof(
    request: Phase1CompareRequest,
) -> JSONObject:
    """Run one baseline and replay orchestrator with guarded chase off and on."""
    if request.planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
        raise ValueError(
            "Guarded chase rollout proof requires planner_mode=guarded.",
        )
    session = SessionLocal()
    set_session_rls_context(
        session,
        current_user_id=_COMPARE_OWNER_ID,
        is_admin=True,
        bypass_rls=True,
    )
    runtime = get_graph_harness_kernel_runtime()
    research_space_store = get_research_space_store(session)
    services = get_harness_execution_services(
        runtime=runtime,
        run_registry=get_run_registry(session, runtime),
        artifact_store=get_artifact_store(runtime),
        chat_session_store=get_chat_session_store(session),
        document_store=get_document_store(session),
        proposal_store=get_proposal_store(session),
        approval_store=get_approval_store(session),
        research_state_store=get_research_state_store(session),
        graph_snapshot_store=get_graph_snapshot_store(session),
        schedule_store=get_schedule_store(session),
        graph_connection_runner=get_graph_connection_runner(),
        graph_search_runner=get_graph_search_runner(),
        graph_chat_runner=get_graph_chat_runner(),
        research_onboarding_runner=get_research_onboarding_runner(),
        graph_api_gateway_factory=get_graph_api_gateway_factory(),
        pubmed_discovery_service_factory=get_pubmed_discovery_service_factory(),
        document_binary_store=get_document_binary_store(),
    )
    try:
        graph_api_gateway = get_graph_api_gateway()
        try:
            graph_health = graph_api_gateway.get_health()
        finally:
            graph_api_gateway.close()

        compare_space = research_space_store.create_space(
            owner_id=_COMPARE_OWNER_ID,
            owner_email=_COMPARE_OWNER_EMAIL,
            name=f"{request.title} rollout proof {uuid4().hex[:8]}",
            description="Guarded chase rollout proof space",
            settings=_source_settings(request.sources),
        )
        pubmed_replay_bundle = (
            await prepare_pubmed_replay_bundle(
                objective=request.objective,
                seed_terms=list(request.seed_terms),
            )
            if request.sources.get("pubmed", True)
            else None
        )
        baseline_run = queue_research_init_run(
            space_id=UUID(compare_space.id),
            title=request.title,
            objective=request.objective,
            seed_terms=list(request.seed_terms),
            sources=request.sources,
            max_depth=request.max_depth,
            max_hypotheses=request.max_hypotheses,
            graph_service_status=graph_health.status,
            graph_service_version=graph_health.version,
            run_registry=services.run_registry,
            artifact_store=services.artifact_store,
            execution_services=services,
        )
        with _temporary_env_setting(_GUARDED_CHASE_ROLLOUT_ENV, None):
            collector_run = queue_full_ai_orchestrator_run(
                space_id=UUID(compare_space.id),
                title=request.title,
                objective=request.objective,
                seed_terms=list(request.seed_terms),
                sources=request.sources,
                max_depth=request.max_depth,
                max_hypotheses=request.max_hypotheses,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                execution_services=services,
                planner_mode=request.planner_mode,
            )
        services.run_registry.set_run_status(
            space_id=compare_space.id,
            run_id=collector_run.id,
            status="compare_pending",
        )
        orchestrator_progress_observer = _build_compare_orchestrator_progress_observer(
            artifact_store=services.artifact_store,
            space_id=UUID(compare_space.id),
            run_id=collector_run.id,
            request=request,
        )
        await _await_compare_phase(
            awaitable=execute_research_init_run(
                space_id=UUID(compare_space.id),
                title=request.title,
                objective=request.objective,
                seed_terms=list(request.seed_terms),
                max_depth=request.max_depth,
                max_hypotheses=request.max_hypotheses,
                sources=request.sources,
                execution_services=services,
                existing_run=baseline_run,
                progress_observer=_CompositeProgressObserver(
                    observers=(
                        _CompareProgressObserver(flow="baseline"),
                        orchestrator_progress_observer,
                    ),
                ),
                pubmed_replay_bundle=pubmed_replay_bundle,
            ),
            timeout_seconds=request.compare_timeout_seconds,
            flow="baseline",
            phase="research_init_execution",
            message="Guarded rollout proof baseline execution",
            metadata={"space_id": compare_space.id, "run_id": baseline_run.id},
        )
        baseline_workspace = services.artifact_store.get_workspace(
            space_id=compare_space.id,
            run_id=baseline_run.id,
        )
        replayed_workspace_snapshot = (
            None if baseline_workspace is None else baseline_workspace.snapshot
        )
        baseline_shadow_timeline = (
            await orchestrator_progress_observer.finalize_shadow_planner(
                final_workspace_snapshot=(
                    {}
                    if replayed_workspace_snapshot is None
                    else replayed_workspace_snapshot
                ),
                final_decisions=[
                    decision.model_copy(deep=True)
                    for decision in orchestrator_progress_observer.decisions
                ],
            )
        )
        baseline_shadow_planner_summary: JSONObject = {
            "timeline": deepcopy(baseline_shadow_timeline),
        }

        rollout_reports: dict[str, JSONObject] = {}
        profile_specs = (
            ("dry_run", _GUARDED_PROFILE_DRY_RUN, None),
            ("chase_only", _GUARDED_PROFILE_CHASE_ONLY, None),
            ("source_chase", _GUARDED_PROFILE_SOURCE_CHASE, None),
            ("low_risk", _GUARDED_PROFILE_LOW_RISK, None),
        )
        for rollout_label, rollout_profile, rollout_value in profile_specs:
            with (
                _temporary_env_setting(_GUARDED_ROLLOUT_PROFILE_ENV, rollout_profile),
                _temporary_env_setting(_GUARDED_CHASE_ROLLOUT_ENV, rollout_value),
            ):
                orchestrator_run = queue_full_ai_orchestrator_run(
                    space_id=UUID(compare_space.id),
                    title=request.title,
                    objective=request.objective,
                    seed_terms=list(request.seed_terms),
                    sources=request.sources,
                    max_depth=request.max_depth,
                    max_hypotheses=request.max_hypotheses,
                    graph_service_status=graph_health.status,
                    graph_service_version=graph_health.version,
                    run_registry=services.run_registry,
                    artifact_store=services.artifact_store,
                    execution_services=services,
                    planner_mode=request.planner_mode,
                )
                orchestrator_progress_observer = (
                    _build_compare_orchestrator_progress_observer(
                        artifact_store=services.artifact_store,
                        space_id=UUID(compare_space.id),
                        run_id=orchestrator_run.id,
                        request=request,
                    )
                )
                orchestrator_progress_observer.shadow_timeline = deepcopy(
                    baseline_shadow_timeline,
                )
                orchestrator_progress_observer.emitted_shadow_checkpoints = {
                    str(entry.get("checkpoint_key"))
                    for entry in orchestrator_progress_observer.shadow_timeline
                    if isinstance(entry.get("checkpoint_key"), str)
                }
                structured_seam_results = await _await_compare_phase(
                    awaitable=_probe_guarded_structured_rollout_seam(
                        observer=orchestrator_progress_observer,
                        workspace_snapshot=(
                            {}
                            if replayed_workspace_snapshot is None
                            else replayed_workspace_snapshot
                        ),
                    ),
                    timeout_seconds=request.compare_timeout_seconds,
                    flow=f"orchestrator_{rollout_label}",
                    phase="guarded_structured_rollout_seam",
                    message=f"Guarded structured rollout seam probe ({rollout_label})",
                    metadata={
                        "space_id": compare_space.id,
                        "run_id": orchestrator_run.id,
                        "guarded_rollout_profile": rollout_profile,
                    },
                )
                seam_results = await _await_compare_phase(
                    awaitable=_probe_guarded_chase_rollout_seam(
                        observer=orchestrator_progress_observer,
                        workspace_snapshot=(
                            {}
                            if replayed_workspace_snapshot is None
                            else replayed_workspace_snapshot
                        ),
                    ),
                    timeout_seconds=request.compare_timeout_seconds,
                    flow=f"orchestrator_{rollout_label}",
                    phase="guarded_chase_rollout_seam",
                    message=f"Guarded rollout seam probe ({rollout_label})",
                    metadata={
                        "space_id": compare_space.id,
                        "run_id": orchestrator_run.id,
                        "guarded_rollout_profile": rollout_profile,
                    },
                )
                orchestrator_workspace = services.artifact_store.get_workspace(
                    space_id=compare_space.id,
                    run_id=orchestrator_run.id,
                )
                rollout_reports[rollout_label] = _rollout_proof_summary(
                    rollout_enabled=_guarded_profile_allows_chase(
                        guarded_rollout_profile=rollout_profile,
                    ),
                    rollout_profile=rollout_profile,
                    run_id=orchestrator_run.id,
                    space_id=str(compare_space.id),
                    workspace_snapshot=(
                        None
                        if orchestrator_workspace is None
                        else orchestrator_workspace.snapshot
                    ),
                    shadow_planner_summary=baseline_shadow_planner_summary,
                    seam_results=seam_results,
                    structured_seam_results=structured_seam_results,
                )

        off_report = rollout_reports["dry_run"]
        on_report = rollout_reports["chase_only"]
        source_chase_report = rollout_reports["source_chase"]
        low_risk_report = rollout_reports["low_risk"]
        boundary_observed = (
            _int_value(off_report.get("selection_returned_count")) == 0
            and _int_value(on_report.get("selection_returned_count")) > 0
        )
        profile_comparison: dict[str, int | bool] = {
            "dry_run_applied_count": _int_value(
                _dict_value(off_report.get("guarded_evaluation")).get(
                    "applied_count",
                ),
            ),
            "chase_only_structured_selection_returned_count": _int_value(
                on_report.get("structured_selection_returned_count"),
            ),
            "low_risk_structured_selection_returned_count": _int_value(
                low_risk_report.get("structured_selection_returned_count"),
            ),
            "source_chase_structured_selection_returned_count": _int_value(
                source_chase_report.get("structured_selection_returned_count"),
            ),
            "source_chase_chase_selection_returned_count": _int_value(
                source_chase_report.get("selection_returned_count"),
            ),
            "low_risk_chase_selection_returned_count": _int_value(
                low_risk_report.get("selection_returned_count"),
            ),
        }
        profile_comparison["profile_boundaries_observed"] = (
            profile_comparison["dry_run_applied_count"] == 0
            and profile_comparison["chase_only_structured_selection_returned_count"]
            == 0
            and (
                profile_comparison["source_chase_structured_selection_returned_count"]
                > 0
                or profile_comparison["source_chase_chase_selection_returned_count"] > 0
                or profile_comparison["low_risk_structured_selection_returned_count"]
                > 0
                or profile_comparison["low_risk_chase_selection_returned_count"] > 0
            )
        )
        return {
            "request": {
                "objective": request.objective,
                "seed_terms": list(request.seed_terms),
                "title": request.title,
                "sources": _source_payload(request.sources),
                "max_depth": request.max_depth,
                "max_hypotheses": request.max_hypotheses,
                "planner_mode": request.planner_mode.value,
            },
            "baseline": {
                "space_id": compare_space.id,
                "run_id": baseline_run.id,
                "workspace": summarize_workspace(replayed_workspace_snapshot),
            },
            "rollout_off": off_report,
            "rollout_on": on_report,
            "profile_reports": rollout_reports,
            "comparison": {
                "boundary_observed": boundary_observed,
                "off_selection_returned_count": _int_value(
                    off_report.get("selection_returned_count"),
                ),
                "on_selection_returned_count": _int_value(
                    on_report.get("selection_returned_count"),
                ),
                **profile_comparison,
            },
        }
    finally:
        session.close()


def run_guarded_chase_rollout_proof_sync(
    request: Phase1CompareRequest,
) -> JSONObject:
    """Synchronous wrapper for rollout-proof CLI usage."""
    return asyncio.run(run_guarded_chase_rollout_proof(request))


def run_phase1_comparison_sync(
    request: Phase1CompareRequest,
) -> JSONObject:
    """Synchronous wrapper for the CLI."""
    return asyncio.run(run_phase1_comparison(request))


def format_phase1_comparison_json(payload: JSONObject) -> str:
    """Return pretty JSON for CLI output."""
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


__all__ = [
    "Phase1CompareRequest",
    "build_guarded_evaluation",
    "build_phase1_source_preferences",
    "compare_workspace_summaries",
    "format_phase1_comparison_json",
    "run_guarded_chase_rollout_proof",
    "run_guarded_chase_rollout_proof_sync",
    "run_phase1_comparison",
    "run_phase1_comparison_sync",
    "summarize_workspace",
    "summarize_guarded_execution",
    "_await_compare_phase",
    "_build_compare_orchestrator_progress_observer",
    "_build_phase1_cost_comparison",
    "_CompareProgressObserver",
    "_collect_run_ids_from_payload",
    "_expand_run_lineage_from_events",
    "_normalize_pending_questions",
    "_progress_event_payload",
]
