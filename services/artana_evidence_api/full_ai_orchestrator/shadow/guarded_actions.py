"""Guarded-action acceptance helpers for shadow planner recommendations."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _GUARDED_STRATEGY_BRIEF_GENERATION,
    _GUARDED_STRATEGY_CHASE_SELECTION,
    _GUARDED_STRATEGY_STRUCTURED_SOURCE,
    _GUARDED_STRATEGY_TERMINAL_CONTROL,
)
from artana_evidence_api.full_ai_orchestrator.workspace_support import (
    _normalized_source_key_list,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
)
from artana_evidence_api.types.common import JSONObject


def _guarded_recommendation_decision_payload(
    *,
    recommendation_payload: JSONObject,
) -> tuple[JSONObject | None, str | None]:
    decision = recommendation_payload.get("decision")
    if not isinstance(decision, dict):
        return None, None
    rationale = decision.get("qualitative_rationale")
    if recommendation_payload.get("planner_status") != "completed":
        return None, None
    if bool(recommendation_payload.get("used_fallback")):
        return None, None
    if recommendation_payload.get("validation_error") is not None:
        return None, None
    if not isinstance(rationale, str) or rationale.strip() == "":
        return None, None
    return decision, rationale


def _guarded_terminal_control_reason(action_type: object) -> str:
    if action_type == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value:
        return "guarded_escalate_to_human"
    return "guarded_stop_requested"


def _accepted_guarded_generate_brief_action(
    *,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
) -> JSONObject | None:
    decision, rationale = _guarded_recommendation_decision_payload(
        recommendation_payload=recommendation_payload,
    )
    if decision is None or rationale is None:
        return None
    if (
        decision.get("action_type")
        != ResearchOrchestratorActionType.GENERATE_BRIEF.value
    ):
        return None
    if decision.get("source_key") is not None:
        return None
    if (
        comparison.get("target_action_type")
        != ResearchOrchestratorActionType.RUN_CHASE_ROUND.value
    ):
        return None
    return {
        "status": "applied",
        "checkpoint_key": comparison.get("checkpoint_key"),
        "applied_action_type": decision.get("action_type"),
        "applied_source_key": decision.get("source_key"),
        "guarded_strategy": _GUARDED_STRATEGY_BRIEF_GENERATION,
        "stop_reason": "guarded_generate_brief",
        "comparison_status": comparison.get("comparison_status"),
        "target_action_type": comparison.get("target_action_type"),
        "target_source_key": comparison.get("target_source_key"),
        "planner_status": recommendation_payload.get("planner_status"),
        "model_id": recommendation_payload.get("model_id"),
        "agent_run_id": recommendation_payload.get("agent_run_id"),
        "prompt_version": recommendation_payload.get("prompt_version"),
        "decision_id": decision.get("decision_id"),
        "step_key": decision.get("step_key"),
        "evidence_basis": decision.get("evidence_basis"),
        "qualitative_rationale": rationale,
        "expected_value_band": decision.get("expected_value_band"),
        "risk_level": decision.get("risk_level"),
        "verification_status": "pending",
        "verification_reason": None,
        "verification_summary": None,
        "verified_at_phase": None,
    }


def _accepted_guarded_control_flow_action(
    *,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
) -> JSONObject | None:
    decision, rationale = _guarded_recommendation_decision_payload(
        recommendation_payload=recommendation_payload,
    )
    if decision is None or rationale is None:
        return None
    if decision.get("source_key") is not None:
        return None
    if decision.get("action_type") not in {
        ResearchOrchestratorActionType.STOP.value,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value,
    }:
        return None
    target_action_type = comparison.get("target_action_type")
    if target_action_type not in {
        ResearchOrchestratorActionType.RUN_CHASE_ROUND.value,
        ResearchOrchestratorActionType.STOP.value,
    }:
        return None
    if (
        target_action_type == ResearchOrchestratorActionType.STOP.value
        and decision.get("action_type") != ResearchOrchestratorActionType.STOP.value
    ):
        return None
    stop_reason = _guarded_terminal_control_reason(decision.get("action_type"))
    return {
        "status": "applied",
        "checkpoint_key": comparison.get("checkpoint_key"),
        "applied_action_type": decision.get("action_type"),
        "applied_source_key": decision.get("source_key"),
        "guarded_strategy": _GUARDED_STRATEGY_TERMINAL_CONTROL,
        "comparison_status": comparison.get("comparison_status"),
        "target_action_type": comparison.get("target_action_type"),
        "target_source_key": comparison.get("target_source_key"),
        "planner_status": recommendation_payload.get("planner_status"),
        "model_id": recommendation_payload.get("model_id"),
        "agent_run_id": recommendation_payload.get("agent_run_id"),
        "prompt_version": recommendation_payload.get("prompt_version"),
        "decision_id": decision.get("decision_id"),
        "step_key": decision.get("step_key"),
        "evidence_basis": decision.get("evidence_basis"),
        "qualitative_rationale": rationale,
        "expected_value_band": decision.get("expected_value_band"),
        "risk_level": decision.get("risk_level"),
        "stop_reason": stop_reason,
        "verification_status": "pending",
        "verification_reason": None,
        "verification_summary": None,
        "verified_at_phase": None,
    }


def _accepted_guarded_chase_selection_action(
    *,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
    round_number: int,
    chase_candidates: tuple[ResearchOrchestratorChaseCandidate, ...],
    deterministic_selection: ResearchOrchestratorChaseSelection,
) -> JSONObject | None:
    decision, rationale = _guarded_recommendation_decision_payload(
        recommendation_payload=recommendation_payload,
    )
    if (
        decision is None
        or rationale is None
        or decision.get("source_key") is not None
        or (
            decision.get("action_type")
            != ResearchOrchestratorActionType.RUN_CHASE_ROUND.value
        )
        or (
            comparison.get("target_action_type")
            != ResearchOrchestratorActionType.RUN_CHASE_ROUND.value
        )
    ):
        return None
    action_input = decision.get("action_input")
    if not isinstance(action_input, dict):
        return None
    selected_entity_ids = _normalized_source_key_list(
        action_input.get("selected_entity_ids"),
    )
    selected_labels = _normalized_source_key_list(action_input.get("selected_labels"))
    selection_basis = action_input.get("selection_basis")
    if (
        not selected_entity_ids
        or not selected_labels
        or len(selected_entity_ids) != len(selected_labels)
        or not isinstance(selection_basis, str)
        or selection_basis == ""
    ):
        return None
    if len(set(selected_entity_ids)) != len(selected_entity_ids):
        return None
    candidate_map = {candidate.entity_id: candidate for candidate in chase_candidates}
    deterministic_entity_order = {
        entity_id: index
        for index, entity_id in enumerate(
            deterministic_selection.selected_entity_ids,
        )
    }
    deterministic_label_by_entity_id = dict(
        zip(
            deterministic_selection.selected_entity_ids,
            deterministic_selection.selected_labels,
            strict=True,
        )
    )
    invalid_selection = False
    previous_index = -1
    for entity_id, selected_label in zip(
        selected_entity_ids,
        selected_labels,
        strict=True,
    ):
        candidate = candidate_map.get(entity_id)
        deterministic_index = deterministic_entity_order.get(entity_id)
        deterministic_label = deterministic_label_by_entity_id.get(entity_id)
        if (
            candidate is None
            or candidate.display_label != selected_label
            or deterministic_index is None
            or deterministic_label != selected_label
            or deterministic_index <= previous_index
        ):
            invalid_selection = True
            break
        previous_index = deterministic_index
    if invalid_selection:
        return None
    deterministic_selected_entity_ids = list(
        deterministic_selection.selected_entity_ids
    )
    deterministic_selected_labels = list(deterministic_selection.selected_labels)
    return {
        "status": "applied",
        "checkpoint_key": comparison.get("checkpoint_key"),
        "applied_action_type": decision.get("action_type"),
        "applied_source_key": decision.get("source_key"),
        "guarded_strategy": _GUARDED_STRATEGY_CHASE_SELECTION,
        "round_number": round_number,
        "comparison_status": comparison.get("comparison_status"),
        "target_action_type": comparison.get("target_action_type"),
        "target_source_key": comparison.get("target_source_key"),
        "planner_status": recommendation_payload.get("planner_status"),
        "model_id": recommendation_payload.get("model_id"),
        "agent_run_id": recommendation_payload.get("agent_run_id"),
        "prompt_version": recommendation_payload.get("prompt_version"),
        "decision_id": decision.get("decision_id"),
        "step_key": decision.get("step_key"),
        "evidence_basis": decision.get("evidence_basis"),
        "qualitative_rationale": rationale,
        "expected_value_band": decision.get("expected_value_band"),
        "risk_level": decision.get("risk_level"),
        "selected_entity_ids": selected_entity_ids,
        "selected_labels": selected_labels,
        "selection_basis": selection_basis,
        "deterministic_selected_entity_ids": deterministic_selected_entity_ids,
        "deterministic_selected_labels": deterministic_selected_labels,
        "selection_scope": (
            "exact"
            if (
                selected_entity_ids == deterministic_selected_entity_ids
                and selected_labels == deterministic_selected_labels
            )
            else "subset"
        ),
        "verification_status": "pending",
        "verification_reason": None,
        "verification_summary": None,
        "verified_at_phase": None,
    }


def _accepted_guarded_structured_source_action(
    *,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
    available_source_keys: tuple[str, ...],
) -> JSONObject | None:
    decision, rationale = _guarded_recommendation_decision_payload(
        recommendation_payload=recommendation_payload,
    )
    if decision is None or rationale is None:
        return None
    if (
        decision.get("action_type")
        != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT.value
    ):
        return None
    source_key = decision.get("source_key")
    if not isinstance(source_key, str):
        return None
    if source_key not in available_source_keys:
        return None
    if (
        comparison.get("target_action_type")
        != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT.value
    ):
        return None
    return {
        "status": "applied",
        "checkpoint_key": comparison.get("checkpoint_key"),
        "applied_action_type": decision.get("action_type"),
        "applied_source_key": source_key,
        "guarded_strategy": _GUARDED_STRATEGY_STRUCTURED_SOURCE,
        "comparison_status": comparison.get("comparison_status"),
        "target_action_type": comparison.get("target_action_type"),
        "target_source_key": comparison.get("target_source_key"),
        "planner_status": recommendation_payload.get("planner_status"),
        "model_id": recommendation_payload.get("model_id"),
        "agent_run_id": recommendation_payload.get("agent_run_id"),
        "prompt_version": recommendation_payload.get("prompt_version"),
        "decision_id": decision.get("decision_id"),
        "step_key": decision.get("step_key"),
        "evidence_basis": decision.get("evidence_basis"),
        "qualitative_rationale": rationale,
        "expected_value_band": decision.get("expected_value_band"),
        "risk_level": decision.get("risk_level"),
        "verification_status": "pending",
        "verification_reason": None,
        "verification_summary": None,
        "verified_at_phase": None,
    }


__all__ = [
    "_accepted_guarded_chase_selection_action",
    "_accepted_guarded_control_flow_action",
    "_accepted_guarded_generate_brief_action",
    "_accepted_guarded_structured_source_action",
    "_guarded_recommendation_decision_payload",
    "_guarded_terminal_control_reason",
]
