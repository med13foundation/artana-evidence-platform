"""Guarded decision artifact helpers for the full AI orchestrator."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator_common_support import _planner_mode_value
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
    ResearchOrchestratorDecision,
    ResearchOrchestratorGuardedDecisionProof,
)
from artana_evidence_api.full_ai_orchestrator_guarded_rollout import (
    _guarded_profile_allows,
    _guarded_rollout_policy_summary,
)
from artana_evidence_api.types.common import (
    JSONObject,
    json_int,
    json_object_or_empty,
)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore

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



def _put_decision_history_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    decisions: list[ResearchOrchestratorDecision],
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_DECISION_HISTORY_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "decisions": [decision.model_dump(mode="json") for decision in decisions],
            "decision_count": len(decisions),
        },
    )

def _put_shadow_planner_artifacts(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    timeline: list[JSONObject],
    latest_summary: JSONObject,
    mode: str,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "mode": mode,
            "checkpoints": timeline,
            "checkpoint_count": len(timeline),
        },
    )
    latest_workspace_summary = latest_summary.get("latest_workspace_summary")
    if isinstance(latest_workspace_summary, dict):
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key=_SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
            media_type="application/json",
            content=latest_workspace_summary,
        )
    latest_recommendation = latest_summary.get("latest_recommendation")
    if isinstance(latest_recommendation, dict):
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key=_SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
            media_type="application/json",
            content=latest_recommendation,
        )
    latest_comparison = latest_summary.get("latest_comparison")
    if isinstance(latest_comparison, dict):
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key=_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
            media_type="application/json",
            content=latest_comparison,
        )

def _put_guarded_execution_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    planner_mode: FullAIOrchestratorPlannerMode,
    actions: list[JSONObject],
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_GUARDED_EXECUTION_ARTIFACT_KEY,
        media_type="application/json",
        content=_guarded_execution_summary(
            planner_mode=planner_mode,
            actions=actions,
        ),
    )

def _guarded_decision_proof_artifact_key(*, proof_id: str) -> str:
    normalized_proof_id = "".join(
        character if character.isalnum() else "_"
        for character in proof_id.strip().casefold()
    ).strip("_")
    if not normalized_proof_id:
        normalized_proof_id = "proof"
    return f"{_GUARDED_DECISION_PROOF_ARTIFACT_PREFIX}_{normalized_proof_id}"

def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None

def _decision_payload_from_recommendation(
    recommendation_payload: JSONObject,
) -> JSONObject:
    decision = recommendation_payload.get("decision")
    return dict(decision) if isinstance(decision, dict) else {}

def _guarded_strategy_for_recommendation(
    *,
    recommendation_payload: JSONObject,
    default_strategy: str,
) -> str:
    decision = _decision_payload_from_recommendation(recommendation_payload)
    action_type = decision.get("action_type")
    if action_type == ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT.value:
        return _GUARDED_STRATEGY_STRUCTURED_SOURCE
    if action_type == ResearchOrchestratorActionType.RUN_CHASE_ROUND.value:
        return _GUARDED_STRATEGY_CHASE_SELECTION
    if action_type == ResearchOrchestratorActionType.GENERATE_BRIEF.value:
        return _GUARDED_STRATEGY_BRIEF_GENERATION
    if action_type in {
        ResearchOrchestratorActionType.STOP.value,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value,
    }:
        return _GUARDED_STRATEGY_TERMINAL_CONTROL
    return default_strategy

def _guarded_rejection_reason(
    *,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
    default_reason: str,
) -> str:
    if recommendation_payload.get("planner_status") != "completed":
        return "planner_not_completed"
    if bool(recommendation_payload.get("used_fallback")):
        fallback_reason = recommendation_payload.get("fallback_reason")
        return (
            f"fallback_recommendation:{fallback_reason}"
            if isinstance(fallback_reason, str) and fallback_reason
            else "fallback_recommendation"
        )
    validation_error = recommendation_payload.get("validation_error")
    if isinstance(validation_error, str) and validation_error:
        return "invalid_planner_output"
    if comparison.get("budget_violation") is True:
        return "budget_violation"
    if comparison.get("qualitative_rationale_present") is False:
        return "qualitative_rationale_missing"
    return default_reason

def _build_guarded_decision_proof(
    *,
    proof_id: str,
    checkpoint_key: str,
    guarded_strategy: str,
    planner_mode: FullAIOrchestratorPlannerMode,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str,
    decision_outcome: Literal["allowed", "blocked", "ignored"],
    outcome_reason: str,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
    guarded_action: JSONObject | None = None,
    policy_allowed: bool = False,
    disabled_source_violation: bool = False,
) -> ResearchOrchestratorGuardedDecisionProof:
    decision = _decision_payload_from_recommendation(recommendation_payload)
    applied_action_type = (
        _string_or_none(guarded_action.get("applied_action_type"))
        if guarded_action is not None
        else None
    )
    applied_source_key = (
        _string_or_none(guarded_action.get("applied_source_key"))
        if guarded_action is not None
        else None
    )
    return ResearchOrchestratorGuardedDecisionProof(
        proof_id=proof_id,
        artifact_key=_guarded_decision_proof_artifact_key(proof_id=proof_id),
        checkpoint_key=checkpoint_key,
        guarded_strategy=guarded_strategy,
        planner_mode=(
            "guarded"
            if planner_mode is FullAIOrchestratorPlannerMode.GUARDED
            else "shadow"
        ),
        guarded_rollout_profile=guarded_rollout_profile,
        guarded_rollout_profile_source=guarded_rollout_profile_source,
        guarded_policy_version=_GUARDED_ROLLOUT_POLICY_VERSION,
        decision_outcome=decision_outcome,
        outcome_reason=outcome_reason,
        deterministic_action_type=_string_or_none(comparison.get("target_action_type")),
        deterministic_source_key=_string_or_none(comparison.get("target_source_key")),
        recommended_action_type=_string_or_none(
            comparison.get("recommended_action_type"),
        )
        or _string_or_none(decision.get("action_type")),
        recommended_source_key=_string_or_none(comparison.get("recommended_source_key"))
        or _string_or_none(decision.get("source_key")),
        applied_action_type=applied_action_type,
        applied_source_key=applied_source_key,
        planner_status=_string_or_none(recommendation_payload.get("planner_status")),
        used_fallback=bool(recommendation_payload.get("used_fallback")),
        fallback_reason=_string_or_none(recommendation_payload.get("fallback_reason")),
        validation_error=_string_or_none(
            recommendation_payload.get("validation_error")
        ),
        qualitative_rationale_present=bool(
            comparison.get("qualitative_rationale_present"),
        ),
        budget_violation=bool(comparison.get("budget_violation")),
        disabled_source_violation=disabled_source_violation,
        policy_allowed=policy_allowed,
        comparison_status=_string_or_none(comparison.get("comparison_status")),
        verification_status=(
            _string_or_none(guarded_action.get("verification_status"))
            if guarded_action is not None
            else None
        ),
        verification_reason=(
            _string_or_none(guarded_action.get("verification_reason"))
            if guarded_action is not None
            else None
        ),
        model_id=_string_or_none(recommendation_payload.get("model_id")),
        prompt_version=_string_or_none(recommendation_payload.get("prompt_version")),
        agent_run_id=_string_or_none(recommendation_payload.get("agent_run_id")),
        decision_id=_string_or_none(decision.get("decision_id")),
        step_key=_string_or_none(decision.get("step_key")),
        qualitative_rationale=_string_or_none(decision.get("qualitative_rationale")),
        evidence_basis=_string_or_none(decision.get("evidence_basis")),
        comparison=dict(comparison),
        recommendation=dict(recommendation_payload),
        guarded_action=dict(guarded_action) if guarded_action is not None else None,
    )

def _guarded_decision_proof_summary(
    *,
    planner_mode: FullAIOrchestratorPlannerMode,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str = "resolved",
    proofs: list[ResearchOrchestratorGuardedDecisionProof],
) -> JSONObject:
    allowed_count = sum(1 for proof in proofs if proof.decision_outcome == "allowed")
    blocked_count = sum(1 for proof in proofs if proof.decision_outcome == "blocked")
    ignored_count = sum(1 for proof in proofs if proof.decision_outcome == "ignored")
    verified_count = sum(
        1 for proof in proofs if proof.verification_status == "verified"
    )
    verification_failed_count = sum(
        1 for proof in proofs if proof.verification_status == "verification_failed"
    )
    pending_verification_count = sum(
        1 for proof in proofs if proof.verification_status == "pending"
    )
    return {
        "mode": _planner_mode_value(planner_mode),
        "policy_version": _GUARDED_ROLLOUT_POLICY_VERSION,
        "guarded_rollout_profile": guarded_rollout_profile,
        "guarded_rollout_profile_source": guarded_rollout_profile_source,
        "proof_count": len(proofs),
        "allowed_count": allowed_count,
        "blocked_count": blocked_count,
        "ignored_count": ignored_count,
        "verified_count": verified_count,
        "verification_failed_count": verification_failed_count,
        "pending_verification_count": pending_verification_count,
        "artifact_keys": [proof.artifact_key for proof in proofs],
        "proofs": [proof.model_dump(mode="json") for proof in proofs],
    }

def _put_guarded_decision_proof_artifacts(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    planner_mode: FullAIOrchestratorPlannerMode,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str = "resolved",
    proofs: list[ResearchOrchestratorGuardedDecisionProof],
) -> None:
    for proof in proofs:
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key=proof.artifact_key,
            media_type="application/json",
            content=proof.model_dump(mode="json"),
        )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY,
        media_type="application/json",
        content=_guarded_decision_proof_summary(
            planner_mode=planner_mode,
            guarded_rollout_profile=guarded_rollout_profile,
            guarded_rollout_profile_source=guarded_rollout_profile_source,
            proofs=proofs,
        ),
    )

def _guarded_action_with_policy(
    *,
    action: JSONObject,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str = "resolved",
) -> JSONObject:
    guarded_strategy = action.get("guarded_strategy")
    annotated = dict(action)
    annotated["guarded_policy_version"] = _GUARDED_ROLLOUT_POLICY_VERSION
    annotated["guarded_rollout_profile"] = guarded_rollout_profile
    annotated["guarded_rollout_profile_source"] = guarded_rollout_profile_source
    annotated["guarded_policy_allowed"] = isinstance(
        guarded_strategy, str
    ) and _guarded_profile_allows(
        guarded_rollout_profile=guarded_rollout_profile,
        guarded_strategy=guarded_strategy,
    )
    return annotated

def _guarded_action_allowed_by_profile(
    *,
    action: JSONObject,
    guarded_rollout_profile: str,
) -> bool:
    guarded_strategy = action.get("guarded_strategy")
    if not isinstance(guarded_strategy, str) or not _guarded_profile_allows(
        guarded_rollout_profile=guarded_rollout_profile,
        guarded_strategy=guarded_strategy,
    ):
        return False
    if (
        guarded_rollout_profile == _GUARDED_PROFILE_SOURCE_CHASE
        and guarded_strategy == _GUARDED_STRATEGY_TERMINAL_CONTROL
    ):
        return (
            action.get("applied_action_type")
            == ResearchOrchestratorActionType.STOP.value
        )
    return True

def _guarded_execution_summary(
    *,
    planner_mode: FullAIOrchestratorPlannerMode,
    actions: list[JSONObject],
) -> JSONObject:
    verified_count = 0
    verification_failed_count = 0
    pending_verification_count = 0
    stop_action_count = 0
    escalate_action_count = 0
    brief_action_count = 0
    for action in actions:
        applied_action_type = action.get("applied_action_type")
        if applied_action_type == ResearchOrchestratorActionType.STOP.value:
            stop_action_count += 1
        elif (
            applied_action_type
            == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
        ):
            escalate_action_count += 1
        elif applied_action_type == ResearchOrchestratorActionType.GENERATE_BRIEF.value:
            brief_action_count += 1
        verification_status = action.get("verification_status")
        if verification_status == "verified":
            verified_count += 1
        elif verification_status == "verification_failed":
            verification_failed_count += 1
        elif verification_status == "pending":
            pending_verification_count += 1
    return {
        "mode": _planner_mode_value(planner_mode),
        "applied_count": len(actions),
        "verified_count": verified_count,
        "verification_failed_count": verification_failed_count,
        "pending_verification_count": pending_verification_count,
        "stop_action_count": stop_action_count,
        "escalate_action_count": escalate_action_count,
        "brief_action_count": brief_action_count,
        "control_action_count": stop_action_count + escalate_action_count,
        "actions": list(actions),
    }

def _guarded_readiness_summary(
    *,
    planner_mode: FullAIOrchestratorPlannerMode,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str = "resolved",
    actions: list[JSONObject],
    proofs: list[ResearchOrchestratorGuardedDecisionProof] | None = None,
) -> JSONObject:
    execution_summary = _guarded_execution_summary(
        planner_mode=planner_mode,
        actions=actions,
    )
    verification_failed_count = json_int(
        execution_summary["verification_failed_count"]
    )
    pending_verification_count = json_int(
        execution_summary["pending_verification_count"]
    )
    applied_count = json_int(execution_summary["applied_count"])
    proof_summary = _guarded_decision_proof_summary(
        planner_mode=planner_mode,
        guarded_rollout_profile=guarded_rollout_profile,
        guarded_rollout_profile_source=guarded_rollout_profile_source,
        proofs=proofs or [],
    )
    proof_blocked_count = json_int(proof_summary["blocked_count"])
    proof_ignored_count = json_int(proof_summary["ignored_count"])
    proof_verification_failed_count = json_int(
        proof_summary["verification_failed_count"]
    )
    proof_pending_verification_count = json_int(
        proof_summary["pending_verification_count"]
    )
    blocked_or_ignored_count = proof_blocked_count + proof_ignored_count
    if planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
        status = "not_applicable"
    elif verification_failed_count > 0 or proof_verification_failed_count > 0:
        status = "blocked_verification_failed"
    elif blocked_or_ignored_count > 0 and guarded_rollout_profile not in {
        _GUARDED_PROFILE_SHADOW_ONLY,
        _GUARDED_PROFILE_DRY_RUN,
    }:
        status = "blocked_guarded_decision_proofs"
    elif pending_verification_count > 0 or proof_pending_verification_count > 0:
        status = "pending_verification"
    elif guarded_rollout_profile in {
        _GUARDED_PROFILE_SHADOW_ONLY,
        _GUARDED_PROFILE_DRY_RUN,
    }:
        status = "observation_only"
    elif applied_count == 0:
        status = "ready_no_guarded_actions_applied"
    else:
        status = "ready_verified"
    applied_strategies = sorted(
        {
            str(action["guarded_strategy"])
            for action in actions
            if isinstance(action.get("guarded_strategy"), str)
        },
    )
    applied_strategy_counts = _applied_strategy_counts(actions)
    intervention_counts = _intervention_counts(actions, applied_strategy_counts)
    profile_allowed_strategies = sorted(
        _GUARDED_PROFILE_ALLOWED_STRATEGIES.get(guarded_rollout_profile, frozenset()),
    )
    profile_authority_exercised = _profile_authority_exercised(
        guarded_rollout_profile=guarded_rollout_profile,
        intervention_counts=intervention_counts,
    )
    return {
        "status": status,
        "ready_for_wider_rollout": status
        in {
            "ready_no_guarded_actions_applied",
            "ready_verified",
        },
        "policy": _guarded_rollout_policy_summary(
            planner_mode=planner_mode,
            guarded_rollout_profile=guarded_rollout_profile,
            guarded_rollout_profile_source=guarded_rollout_profile_source,
        ),
        "proofs": {
            "proof_count": proof_summary["proof_count"],
            "allowed_count": proof_summary["allowed_count"],
            "blocked_count": proof_summary["blocked_count"],
            "ignored_count": proof_summary["ignored_count"],
            "verified_count": proof_summary["verified_count"],
            "pending_verification_count": proof_summary["pending_verification_count"],
            "verification_failed_count": proof_summary["verification_failed_count"],
        },
        "applied_guarded_strategies": applied_strategies,
        "applied_strategy_counts": applied_strategy_counts,
        "intervention_counts": intervention_counts,
        "profile_allowed_strategies": profile_allowed_strategies,
        "profile_authority_exercised": profile_authority_exercised,
        "execution": execution_summary,
    }

def _applied_strategy_counts(actions: list[JSONObject]) -> JSONObject:
    counts: dict[str, int] = {
        _GUARDED_STRATEGY_STRUCTURED_SOURCE: 0,
        _GUARDED_STRATEGY_CHASE_SELECTION: 0,
        _GUARDED_STRATEGY_TERMINAL_CONTROL: 0,
        _GUARDED_STRATEGY_BRIEF_GENERATION: 0,
    }
    for action in actions:
        strategy = action.get("guarded_strategy")
        if isinstance(strategy, str) and strategy in counts:
            counts[strategy] += 1
    return json_object_or_empty(counts)

def _intervention_counts(
    actions: list[JSONObject],
    applied_strategy_counts: JSONObject,
) -> JSONObject:
    terminal_stop_count = sum(
        1
        for action in actions
        if action.get("guarded_strategy") == _GUARDED_STRATEGY_TERMINAL_CONTROL
        and action.get("applied_action_type")
        == ResearchOrchestratorActionType.STOP.value
    )
    return {
        "source_selection": json_int(
            applied_strategy_counts[_GUARDED_STRATEGY_STRUCTURED_SOURCE],
        ),
        "chase_or_stop": json_int(
            applied_strategy_counts[_GUARDED_STRATEGY_CHASE_SELECTION],
        )
        + terminal_stop_count,
        "brief_generation": json_int(
            applied_strategy_counts[_GUARDED_STRATEGY_BRIEF_GENERATION],
        ),
    }

def _profile_authority_exercised(
    *,
    guarded_rollout_profile: str,
    intervention_counts: JSONObject,
) -> bool | None:
    if guarded_rollout_profile in {
        _GUARDED_PROFILE_SHADOW_ONLY,
        _GUARDED_PROFILE_DRY_RUN,
    }:
        return None
    source = json_int(intervention_counts["source_selection"])
    chase_or_stop = json_int(intervention_counts["chase_or_stop"])
    brief = json_int(intervention_counts["brief_generation"])
    if guarded_rollout_profile == _GUARDED_PROFILE_CHASE_ONLY:
        return chase_or_stop > 0 or brief > 0
    if guarded_rollout_profile == _GUARDED_PROFILE_SOURCE_CHASE:
        return source > 0 and chase_or_stop > 0
    if guarded_rollout_profile == _GUARDED_PROFILE_LOW_RISK:
        return source > 0 or chase_or_stop > 0 or brief > 0
    return None

def _put_guarded_readiness_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    planner_mode: FullAIOrchestratorPlannerMode,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str = "resolved",
    actions: list[JSONObject],
    proofs: list[ResearchOrchestratorGuardedDecisionProof] | None = None,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_GUARDED_READINESS_ARTIFACT_KEY,
        media_type="application/json",
        content=_guarded_readiness_summary(
            planner_mode=planner_mode,
            guarded_rollout_profile=guarded_rollout_profile,
            guarded_rollout_profile_source=guarded_rollout_profile_source,
            actions=actions,
            proofs=proofs,
        ),
    )
