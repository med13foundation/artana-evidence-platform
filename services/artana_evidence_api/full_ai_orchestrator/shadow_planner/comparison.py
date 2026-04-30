"""Baseline comparison helpers for the full-AI shadow planner."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.shadow_planner.models import (
    ShadowPlannerRecommendationResult,
    _comparison_reason,
)
from artana_evidence_api.full_ai_orchestrator.shadow_planner.workspace import (
    _workspace_chase_selection,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseSelection,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.types.common import JSONObject


def _decision_chase_selection(
    *,
    decision: ResearchOrchestratorDecision,
) -> ResearchOrchestratorChaseSelection | None:
    if decision.action_type is ResearchOrchestratorActionType.RUN_CHASE_ROUND:
        selected_entity_ids = decision.action_input.get("selected_entity_ids")
        selected_labels = decision.action_input.get("selected_labels")
        selection_basis = decision.action_input.get("selection_basis")
        if (
            isinstance(selected_entity_ids, list)
            and isinstance(selected_labels, list)
            and isinstance(selection_basis, str)
        ):
            try:
                return ResearchOrchestratorChaseSelection(
                    selected_entity_ids=[
                        item for item in selected_entity_ids if isinstance(item, str)
                    ],
                    selected_labels=[
                        item for item in selected_labels if isinstance(item, str)
                    ],
                    stop_instead=decision.status == "skipped",
                    stop_reason=decision.stop_reason,
                    selection_basis=selection_basis,
                )
            except Exception:  # noqa: BLE001
                return None
    if decision.action_type is ResearchOrchestratorActionType.STOP:
        return ResearchOrchestratorChaseSelection(
            selected_entity_ids=[],
            selected_labels=[],
            stop_instead=True,
            stop_reason=decision.stop_reason,
            selection_basis=decision.evidence_basis,
        )
    return None


def _build_chase_selection_comparison(
    *,
    checkpoint_key: str,
    planner_result: ShadowPlannerRecommendationResult,
    deterministic_target: ResearchOrchestratorDecision,
    workspace_summary: JSONObject,
) -> JSONObject:
    target_selection = _workspace_chase_selection(
        workspace_summary=workspace_summary,
    ) or _decision_chase_selection(decision=deterministic_target)
    planner_selection = _decision_chase_selection(decision=planner_result.decision)
    deterministic_labels = (
        list(target_selection.selected_labels) if target_selection is not None else []
    )
    planner_labels = (
        list(planner_selection.selected_labels) if planner_selection is not None else []
    )
    deterministic_ids = (
        list(target_selection.selected_entity_ids)
        if target_selection is not None
        else []
    )
    planner_ids = (
        list(planner_selection.selected_entity_ids)
        if planner_selection is not None
        else []
    )
    deterministic_stop_expected = bool(
        target_selection is not None and target_selection.stop_instead,
    )
    planner_recommended_stop = (
        planner_result.decision.action_type is ResearchOrchestratorActionType.STOP
    )
    stop_match = (deterministic_stop_expected and planner_recommended_stop) or (
        not deterministic_stop_expected
        and planner_result.decision.action_type
        is ResearchOrchestratorActionType.RUN_CHASE_ROUND
    )
    chase_selection_available = (
        target_selection is not None
        and planner_selection is not None
        and not deterministic_stop_expected
        and (
            bool(target_selection.selected_entity_ids)
            or bool(planner_selection.selected_entity_ids)
        )
    )
    deterministic_only_labels = [
        label for label in deterministic_labels if label not in set(planner_labels)
    ]
    planner_only_labels = [
        label for label in planner_labels if label not in set(deterministic_labels)
    ]
    exact_selection_match = (
        chase_selection_available
        and not deterministic_stop_expected
        and planner_result.decision.action_type
        is ResearchOrchestratorActionType.RUN_CHASE_ROUND
        and planner_ids == deterministic_ids
        and planner_labels == deterministic_labels
    )
    selected_entity_overlap_count = len(set(deterministic_ids) & set(planner_ids))
    comparison_status = (
        "matched"
        if (deterministic_stop_expected and planner_recommended_stop)
        or exact_selection_match
        or (
            not chase_selection_available
            and planner_result.decision.action_type
            is ResearchOrchestratorActionType.RUN_CHASE_ROUND
            and deterministic_target.action_type
            is ResearchOrchestratorActionType.RUN_CHASE_ROUND
        )
        else "diverged"
    )
    return {
        "checkpoint_key": checkpoint_key,
        "deterministic_selected_entity_ids": deterministic_ids,
        "deterministic_selected_labels": deterministic_labels,
        "recommended_selected_entity_ids": planner_ids,
        "recommended_selected_labels": planner_labels,
        "deterministic_stop_expected": deterministic_stop_expected,
        "recommended_stop": planner_recommended_stop,
        "stop_match": stop_match,
        "chase_selection_available": chase_selection_available,
        "exact_selection_match": exact_selection_match,
        "selected_entity_overlap_count": selected_entity_overlap_count,
        "deterministic_only_labels": deterministic_only_labels,
        "planner_only_labels": planner_only_labels,
        "planner_conservative_stop": (
            planner_recommended_stop and not deterministic_stop_expected
        ),
        "planner_continued_when_threshold_stop": (
            not planner_recommended_stop and deterministic_stop_expected
        ),
        "comparison_status": comparison_status,
    }


def build_shadow_planner_comparison(
    *,
    checkpoint_key: str,
    planner_result: ShadowPlannerRecommendationResult,
    deterministic_target: ResearchOrchestratorDecision | None,
    workspace_summary: JSONObject | None = None,
    mode: str = "shadow",
) -> JSONObject:
    """Compare the planner recommendation against the deterministic baseline."""

    fallback_reason = planner_result.decision.fallback_reason
    qualitative_rationale = planner_result.decision.qualitative_rationale
    qualitative_rationale_present = bool(
        isinstance(qualitative_rationale, str) and qualitative_rationale.strip(),
    )
    budget_violation = fallback_reason == "budget_violation"
    if deterministic_target is None:
        return {
            "checkpoint_key": checkpoint_key,
            "mode": mode,
            "planner_status": planner_result.planner_status,
            "comparison_status": "no_target",
            "recommended_step_key": planner_result.decision.step_key,
            "recommended_action_type": planner_result.decision.action_type.value,
            "recommended_source_key": planner_result.decision.source_key,
            "used_fallback": planner_result.used_fallback,
            "fallback_reason": fallback_reason,
            "validation_error": planner_result.validation_error,
            "initial_validation_error": planner_result.initial_validation_error,
            "repair_attempted": planner_result.repair_attempted,
            "repair_succeeded": planner_result.repair_succeeded,
            "qualitative_rationale_present": qualitative_rationale_present,
            "budget_violation": budget_violation,
            "comparison_reason": "Deterministic run did not expose a comparable action.",
        }

    action_match = (
        planner_result.decision.action_type == deterministic_target.action_type
    )
    source_match = planner_result.decision.source_key == deterministic_target.source_key
    comparison: JSONObject = {
        "checkpoint_key": checkpoint_key,
        "mode": mode,
        "planner_status": planner_result.planner_status,
        "comparison_status": "matched" if action_match and source_match else "diverged",
        "target_step_key": deterministic_target.step_key,
        "target_action_type": deterministic_target.action_type.value,
        "target_source_key": deterministic_target.source_key,
        "recommended_step_key": planner_result.decision.step_key,
        "recommended_action_type": planner_result.decision.action_type.value,
        "recommended_source_key": planner_result.decision.source_key,
        "used_fallback": planner_result.used_fallback,
        "fallback_reason": fallback_reason,
        "validation_error": planner_result.validation_error,
        "initial_validation_error": planner_result.initial_validation_error,
        "repair_attempted": planner_result.repair_attempted,
        "repair_succeeded": planner_result.repair_succeeded,
        "qualitative_rationale_present": qualitative_rationale_present,
        "budget_violation": budget_violation,
        "action_match": action_match,
        "source_match": source_match,
        "comparison_reason": _comparison_reason(
            action_match=action_match,
            source_match=source_match,
        ),
    }
    if checkpoint_key in {"after_bootstrap", "after_chase_round_1"}:
        comparison.update(
            _build_chase_selection_comparison(
                checkpoint_key=checkpoint_key,
                planner_result=planner_result,
                deterministic_target=deterministic_target,
                workspace_summary=workspace_summary or {},
            ),
        )
    return comparison
