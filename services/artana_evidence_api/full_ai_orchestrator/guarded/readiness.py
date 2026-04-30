"""Guarded execution and rollout-readiness summaries."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.guarded.decision_proofs import (
    _guarded_decision_proof_summary,
)
from artana_evidence_api.full_ai_orchestrator.guarded.rollout import (
    _guarded_rollout_policy_summary,
)
from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _GUARDED_PROFILE_ALLOWED_STRATEGIES,
    _GUARDED_PROFILE_CHASE_ONLY,
    _GUARDED_PROFILE_DRY_RUN,
    _GUARDED_PROFILE_LOW_RISK,
    _GUARDED_PROFILE_SHADOW_ONLY,
    _GUARDED_PROFILE_SOURCE_CHASE,
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
from artana_evidence_api.types.common import JSONObject, json_int, json_object_or_empty


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
    verification_failed_count = json_int(execution_summary["verification_failed_count"])
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


__all__ = [
    "_applied_strategy_counts",
    "_guarded_execution_summary",
    "_guarded_readiness_summary",
    "_intervention_counts",
    "_profile_authority_exercised",
]
