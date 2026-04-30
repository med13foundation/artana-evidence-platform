"""Guarded decision proof builders and summaries."""

from __future__ import annotations

from typing import Literal

from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _GUARDED_DECISION_PROOF_ARTIFACT_PREFIX,
    _GUARDED_ROLLOUT_POLICY_VERSION,
    _GUARDED_STRATEGY_BRIEF_GENERATION,
    _GUARDED_STRATEGY_CHASE_SELECTION,
    _GUARDED_STRATEGY_STRUCTURED_SOURCE,
    _GUARDED_STRATEGY_TERMINAL_CONTROL,
)
from artana_evidence_api.full_ai_orchestrator.workspace_support import (
    _planner_mode_value,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorActionType,
    ResearchOrchestratorGuardedDecisionProof,
)
from artana_evidence_api.types.common import JSONObject


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


__all__ = [
    "_build_guarded_decision_proof",
    "_decision_payload_from_recommendation",
    "_guarded_decision_proof_artifact_key",
    "_guarded_decision_proof_summary",
    "_guarded_rejection_reason",
    "_guarded_strategy_for_recommendation",
    "_string_or_none",
]
