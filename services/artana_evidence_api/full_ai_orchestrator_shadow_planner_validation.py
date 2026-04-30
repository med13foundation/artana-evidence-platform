"""Output validation for the full-AI shadow planner."""

from __future__ import annotations

from typing import Literal, cast

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseCandidate,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_models import (
    _CONFIDENCE_SCORE_PATTERN,
    _MAX_CHASE_SELECTION_ENTITIES,
    _PERCENT_PATTERN,
    _RANKING_NUMBER_PATTERN,
    ShadowPlannerRecommendationOutput,
    _default_stop_reason,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_workspace import (
    _chase_decision_posture_value,
    _checkpoint_live_action_specs,
    _workspace_chase_candidate_map,
    _workspace_planner_constraints,
    _workspace_structured_enrichment_source_keys,
    planner_live_action_types,
)
from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences
from pydantic import BaseModel, create_model


def validate_shadow_planner_output(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject | None = None,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> str | None:
    """Return a validation error when the planner output is not acceptable."""

    action_spec = next(
        (spec for spec in action_registry if spec.action_type == output.action_type),
        None,
    )
    live_types = planner_live_action_types(action_registry=action_registry)
    validations = (
        _validate_allowlisted_action(
            action_spec=action_spec,
            output=output,
            live_types=live_types,
        ),
        _validate_action_source(
            action_spec=action_spec,
            output=output,
            sources=sources,
        ),
        _validate_checkpoint_stage_semantics(
            output=output,
            workspace_summary=workspace_summary or {},
        ),
        _validate_chase_selection(
            output=output,
            workspace_summary=workspace_summary or {},
        ),
        _validate_stop_reason(output=output),
        _validate_qualitative_rationale(output=output),
    )
    for error in validations:
        if error is not None:
            return error
    return None


def _build_shadow_planner_output_schema(
    *,
    checkpoint_key: str,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> type[BaseModel]:
    live_action_types = tuple(
        spec.action_type
        for spec in _checkpoint_live_action_specs(
            checkpoint_key=checkpoint_key,
            action_registry=action_registry,
        )
    )
    if not live_action_types:
        return ShadowPlannerRecommendationOutput
    action_literal = Literal.__getitem__(live_action_types)
    return cast(
        "type[BaseModel]",
        create_model(
            "ShadowPlannerLiveRecommendationOutput",
            __base__=ShadowPlannerRecommendationOutput,
            action_type=(action_literal, ...),
        ),
    )


def _coerce_shadow_planner_output(output: object) -> ShadowPlannerRecommendationOutput:
    if isinstance(output, BaseModel):
        return ShadowPlannerRecommendationOutput.model_validate(
            output.model_dump(mode="python"),
        )
    return ShadowPlannerRecommendationOutput.model_validate(output)


def _normalize_shadow_planner_output(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> ShadowPlannerRecommendationOutput:
    action_spec = next(
        (spec for spec in action_registry if spec.action_type == output.action_type),
        None,
    )
    if action_spec is None:
        return output

    updates: JSONObject = {}
    if (
        output.source_key is None
        and action_spec.default_source_key is not None
        and sources.get(action_spec.default_source_key, False)
    ):
        updates["source_key"] = action_spec.default_source_key

    if (
        output.action_type is ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT
        and output.source_key is None
    ):
        structured_sources = _workspace_structured_enrichment_source_keys(
            workspace_summary=workspace_summary,
        )
        if len(structured_sources) == 1 and sources.get(structured_sources[0], False):
            updates["source_key"] = structured_sources[0]

    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        else ""
    )
    if output.action_type in {
        ResearchOrchestratorActionType.STOP,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
    } and (output.stop_reason is None or output.stop_reason.strip() == ""):
        updates["stop_reason"] = _default_stop_reason(
            action_type=output.action_type,
            checkpoint_key=checkpoint_key,
        )

    if not updates:
        return output
    return output.model_copy(update=updates)


def _contains_forbidden_numeric_style(text: str) -> bool:
    normalized = text.strip()
    if normalized == "":
        return False
    return any(
        pattern.search(normalized) is not None
        for pattern in (
            _PERCENT_PATTERN,
            _CONFIDENCE_SCORE_PATTERN,
            _RANKING_NUMBER_PATTERN,
        )
    )


def _validate_allowlisted_action(
    *,
    action_spec: ResearchOrchestratorActionSpec | None,
    output: ShadowPlannerRecommendationOutput,
    live_types: frozenset[ResearchOrchestratorActionType],
) -> str | None:
    if action_spec is None:
        return "action_not_allowlisted"
    if output.action_type not in live_types:
        return "action_not_live"
    return None


def _validate_action_source(
    *,
    action_spec: ResearchOrchestratorActionSpec | None,
    output: ShadowPlannerRecommendationOutput,
    sources: ResearchSpaceSourcePreferences,
) -> str | None:
    if action_spec is None:
        return None
    if action_spec.source_bound and output.source_key is None:
        return "source_key_required"
    if not action_spec.source_bound and output.source_key is not None:
        return "source_key_not_allowed"
    if (
        action_spec.default_source_key is not None
        and output.source_key is not None
        and output.source_key != action_spec.default_source_key
    ):
        return "unexpected_source_key"
    if output.source_key is not None and not sources.get(output.source_key, False):
        return "source_disabled"
    return None


def _validate_checkpoint_stage_semantics(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject,
) -> str | None:
    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        and str(workspace_summary.get("checkpoint_key")).strip()
        else None
    )
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    if (
        checkpoint_key == "after_pubmed_discovery"
        and planner_constraints["pubmed_ingest_pending"]
        and output.action_type
        is not ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED
    ):
        return "pubmed_ingest_required"
    if checkpoint_key == "before_terminal_stop" and output.action_type not in {
        ResearchOrchestratorActionType.STOP,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
    }:
        return "terminal_stop_required"
    return None


def _validate_stop_reason(
    *,
    output: ShadowPlannerRecommendationOutput,
) -> str | None:
    if output.action_type not in {
        ResearchOrchestratorActionType.STOP,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
    }:
        return None
    if output.stop_reason is None or output.stop_reason.strip() == "":
        return "stop_reason_required"
    return None


def _validate_chase_selection(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject,
) -> str | None:
    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        else ""
    )
    if checkpoint_key not in {"after_bootstrap", "after_chase_round_1"}:
        return None
    if output.action_type not in {
        ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        ResearchOrchestratorActionType.STOP,
    }:
        return "chase_checkpoint_action_not_allowed"
    if output.action_type is ResearchOrchestratorActionType.STOP:
        if (
            _chase_decision_posture_value(workspace_summary=workspace_summary)
            == "continue_objective_relevant"
        ):
            return "objective_relevant_chase_required"
        return (
            None
            if output.stop_reason is not None and output.stop_reason.strip() != ""
            else "stop_reason_required"
        )
    if output.action_type is not ResearchOrchestratorActionType.RUN_CHASE_ROUND:
        return None
    return _validate_run_chase_round_selection(
        output=output,
        workspace_summary=workspace_summary,
    )


def _validate_run_chase_round_selection(
    *,
    output: ShadowPlannerRecommendationOutput,
    workspace_summary: JSONObject,
) -> str | None:
    shape_error = _validate_run_chase_round_selection_shape(output=output)
    if shape_error is not None:
        return shape_error

    candidate_map = _workspace_chase_candidate_map(workspace_summary=workspace_summary)
    if not candidate_map:
        return "chase_selection_unknown_entity"
    return _validate_run_chase_round_selection_membership(
        output=output,
        candidate_map=candidate_map,
    )


def _validate_run_chase_round_selection_shape(
    *,
    output: ShadowPlannerRecommendationOutput,
) -> str | None:
    if (
        not output.selected_entity_ids
        or not output.selected_labels
        or output.selection_basis is None
        or output.selection_basis.strip() == ""
    ):
        return "chase_selection_required"
    if (
        len(output.selected_entity_ids) > _MAX_CHASE_SELECTION_ENTITIES
        or len(output.selected_labels) > _MAX_CHASE_SELECTION_ENTITIES
    ):
        return "chase_selection_too_large"
    if len(output.selected_entity_ids) != len(output.selected_labels):
        return "chase_selection_label_mismatch"
    return None


def _validate_run_chase_round_selection_membership(
    *,
    output: ShadowPlannerRecommendationOutput,
    candidate_map: dict[str, ResearchOrchestratorChaseCandidate],
) -> str | None:
    for entity_id, selected_label in zip(
        output.selected_entity_ids,
        output.selected_labels,
        strict=True,
    ):
        candidate = candidate_map.get(entity_id)
        if candidate is None:
            return "chase_selection_unknown_entity"
        if candidate.display_label != selected_label:
            return "chase_selection_label_mismatch"
    return None


def _validate_qualitative_rationale(
    *,
    output: ShadowPlannerRecommendationOutput,
) -> str | None:
    if output.qualitative_rationale.strip() == "":
        return "qualitative_rationale_missing"
    if _contains_forbidden_numeric_style(output.qualitative_rationale):
        return "numeric_style_ranking_not_allowed"
    return None

