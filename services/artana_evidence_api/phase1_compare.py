"""In-process side-by-side comparison for research-init and Phase 1 orchestrator."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import deque
from collections.abc import Awaitable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, TypeVar
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
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    _GUARDED_PROFILE_CHASE_ONLY,
    _GUARDED_PROFILE_DRY_RUN,
    _GUARDED_PROFILE_LOW_RISK,
    _GUARDED_PROFILE_SOURCE_CHASE,
    _STRUCTURED_ENRICHMENT_SOURCES,
    _accepted_guarded_chase_selection_action,
    _accepted_guarded_control_flow_action,
    _accepted_guarded_generate_brief_action,
    _accepted_guarded_structured_source_action,
    _build_initial_decision_history,
    _FullAIOrchestratorProgressObserver,
    _guarded_profile_allows_chase,
    _guarded_rollout_profile,
    execute_full_ai_orchestrator_run,
    orchestrator_action_registry,
    queue_full_ai_orchestrator_run,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    build_shadow_planner_workspace_summary,
)
from artana_evidence_api.research_init_runtime import (
    ResearchInitProgressObserver,
    build_pubmed_replay_bundle_with_document_outputs,
    build_structured_enrichment_replay_bundle,
    execute_research_init_run,
    prepare_pubmed_replay_bundle,
    queue_research_init_run,
)
from artana_evidence_api.research_init_source_results import build_source_results
from artana_evidence_api.runtime_support import create_artana_postgres_store
from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences
from pydantic import ValidationError

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore

Phase1CompareMode = Literal["shared_baseline_replay", "dual_live_guarded"]
_T = TypeVar("_T")

_COMPARE_OWNER_ID: Final[UUID] = UUID("00000000-0000-4000-a000-00000000c0de")
_COMPARE_OWNER_EMAIL: Final[str] = "phase1-compare@artana.org"
_SHARED_BASELINE_REPLAY_MODE: Final[Phase1CompareMode] = "shared_baseline_replay"
_DUAL_LIVE_GUARDED_MODE: Final[Phase1CompareMode] = "dual_live_guarded"
_ALL_SOURCE_KEYS: Final[tuple[str, ...]] = (
    "pubmed",
    "marrvel",
    "clinvar",
    "mondo",
    "pdf",
    "text",
    "drugbank",
    "alphafold",
    "uniprot",
    "hgnc",
    "clinical_trials",
    "mgi",
    "zfin",
)
_UUID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_PUBMED_BACKEND_ENV: Final[str] = "ARTANA_PUBMED_SEARCH_BACKEND"
_GUARDED_CHASE_ROLLOUT_ENV: Final[str] = "ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT"
_GUARDED_ROLLOUT_PROFILE_ENV: Final[str] = "ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE"


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


def _build_compare_orchestrator_progress_observer(
    *,
    space_id: UUID,
    run_id: str,
    request: Phase1CompareRequest,
    artifact_store: HarnessArtifactStore,
) -> _FullAIOrchestratorProgressObserver:
    initial_decisions = _build_initial_decision_history(
        objective=request.objective,
        seed_terms=list(request.seed_terms),
        max_depth=request.max_depth,
        max_hypotheses=request.max_hypotheses,
        sources=request.sources,
    )
    action_registry = orchestrator_action_registry()
    guarded_rollout_profile = _guarded_rollout_profile(
        planner_mode=request.planner_mode,
    )
    initial_workspace_summary = build_shadow_planner_workspace_summary(
        checkpoint_key="before_first_action",
        mode=request.planner_mode.value,
        objective=request.objective,
        seed_terms=list(request.seed_terms),
        sources=request.sources,
        max_depth=request.max_depth,
        max_hypotheses=request.max_hypotheses,
        workspace_snapshot={
            "source_results": build_source_results(sources=request.sources),
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
    return _FullAIOrchestratorProgressObserver(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run_id,
        objective=request.objective,
        seed_terms=list(request.seed_terms),
        max_depth=request.max_depth,
        max_hypotheses=request.max_hypotheses,
        sources=request.sources,
        planner_mode=request.planner_mode,
        action_registry=action_registry,
        decisions=initial_decisions,
        initial_workspace_summary=initial_workspace_summary,
        phase_records={},
        guarded_rollout_profile=guarded_rollout_profile,
        guarded_chase_rollout_enabled=_guarded_profile_allows_chase(
            guarded_rollout_profile=guarded_rollout_profile,
        ),
    )


def _progress_event_payload(
    *,
    flow: str,
    phase: str,
    message: str,
    progress_percent: float,
    completed_steps: int,
    metadata: JSONObject | None = None,
) -> JSONObject:
    return {
        "flow": flow,
        "phase": phase,
        "message": message,
        "progress_percent": progress_percent,
        "completed_steps": completed_steps,
        "metadata": dict(metadata or {}),
    }


def _emit_compare_progress(
    *,
    flow: str,
    phase: str,
    message: str,
    progress_percent: float,
    completed_steps: int,
    metadata: JSONObject | None = None,
) -> None:
    payload = _progress_event_payload(
        flow=flow,
        phase=phase,
        message=message,
        progress_percent=progress_percent,
        completed_steps=completed_steps,
        metadata=metadata,
    )
    sys.stderr.write(json.dumps(payload, sort_keys=True) + "\n")
    sys.stderr.flush()


async def _await_compare_phase(
    *,
    awaitable: Awaitable[_T],
    timeout_seconds: float | None,
    flow: str,
    phase: str,
    message: str,
    metadata: JSONObject | None = None,
) -> _T:
    if timeout_seconds is None or timeout_seconds <= 0:
        return await awaitable
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except TimeoutError as exc:
        timeout_metadata: JSONObject = dict(metadata or {})
        timeout_metadata["timeout_seconds"] = timeout_seconds
        _emit_compare_progress(
            flow=flow,
            phase=f"{phase}_timeout",
            message=f"{message} timed out after {timeout_seconds:.1f}s.",
            progress_percent=1.0,
            completed_steps=999,
            metadata=timeout_metadata,
        )
        raise TimeoutError(
            f"{flow} phase '{phase}' timed out after {timeout_seconds:.1f}s",
        ) from exc


@dataclass(slots=True)
class _CompareProgressObserver(ResearchInitProgressObserver):
    flow: str
    last_signature: tuple[str, str, int] | None = None

    def on_progress(
        self,
        *,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int,
        metadata: JSONObject,
        workspace_snapshot: JSONObject,
    ) -> None:
        del workspace_snapshot
        signature = (phase, message, completed_steps)
        if signature == self.last_signature:
            return
        self.last_signature = signature
        _emit_compare_progress(
            flow=self.flow,
            phase=phase,
            message=message,
            progress_percent=progress_percent,
            completed_steps=completed_steps,
            metadata=metadata,
        )


@dataclass(slots=True)
class _CompositeProgressObserver(ResearchInitProgressObserver):
    observers: tuple[ResearchInitProgressObserver, ...]

    def on_progress(
        self,
        *,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int,
        metadata: JSONObject,
        workspace_snapshot: JSONObject,
    ) -> None:
        for observer in self.observers:
            observer.on_progress(
                phase=phase,
                message=message,
                progress_percent=progress_percent,
                completed_steps=completed_steps,
                metadata=metadata,
                workspace_snapshot=workspace_snapshot,
            )


def build_phase1_source_preferences(
    enabled_sources: list[str] | tuple[str, ...],
) -> ResearchSpaceSourcePreferences:
    """Return a normalized source preference map for the compare run."""
    selected = {source.strip() for source in enabled_sources if source.strip() != ""}
    unknown = sorted(source for source in selected if source not in _ALL_SOURCE_KEYS)
    if unknown:
        msg = f"Unknown source keys: {', '.join(unknown)}"
        raise ValueError(msg)
    return {source: source in selected for source in _ALL_SOURCE_KEYS}


def _normalize_seed_terms(seed_terms: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for term in seed_terms:
        trimmed = term.strip()
        if trimmed == "":
            continue
        normalized.append(trimmed)
    if not normalized:
        msg = "At least one non-empty seed term is required"
        raise ValueError(msg)
    return tuple(normalized)


def _workspace_source_summary(snapshot: JSONObject) -> JSONObject:
    source_results = snapshot.get("source_results")
    if not isinstance(source_results, dict):
        return {}
    return {
        key: value
        for key, value in source_results.items()
        if isinstance(key, str) and isinstance(value, dict)
    }


def _workspace_chase_context_summary(value: object) -> JSONObject | None:
    if not isinstance(value, dict):
        return None
    filtered_chase_candidates = (
        [
            item
            for item in value.get("filtered_chase_candidates", [])
            if isinstance(item, dict)
        ]
        if isinstance(value.get("filtered_chase_candidates"), list)
        else []
    )
    filtered_labels = [
        item["display_label"]
        for item in filtered_chase_candidates
        if isinstance(item.get("display_label"), str)
    ]
    filtered_reason_counts = (
        {
            key: count
            for key, count in value.get(
                "filtered_chase_filter_reason_counts",
                {},
            ).items()
            if isinstance(key, str) and isinstance(count, int)
        }
        if isinstance(value.get("filtered_chase_filter_reason_counts"), dict)
        else {}
    )
    return {
        "round_number": value.get("round_number"),
        "candidate_count": value.get("candidate_count"),
        "deterministic_candidate_count": value.get("deterministic_candidate_count"),
        "deterministic_threshold_met": value.get("deterministic_threshold_met"),
        "selection_mode": value.get("selection_mode"),
        "selected_labels": (
            [item for item in value.get("selected_labels", []) if isinstance(item, str)]
            if isinstance(value.get("selected_labels"), list)
            else []
        ),
        "filtered_chase_candidate_count": value.get("filtered_chase_candidate_count"),
        "filtered_chase_filter_reason_counts": filtered_reason_counts,
        "filtered_chase_labels": filtered_labels,
    }


def _workspace_guarded_decision_proofs_summary(value: object) -> JSONObject | None:
    if not isinstance(value, dict):
        return None
    proofs = value.get("proofs")
    proof_summaries = (
        [
            {
                "proof_id": proof.get("proof_id"),
                "checkpoint_key": proof.get("checkpoint_key"),
                "guarded_strategy": proof.get("guarded_strategy"),
                "guarded_rollout_profile": proof.get("guarded_rollout_profile"),
                "guarded_rollout_profile_source": proof.get(
                    "guarded_rollout_profile_source",
                ),
                "decision_outcome": proof.get("decision_outcome"),
                "outcome_reason": proof.get("outcome_reason"),
                "recommended_action_type": proof.get("recommended_action_type"),
                "applied_action_type": proof.get("applied_action_type"),
                "policy_allowed": proof.get("policy_allowed"),
                "verification_status": proof.get("verification_status"),
                "used_fallback": proof.get("used_fallback"),
                "fallback_reason": proof.get("fallback_reason"),
                "validation_error": proof.get("validation_error"),
                "qualitative_rationale_present": proof.get(
                    "qualitative_rationale_present",
                ),
                "budget_violation": proof.get("budget_violation"),
                "disabled_source_violation": proof.get(
                    "disabled_source_violation",
                ),
                "planner_status": proof.get("planner_status"),
                "model_id": proof.get("model_id"),
                "prompt_version": proof.get("prompt_version"),
                "agent_run_id": proof.get("agent_run_id"),
            }
            for proof in proofs
            if isinstance(proof, dict)
        ]
        if isinstance(proofs, list)
        else []
    )
    artifact_keys = (
        [key for key in value.get("artifact_keys", []) if isinstance(key, str)]
        if isinstance(value.get("artifact_keys"), list)
        else []
    )
    return {
        "mode": value.get("mode"),
        "policy_version": value.get("policy_version"),
        "guarded_rollout_profile": value.get("guarded_rollout_profile"),
        "guarded_rollout_profile_source": value.get(
            "guarded_rollout_profile_source",
        ),
        "proof_count": value.get("proof_count"),
        "allowed_count": value.get("allowed_count"),
        "blocked_count": value.get("blocked_count"),
        "ignored_count": value.get("ignored_count"),
        "verified_count": value.get("verified_count"),
        "verification_failed_count": value.get("verification_failed_count"),
        "pending_verification_count": value.get("pending_verification_count"),
        "artifact_keys": artifact_keys,
        "proofs": proof_summaries,
    }


def summarize_workspace(snapshot: JSONObject | None) -> JSONObject:
    """Extract the high-signal fields we compare between both flows."""
    if snapshot is None:
        return {"present": False}
    source_results = _workspace_source_summary(snapshot)
    return {
        "present": True,
        "status": snapshot.get("status"),
        "documents_ingested": snapshot.get("documents_ingested"),
        "proposal_count": snapshot.get("proposal_count"),
        "pending_questions": snapshot.get("pending_questions"),
        "errors": snapshot.get("errors"),
        "pubmed_results": snapshot.get("pubmed_results"),
        "driven_terms": snapshot.get("driven_terms"),
        "bootstrap_run_id": snapshot.get("bootstrap_run_id"),
        "bootstrap_summary": snapshot.get("bootstrap_summary"),
        "brief_present": isinstance(snapshot.get("research_brief"), dict),
        "planner_execution_mode": snapshot.get("planner_execution_mode"),
        "guarded_rollout_profile": snapshot.get("guarded_rollout_profile"),
        "guarded_rollout_policy": (
            dict(snapshot.get("guarded_rollout_policy"))
            if isinstance(snapshot.get("guarded_rollout_policy"), dict)
            else None
        ),
        "guarded_readiness": (
            dict(snapshot.get("guarded_readiness"))
            if isinstance(snapshot.get("guarded_readiness"), dict)
            else None
        ),
        "guarded_execution": (
            dict(snapshot.get("guarded_execution"))
            if isinstance(snapshot.get("guarded_execution"), dict)
            else None
        ),
        "guarded_decision_proofs_key": snapshot.get("guarded_decision_proofs_key"),
        "guarded_decision_proofs": _workspace_guarded_decision_proofs_summary(
            snapshot.get("guarded_decision_proofs"),
        ),
        "pending_chase_round": _workspace_chase_context_summary(
            snapshot.get("pending_chase_round"),
        ),
        "chase_round_1": _workspace_chase_context_summary(
            snapshot.get("chase_round_1"),
        ),
        "chase_round_2": _workspace_chase_context_summary(
            snapshot.get("chase_round_2"),
        ),
        "source_results": source_results,
    }


def summarize_guarded_execution(guarded_execution: object) -> JSONObject:
    """Return a compact evaluation summary for guarded pilot actions."""
    if not isinstance(guarded_execution, dict):
        return {
            "present": False,
            "mode": None,
            "applied_count": 0,
            "verified_count": 0,
            "verification_failed_count": 0,
            "pending_verification_count": 0,
            "all_verified": False,
            "actions": [],
            "failed_actions": [],
        }

    actions = (
        [
            action
            for action in guarded_execution.get("actions", [])
            if isinstance(action, dict)
        ]
        if isinstance(guarded_execution.get("actions"), list)
        else []
    )
    failed_actions: list[JSONObject] = []
    chase_action_count = 0
    chase_verified_count = 0
    chase_exact_selection_match_count = 0
    chase_selected_entity_overlap_total = 0
    chase_selection_mismatch_count = 0
    terminal_control_action_count = 0
    terminal_control_verified_count = 0
    chase_checkpoint_stop_count = 0
    chase_checkpoint_escalate_count = 0
    action_summaries: list[JSONObject] = []
    for action in actions:
        action_summary = _guarded_execution_action_summary(action)
        action_summaries.append(action_summary)
        if action_summary.get("guarded_strategy") == "terminal_control_flow":
            terminal_control_action_count += 1
            if action_summary.get("verification_status") == "verified":
                terminal_control_verified_count += 1
            if action_summary.get("checkpoint_key") in {
                "after_bootstrap",
                "after_chase_round_1",
            }:
                if action_summary.get("action_type") == "STOP":
                    chase_checkpoint_stop_count += 1
                elif action_summary.get("action_type") == "ESCALATE_TO_HUMAN":
                    chase_checkpoint_escalate_count += 1
        if action_summary.get("guarded_strategy") == "chase_selection":
            chase_action_count += 1
            if action_summary.get("verification_status") == "verified":
                chase_verified_count += 1
            if bool(action_summary.get("exact_selection_match")):
                chase_exact_selection_match_count += 1
            chase_selected_entity_overlap_total += _guarded_chase_overlap_count(
                action_summary,
            )
            if not bool(action_summary.get("exact_selection_match")):
                chase_selection_mismatch_count += 1
        if action.get("verification_status") != "verification_failed":
            continue
        failed_actions.append(
            {
                "checkpoint_key": action.get("checkpoint_key"),
                "action_type": action.get("applied_action_type"),
                "source_key": action.get("applied_source_key"),
                "verification_reason": action.get("verification_reason"),
            },
        )
    applied_count = (
        guarded_execution.get("applied_count")
        if isinstance(guarded_execution.get("applied_count"), int)
        else len(actions)
    )
    verified_count = (
        guarded_execution.get("verified_count")
        if isinstance(guarded_execution.get("verified_count"), int)
        else 0
    )
    verification_failed_count = (
        guarded_execution.get("verification_failed_count")
        if isinstance(guarded_execution.get("verification_failed_count"), int)
        else len(failed_actions)
    )
    pending_verification_count = (
        guarded_execution.get("pending_verification_count")
        if isinstance(guarded_execution.get("pending_verification_count"), int)
        else 0
    )
    return {
        "present": True,
        "mode": guarded_execution.get("mode"),
        "applied_count": applied_count,
        "verified_count": verified_count,
        "verification_failed_count": verification_failed_count,
        "pending_verification_count": pending_verification_count,
        "all_verified": (
            verification_failed_count == 0 and pending_verification_count == 0
        ),
        "chase_action_count": chase_action_count,
        "chase_verified_count": chase_verified_count,
        "chase_exact_selection_match_count": chase_exact_selection_match_count,
        "chase_selected_entity_overlap_total": chase_selected_entity_overlap_total,
        "chase_selection_mismatch_count": chase_selection_mismatch_count,
        "terminal_control_action_count": terminal_control_action_count,
        "terminal_control_verified_count": terminal_control_verified_count,
        "chase_checkpoint_stop_count": chase_checkpoint_stop_count,
        "chase_checkpoint_escalate_count": chase_checkpoint_escalate_count,
        "actions": action_summaries,
        "failed_actions": failed_actions,
    }


def build_guarded_evaluation(
    *,
    planner_mode: FullAIOrchestratorPlannerMode,
    orchestrator_workspace: JSONObject,
    shadow_planner_summary: object | None = None,
) -> JSONObject:
    """Summarize whether guarded actions verified cleanly for one compare run."""
    if planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
        return {
            "mode": planner_mode.value,
            "status": "not_applicable",
            "applied_count": 0,
            "candidate_count": 0,
            "identified_count": 0,
            "verified_count": 0,
            "verification_failed_count": 0,
            "pending_verification_count": 0,
            "all_verified": None,
            "failed_actions": [],
            "applied_actions": [],
            "candidate_actions": [],
            "notes": "Guarded evaluation is only active when planner_mode=guarded.",
        }

    guarded_summary = summarize_guarded_execution(
        orchestrator_workspace.get("guarded_execution"),
    )
    verification_failed_count = (
        guarded_summary.get("verification_failed_count")
        if isinstance(guarded_summary.get("verification_failed_count"), int)
        else 0
    )
    pending_verification_count = (
        guarded_summary.get("pending_verification_count")
        if isinstance(guarded_summary.get("pending_verification_count"), int)
        else 0
    )
    applied_count = (
        guarded_summary.get("applied_count")
        if isinstance(guarded_summary.get("applied_count"), int)
        else 0
    )
    verified_count = (
        guarded_summary.get("verified_count")
        if isinstance(guarded_summary.get("verified_count"), int)
        else 0
    )
    candidate_summary = summarize_guarded_candidates(
        orchestrator_workspace=orchestrator_workspace,
        shadow_planner_summary=shadow_planner_summary,
    )
    candidate_count = (
        candidate_summary.get("candidate_count")
        if isinstance(candidate_summary.get("candidate_count"), int)
        else 0
    )
    status = "clean"
    if verification_failed_count > 0:
        status = "verification_failed"
    elif pending_verification_count > 0:
        status = "verification_pending"
    elif applied_count == 0:
        status = (
            "candidate_detected_replay_only"
            if candidate_count > 0
            else "no_guarded_actions_applied"
        )
    identified_count = applied_count if applied_count > 0 else candidate_count
    return {
        "mode": planner_mode.value,
        "status": status,
        "applied_count": applied_count,
        "candidate_count": candidate_count,
        "identified_count": identified_count,
        "verified_count": verified_count,
        "verification_failed_count": verification_failed_count,
        "pending_verification_count": pending_verification_count,
        "chase_action_count": guarded_summary.get("chase_action_count"),
        "chase_verified_count": guarded_summary.get("chase_verified_count"),
        "chase_exact_selection_match_count": guarded_summary.get(
            "chase_exact_selection_match_count",
        ),
        "chase_selected_entity_overlap_total": guarded_summary.get(
            "chase_selected_entity_overlap_total",
        ),
        "chase_selection_mismatch_count": guarded_summary.get(
            "chase_selection_mismatch_count",
        ),
        "terminal_control_action_count": guarded_summary.get(
            "terminal_control_action_count",
        ),
        "terminal_control_verified_count": guarded_summary.get(
            "terminal_control_verified_count",
        ),
        "chase_checkpoint_stop_count": guarded_summary.get(
            "chase_checkpoint_stop_count",
        ),
        "chase_checkpoint_escalate_count": guarded_summary.get(
            "chase_checkpoint_escalate_count",
        ),
        "chase_candidate_count": candidate_summary.get("chase_candidate_count"),
        "chase_candidate_exact_selection_match_count": candidate_summary.get(
            "chase_candidate_exact_selection_match_count",
        ),
        "chase_candidate_overlap_total": candidate_summary.get(
            "chase_candidate_overlap_total",
        ),
        "all_verified": (
            guarded_summary.get("all_verified") if applied_count > 0 else None
        ),
        "failed_actions": guarded_summary.get("failed_actions"),
        "applied_actions": guarded_summary.get("actions"),
        "candidate_actions": candidate_summary.get("candidate_actions"),
        "notes": (
            "Guarded pilot is healthy."
            if status == "clean"
            else (
                "Shared baseline replay found a valid guarded intervention, but this compare mode cannot execute the branch change live."
                if status == "candidate_detected_replay_only"
                else (
                    "No guarded action was accepted during this compare run."
                    if status == "no_guarded_actions_applied"
                    else "At least one guarded action did not verify cleanly."
                )
            )
        ),
    }


def summarize_guarded_candidates(
    *,
    orchestrator_workspace: JSONObject,
    shadow_planner_summary: object | None,
) -> JSONObject:
    """Extract guarded opportunities from the shadow timeline in replay mode."""
    if not isinstance(shadow_planner_summary, dict):
        return {"candidate_count": 0, "candidate_actions": []}

    timeline = shadow_planner_summary.get("timeline")
    if not isinstance(timeline, list):
        return {"candidate_count": 0, "candidate_actions": []}

    source_results = _workspace_source_summary(orchestrator_workspace)
    available_structured_sources = tuple(
        source_key
        for source_key in _STRUCTURED_ENRICHMENT_SOURCES
        if source_key in source_results
    )
    candidate_actions: list[JSONObject] = []
    chase_candidate_count = 0
    chase_candidate_exact_selection_match_count = 0
    chase_candidate_overlap_total = 0
    for entry in timeline:
        candidate_action = _summarize_guarded_candidate_for_checkpoint(
            entry=entry,
            available_structured_sources=available_structured_sources,
        )
        if candidate_action is None:
            continue
        candidate_action_summary = _guarded_execution_action_summary(
            candidate_action,
        )
        candidate_action_summary["evaluation_mode"] = (
            "shared_baseline_replay_counterfactual"
        )
        if candidate_action_summary.get("guarded_strategy") == "chase_selection":
            chase_candidate_count += 1
            if bool(candidate_action_summary.get("exact_selection_match")):
                chase_candidate_exact_selection_match_count += 1
            chase_candidate_overlap_total += _guarded_chase_overlap_count(
                candidate_action_summary,
            )
        candidate_actions.append(candidate_action_summary)

    return {
        "candidate_count": len(candidate_actions),
        "chase_candidate_count": chase_candidate_count,
        "chase_candidate_exact_selection_match_count": (
            chase_candidate_exact_selection_match_count
        ),
        "chase_candidate_overlap_total": chase_candidate_overlap_total,
        "candidate_actions": candidate_actions,
    }


def _summarize_guarded_candidate_for_checkpoint(
    *,
    entry: object,
    available_structured_sources: tuple[str, ...],
) -> JSONObject | None:
    candidate_action: JSONObject | None = None
    if not isinstance(entry, dict):
        return None
    checkpoint_key = entry.get("checkpoint_key")
    recommendation = entry.get("recommendation")
    comparison = entry.get("comparison")
    if not isinstance(recommendation, dict) or not isinstance(comparison, dict):
        return None
    workspace_summary = (
        dict(entry.get("workspace_summary"))
        if isinstance(entry.get("workspace_summary"), dict)
        else {}
    )
    if checkpoint_key == "after_driven_terms_ready":
        candidate_action = _accepted_guarded_structured_source_action(
            recommendation_payload=recommendation,
            comparison=comparison,
            available_source_keys=available_structured_sources,
        )
    elif checkpoint_key in {"after_bootstrap", "after_chase_round_1"}:
        candidate_action = _accepted_guarded_control_flow_action(
            recommendation_payload=recommendation,
            comparison=comparison,
        )
        if candidate_action is None:
            chase_candidates = _workspace_chase_candidates(workspace_summary)
            deterministic_selection = _workspace_deterministic_chase_selection(
                workspace_summary,
            )
            round_number = _checkpoint_chase_round_number(checkpoint_key)
            if (
                round_number is not None
                and chase_candidates
                and deterministic_selection is not None
            ):
                candidate_action = _accepted_guarded_chase_selection_action(
                    recommendation_payload=recommendation,
                    comparison=comparison,
                    round_number=round_number,
                    chase_candidates=chase_candidates,
                    deterministic_selection=deterministic_selection,
                )
        if candidate_action is None and checkpoint_key == "after_chase_round_1":
            candidate_action = _accepted_guarded_generate_brief_action(
                recommendation_payload=recommendation,
                comparison=comparison,
            )
    return candidate_action


def _guarded_execution_action_summary(action: JSONObject) -> JSONObject:
    summary: JSONObject = {
        "checkpoint_key": action.get("checkpoint_key"),
        "action_type": action.get("applied_action_type"),
        "source_key": action.get("applied_source_key"),
        "guarded_strategy": action.get("guarded_strategy"),
        "round_number": action.get("round_number"),
        "comparison_status": action.get("comparison_status"),
        "target_action_type": action.get("target_action_type"),
        "target_source_key": action.get("target_source_key"),
        "planner_status": action.get("planner_status"),
        "qualitative_rationale": action.get("qualitative_rationale"),
        "stop_reason": action.get("stop_reason"),
        "recommended_stop": action.get("recommended_stop"),
        "deterministic_stop_expected": action.get("deterministic_stop_expected"),
        "verification_status": action.get("verification_status"),
        "verification_reason": action.get("verification_reason"),
    }
    if action.get("guarded_strategy") != "chase_selection":
        return summary
    selected_entity_ids = _string_list(action.get("selected_entity_ids"))
    selected_labels = _string_list(action.get("selected_labels"))
    deterministic_selected_entity_ids = _string_list(
        action.get("deterministic_selected_entity_ids"),
    )
    deterministic_selected_labels = _string_list(
        action.get("deterministic_selected_labels"),
    )
    summary.update(
        {
            "selected_entity_ids": selected_entity_ids,
            "selected_labels": selected_labels,
            "deterministic_selected_entity_ids": deterministic_selected_entity_ids,
            "deterministic_selected_labels": deterministic_selected_labels,
            "selection_basis": action.get("selection_basis"),
            "selected_entity_overlap_count": len(
                set(selected_entity_ids) & set(deterministic_selected_entity_ids),
            ),
            "exact_selection_match": (
                selected_entity_ids == deterministic_selected_entity_ids
                and selected_labels == deterministic_selected_labels
            ),
        },
    )
    return summary


def _guarded_chase_overlap_count(action: JSONObject) -> int:
    value = action.get("selected_entity_overlap_count")
    return value if isinstance(value, int) else 0


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


@contextmanager
def _temporary_env_setting(name: str, value: str | None) -> Iterator[None]:
    previous = os.getenv(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _dict_value(value: object) -> JSONObject:
    return dict(value) if isinstance(value, dict) else {}


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _checkpoint_chase_round_number(checkpoint_key: object) -> int | None:
    if checkpoint_key == "after_bootstrap":
        return 1
    if checkpoint_key == "after_chase_round_1":
        return 2
    return None


def _workspace_chase_candidates(
    workspace_summary: JSONObject,
) -> tuple[ResearchOrchestratorChaseCandidate, ...]:
    raw_candidates = workspace_summary.get("chase_candidates")
    if not isinstance(raw_candidates, list):
        return ()
    parsed_candidates: list[ResearchOrchestratorChaseCandidate] = []
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            parsed_candidates.append(
                ResearchOrchestratorChaseCandidate.model_validate(candidate),
            )
        except ValidationError:
            continue
    return tuple(parsed_candidates)


def _workspace_deterministic_chase_selection(
    workspace_summary: JSONObject,
) -> ResearchOrchestratorChaseSelection | None:
    selection = workspace_summary.get("deterministic_selection")
    if not isinstance(selection, dict):
        return None
    try:
        return ResearchOrchestratorChaseSelection.model_validate(selection)
    except ValidationError:
        return None


def _normalized_unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        trimmed = value.strip()
        if trimmed == "" or trimmed in seen:
            continue
        seen.add(trimmed)
        normalized.append(trimmed)
    return normalized


def _collect_run_ids_from_payload(value: object) -> list[str]:
    collected: list[str] = []
    visited_json_strings: set[str] = set()

    def _visit(node: object) -> None:
        if isinstance(node, dict):
            for key, nested_value in node.items():
                normalized_key = key.casefold() if isinstance(key, str) else ""
                if normalized_key.endswith("run_ids") and isinstance(
                    nested_value, list
                ):
                    collected.extend(
                        item for item in nested_value if isinstance(item, str)
                    )
                elif normalized_key.endswith("run_id") and isinstance(
                    nested_value, str
                ):
                    collected.append(nested_value)
                _visit(nested_value)
            return
        if isinstance(node, list):
            for item in node:
                _visit(item)
            return
        if isinstance(node, str):
            trimmed = node.strip()
            if trimmed == "" or trimmed in visited_json_strings:
                return
            if trimmed[0] not in {"{", "["}:
                return
            try:
                parsed = json.loads(trimmed)
            except ValueError:
                return
            visited_json_strings.add(trimmed)
            _visit(parsed)

    _visit(value)
    return _normalized_unique_strings(collected)


def _collect_baseline_run_ids(
    *,
    baseline_run_id: str,
    workspace_snapshot: JSONObject | None,
    artifact_contents: list[JSONObject],
) -> list[str]:
    collected = [baseline_run_id]
    if workspace_snapshot is not None:
        collected.extend(_collect_run_ids_from_payload(workspace_snapshot))
    for artifact_content in artifact_contents:
        collected.extend(_collect_run_ids_from_payload(artifact_content))
    return _normalized_unique_strings(collected)


def _collect_shadow_planner_run_ids(
    *,
    decision_history: JSONObject | None,
    latest_shadow_planner_summary: JSONObject | None,
) -> list[str]:
    collected: list[str] = []
    if decision_history is not None:
        collected.extend(_collect_run_ids_from_payload(decision_history))
    if latest_shadow_planner_summary is not None:
        collected.extend(_collect_run_ids_from_payload(latest_shadow_planner_summary))
    return _normalized_unique_strings(collected)


def _unavailable_model_telemetry() -> JSONObject:
    return {
        "status": "unavailable",
        "model_terminal_count": 0,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "cost_usd": None,
        "latency_seconds": None,
        "tool_call_count": 0,
    }


async def _collect_model_telemetry(
    *,
    store: object,
    run_ids: tuple[str, ...],
) -> JSONObject:
    get_events_for_run = getattr(store, "get_events_for_run", None)
    if not callable(get_events_for_run) or not run_ids:
        return _unavailable_model_telemetry()

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
            if payload.cost_usd is not None:
                cost_total += payload.cost_usd
                cost_seen = True

    if model_terminal_count == 0:
        return _unavailable_model_telemetry()

    prompt_tokens = prompt_tokens_total if prompt_tokens_seen else None
    completion_tokens = completion_tokens_total if completion_tokens_seen else None
    total_tokens = None
    if prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    status: Literal["available", "partial", "unavailable"] = "partial"
    if prompt_tokens is not None and completion_tokens is not None and cost_seen:
        status = "available"
    return {
        "status": status,
        "model_terminal_count": model_terminal_count,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_total, 8) if cost_seen else None,
        "latency_seconds": (
            round(latency_ms_total / 1000.0, 6) if latency_seen else None
        ),
        "tool_call_count": tool_call_count,
    }


async def _resolve_run_event_time_window(
    *,
    store: object,
    run_id: str,
) -> tuple[object, object] | None:
    get_events_for_run = getattr(store, "get_events_for_run", None)
    if not callable(get_events_for_run):
        return None

    events = await get_events_for_run(run_id)
    if not isinstance(events, list) or not events:
        return None
    started_at = getattr(events[0], "timestamp", None)
    finished_at = getattr(events[-1], "timestamp", None)
    if started_at is None or finished_at is None:
        return None
    return (started_at, finished_at)


async def _collect_model_terminal_run_ids_for_tenant_window(
    *,
    store: object,
    tenant_id: str,
    started_at: object,
    finished_at: object,
    excluded_run_id_prefixes: tuple[str, ...] = (),
) -> list[str]:
    fetch = getattr(store, "_fetch", None)
    if not callable(fetch):
        return []

    from artana.events import EventType

    rows = await fetch(
        """
        SELECT DISTINCT run_id
        FROM kernel_events
        WHERE tenant_id = $1
          AND event_type = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY run_id ASC
        """,
        tenant_id,
        EventType.MODEL_TERMINAL.value,
        started_at,
        finished_at,
    )
    collected: list[str] = []
    for row in rows:
        run_id = row["run_id"]
        if not isinstance(run_id, str):
            continue
        if any(run_id.startswith(prefix) for prefix in excluded_run_id_prefixes):
            continue
        collected.append(run_id)
    return collected


async def _expand_run_lineage_from_events(
    *,
    store: object,
    run_ids: tuple[str, ...],
) -> list[str]:
    get_events_for_run = getattr(store, "get_events_for_run", None)
    if not callable(get_events_for_run) or not run_ids:
        return list(run_ids)

    discovered = list(run_ids)
    seen = set(run_ids)
    pending: deque[str] = deque(run_ids)

    while pending:
        current_run_id = pending.popleft()
        events = await get_events_for_run(current_run_id)
        if not isinstance(events, list):
            continue
        for event in events:
            payload = getattr(event, "payload", None)
            payload_model_dump = getattr(payload, "model_dump", None)
            if callable(payload_model_dump):
                payload = payload_model_dump(mode="json")
            if not isinstance(payload, dict | list | str):
                continue
            for discovered_run_id in _collect_run_ids_from_payload(payload):
                if discovered_run_id in seen:
                    continue
                seen.add(discovered_run_id)
                discovered.append(discovered_run_id)
                pending.append(discovered_run_id)

    return discovered


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, int):
        return float(value)
    return value if isinstance(value, float) else None


def _build_phase1_cost_comparison(
    *,
    baseline_telemetry: JSONObject,
    shadow_cost_tracking: JSONObject | None,
) -> JSONObject:
    if shadow_cost_tracking is None:
        shadow_cost_tracking = {}

    baseline_status = str(baseline_telemetry.get("status", "unavailable"))
    planner_status = str(shadow_cost_tracking.get("status", "unavailable"))
    baseline_total_cost_usd = _optional_float(baseline_telemetry.get("cost_usd"))
    baseline_total_tokens = _optional_int(baseline_telemetry.get("total_tokens"))
    baseline_latency_seconds = _optional_float(
        baseline_telemetry.get("latency_seconds"),
    )
    planner_total_cost_usd = _optional_float(
        shadow_cost_tracking.get("planner_total_cost_usd"),
    )
    planner_total_tokens = _optional_int(
        shadow_cost_tracking.get("planner_total_tokens"),
    )
    planner_latency_seconds = _optional_float(
        shadow_cost_tracking.get("planner_total_latency_seconds"),
    )

    ratio = None
    within_limit = None
    evaluated = False
    notes = (
        "Cost comparison is unavailable until both deterministic baseline and "
        "shadow planner telemetry are present."
    )
    if baseline_total_cost_usd is not None and planner_total_cost_usd is not None:
        evaluated = True
        if baseline_total_cost_usd > 0:
            ratio = round(planner_total_cost_usd / baseline_total_cost_usd, 6)
            within_limit = planner_total_cost_usd <= baseline_total_cost_usd * 2.0
            notes = (
                "Planner cost can now be compared against the real deterministic "
                "baseline from the Phase 1 replay."
            )
        else:
            notes = (
                "Deterministic baseline telemetry is present, but its recorded "
                "cost is zero, so a planner-to-baseline ratio cannot be computed."
            )
    return {
        "status": (
            "available"
            if evaluated
            else (
                "partial"
                if baseline_status != "unavailable" or planner_status != "unavailable"
                else "unavailable"
            )
        ),
        "evaluated": evaluated,
        "baseline_status": baseline_status,
        "planner_status": planner_status,
        "baseline_total_cost_usd": baseline_total_cost_usd,
        "baseline_total_tokens": baseline_total_tokens,
        "baseline_latency_seconds": baseline_latency_seconds,
        "planner_total_cost_usd": planner_total_cost_usd,
        "planner_total_tokens": planner_total_tokens,
        "planner_latency_seconds": planner_latency_seconds,
        "planner_vs_baseline_cost_ratio": ratio,
        "gate_within_2x_baseline": within_limit,
        "notes": notes,
    }


def _normalize_pending_questions(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized_questions: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized_question = _UUID_PATTERN.sub("<uuid>", item)
        normalized_questions.add(
            _pending_question_signature(normalized_question),
        )
    return sorted(normalized_questions)


_PENDING_QUESTION_RELATION_PATTERN = re.compile(
    r"^(What evidence best supports )(.+?) ([A-Z_]+) (.+\?)$",
)


def _pending_question_signature(question: str) -> str:
    match = _PENDING_QUESTION_RELATION_PATTERN.match(question)
    if match is None:
        return question
    prefix, subject, _relation, obj = match.groups()
    return f"{prefix}{subject} <relation> {obj}"


_ORDER_INSENSITIVE_SOURCE_RESULT_LIST_KEYS = {
    "alias_errors",
    "available_enrichment_sources",
    "deferred_enrichment_sources",
    "driven_genes_from_pubmed",
    "filtered_chase_labels",
    "selected_enrichment_sources",
}


def _normalize_source_results(value: object, *, key: str | None = None) -> object:
    if isinstance(value, dict):
        return {
            nested_key: _normalize_source_results(nested_value, key=nested_key)
            for nested_key, nested_value in sorted(value.items())
            if isinstance(nested_key, str)
        }
    if isinstance(value, list):
        normalized_items = [_normalize_source_results(item, key=key) for item in value]
        if key in _ORDER_INSENSITIVE_SOURCE_RESULT_LIST_KEYS and all(
            isinstance(item, str) for item in normalized_items
        ):
            normalized_string_items = [
                item for item in normalized_items if isinstance(item, str)
            ]
            return sorted(normalized_string_items)
        return normalized_items
    return value


def resolve_compare_environment() -> JSONObject:
    """Return the volatile environment settings relevant to compare runs."""
    backend = os.getenv(_PUBMED_BACKEND_ENV)
    normalized_backend = backend.strip().lower() if isinstance(backend, str) else ""
    if normalized_backend == "":
        normalized_backend = "default"
    return {
        "pubmed_search_backend": normalized_backend,
    }


async def _collect_baseline_telemetry_for_compare(
    *,
    space_id: str,
    baseline_run_id: str,
    workspace_snapshot: JSONObject | None,
    artifact_contents: list[JSONObject],
) -> tuple[list[str], JSONObject]:
    baseline_telemetry_run_ids = _collect_baseline_run_ids(
        baseline_run_id=baseline_run_id,
        workspace_snapshot=workspace_snapshot,
        artifact_contents=artifact_contents,
    )
    telemetry_store = create_artana_postgres_store()
    try:
        baseline_time_window = await _resolve_run_event_time_window(
            store=telemetry_store,
            run_id=baseline_run_id,
        )
        baseline_telemetry_run_ids = await _expand_run_lineage_from_events(
            store=telemetry_store,
            run_ids=tuple(baseline_telemetry_run_ids),
        )
        if baseline_time_window is not None:
            tenant_scoped_run_ids = (
                await _collect_model_terminal_run_ids_for_tenant_window(
                    store=telemetry_store,
                    tenant_id=space_id,
                    started_at=baseline_time_window[0],
                    finished_at=baseline_time_window[1],
                    excluded_run_id_prefixes=("full-ai-shadow-planner:",),
                )
            )
            baseline_telemetry_run_ids = _normalized_unique_strings(
                baseline_telemetry_run_ids + tenant_scoped_run_ids,
            )
        baseline_telemetry = await _collect_model_telemetry(
            store=telemetry_store,
            run_ids=tuple(baseline_telemetry_run_ids),
        )
    finally:
        await telemetry_store.close()
    return baseline_telemetry_run_ids, baseline_telemetry


def build_compare_advisories(
    *,
    mismatches: list[str],
    environment: JSONObject,
    guarded_evaluation: JSONObject | None = None,
) -> list[str]:
    """Explain known sources of volatility in compare output."""
    advisories: list[str] = []
    pubmed_backend = environment.get("pubmed_search_backend")
    if mismatches and pubmed_backend != "deterministic":
        advisories.append(
            "Live PubMed/backend variability can change candidate sets and proposal counts between runs; rerun compare with the deterministic backend to isolate orchestrator parity.",
        )
    compare_mode = environment.get("compare_mode")
    if (
        compare_mode == _DUAL_LIVE_GUARDED_MODE
        and isinstance(guarded_evaluation, dict)
        and guarded_evaluation.get("status") == "clean"
        and mismatches
    ):
        advisories.append(
            "Live guarded compare is expected to diverge from the deterministic baseline when the planner actually narrows structured sources or stops before chase round 2.",
        )
    if isinstance(guarded_evaluation, dict):
        status = guarded_evaluation.get("status")
        if status == "verification_failed":
            advisories.append(
                "Guarded pilot accepted an action that did not verify cleanly; inspect guarded_evaluation.failed_actions before widening the allowlist.",
            )
        elif status == "verification_pending":
            advisories.append(
                "Guarded pilot left accepted actions in a pending verification state; verify the execution hooks ran after the guarded action completed.",
            )
    return advisories


def compare_workspace_summaries(
    *,
    baseline: JSONObject,
    orchestrator: JSONObject,
) -> list[str]:
    """Return human-readable mismatches between baseline and orchestrator."""
    mismatches = [
        (
            f"{field_name}: baseline={baseline.get(field_name)!r} "
            f"orchestrator={orchestrator.get(field_name)!r}"
        )
        for field_name in (
            "documents_ingested",
            "proposal_count",
            "pubmed_results",
            "driven_terms",
            "brief_present",
        )
        if baseline.get(field_name) != orchestrator.get(field_name)
    ]
    baseline_pending_questions = _normalize_pending_questions(
        baseline.get("pending_questions"),
    )
    orchestrator_pending_questions = _normalize_pending_questions(
        orchestrator.get("pending_questions"),
    )
    if baseline_pending_questions != orchestrator_pending_questions:
        mismatches.append(
            "pending_questions: "
            f"baseline={baseline_pending_questions!r} "
            f"orchestrator={orchestrator_pending_questions!r}",
        )
    baseline_sources = _normalize_source_results(baseline.get("source_results"))
    orchestrator_sources = _normalize_source_results(orchestrator.get("source_results"))
    if baseline_sources != orchestrator_sources:
        mismatches.append(
            "source_results differ between baseline and orchestrator summaries",
        )
    return mismatches


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
                settings={"sources": dict(request.sources)},
            )
            orchestrator_space = research_space_store.create_space(
                owner_id=_COMPARE_OWNER_ID,
                owner_email=_COMPARE_OWNER_EMAIL,
                name=f"{request.title} guarded {uuid4().hex[:8]}",
                description="Phase 1 live guarded compare orchestrator space",
                settings={"sources": dict(request.sources)},
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
            baseline_result = execute_research_init_run(
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
            )
            baseline_result = await _await_compare_phase(
                awaitable=baseline_result,
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
            orchestrator_result = execute_full_ai_orchestrator_run(
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
                structured_enrichment_replay_bundle=structured_enrichment_replay_bundle,
            )
            orchestrator_result = await _await_compare_phase(
                awaitable=orchestrator_result,
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
                settings={"sources": dict(request.sources)},
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
            baseline_result = execute_research_init_run(
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
            )
            baseline_result = await _await_compare_phase(
                awaitable=baseline_result,
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
            orchestrator_result = execute_full_ai_orchestrator_run(
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
                    None if baseline_workspace is None else baseline_workspace.snapshot
                ),
                replayed_phase_records=deepcopy(
                    orchestrator_progress_observer.phase_records
                ),
            )
            orchestrator_result = await _await_compare_phase(
                awaitable=orchestrator_result,
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
                "sources": dict(request.sources),
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


def _rollout_proof_summary(
    *,
    rollout_enabled: bool,
    rollout_profile: str,
    run_id: str,
    space_id: str,
    workspace_snapshot: JSONObject | None,
    shadow_planner_summary: JSONObject | None,
    seam_results: list[JSONObject],
    structured_seam_results: list[JSONObject],
) -> JSONObject:
    workspace_summary = summarize_workspace(workspace_snapshot)
    guarded_evaluation = build_guarded_evaluation(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        orchestrator_workspace=workspace_summary,
        shadow_planner_summary=shadow_planner_summary,
    )
    return {
        "space_id": space_id,
        "run_id": run_id,
        "guarded_rollout_profile": rollout_profile,
        "guarded_chase_rollout_enabled": rollout_enabled,
        "workspace": workspace_summary,
        "guarded_evaluation": guarded_evaluation,
        "seam_results": seam_results,
        "structured_seam_results": structured_seam_results,
        "selection_returned_count": sum(
            1 for result in seam_results if bool(result.get("selection_returned"))
        ),
        "structured_selection_returned_count": sum(
            1
            for result in structured_seam_results
            if bool(result.get("selection_returned"))
        ),
    }


def _checkpoint_workspace_summary(
    *,
    shadow_timeline: list[JSONObject],
    checkpoint_key: str,
) -> JSONObject | None:
    for entry in reversed(shadow_timeline):
        if entry.get("checkpoint_key") != checkpoint_key:
            continue
        workspace_summary = entry.get("workspace_summary")
        if isinstance(workspace_summary, dict):
            return dict(workspace_summary)
    return None


def _available_structured_sources_from_workspace(
    workspace_snapshot: JSONObject,
) -> tuple[str, ...]:
    source_results = _dict_value(workspace_snapshot.get("source_results"))
    selected_sources: list[str] = []
    for source_key in _STRUCTURED_ENRICHMENT_SOURCES:
        summary = source_results.get(source_key)
        if not isinstance(summary, dict):
            continue
        if summary.get("selected") is True:
            selected_sources.append(source_key)
    return tuple(selected_sources)


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
                dict(persisted_snapshot.get("guarded_structured_enrichment_selection"))
                if isinstance(
                    persisted_snapshot.get("guarded_structured_enrichment_selection"),
                    dict,
                )
                else None
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
                    dict(
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
            settings={"sources": dict(request.sources)},
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
        profile_comparison: JSONObject = {
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
                "sources": dict(request.sources),
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
    "_build_phase1_cost_comparison",
    "_collect_run_ids_from_payload",
]
