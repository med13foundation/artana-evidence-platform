"""Workspace and verification helpers for the full-AI orchestrator."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _GUARDED_STRATEGY_STRUCTURED_SOURCE,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorChaseSelection,
)
from artana_evidence_api.types.common import JSONObject, JSONValue
from pydantic import ValidationError


def _planner_mode_value(mode: FullAIOrchestratorPlannerMode | str) -> str:
    return mode.value if isinstance(mode, FullAIOrchestratorPlannerMode) else str(mode)


def _workspace_list(
    workspace_snapshot: JSONObject,
    key: str,
) -> list[JSONValue]:
    value = workspace_snapshot.get(key)
    return list(value) if isinstance(value, list) else []


def _workspace_object(
    workspace_snapshot: JSONObject,
    key: str,
) -> JSONObject:
    value = workspace_snapshot.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _normalized_source_key_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _pending_chase_round_summary(workspace_snapshot: JSONObject) -> JSONObject:
    pending = workspace_snapshot.get("pending_chase_round")
    return dict(pending) if isinstance(pending, dict) else {}


def _chase_selection_from_summary(
    *,
    summary: JSONObject,
) -> ResearchOrchestratorChaseSelection | None:
    for selection_key in (
        "effective_selection",
        "guarded_selection",
        "deterministic_selection",
    ):
        selection = summary.get(selection_key)
        if not isinstance(selection, dict):
            continue
        try:
            return ResearchOrchestratorChaseSelection.model_validate(selection)
        except ValidationError:
            continue
    return None


def _chase_round_action_input_from_workspace(
    *,
    workspace_snapshot: JSONObject,
    round_number: int,
) -> JSONObject:
    chase_summary = workspace_snapshot.get(f"chase_round_{round_number}")
    if isinstance(chase_summary, dict):
        return {
            "round_number": round_number,
            "selected_entity_ids": _normalized_source_key_list(
                chase_summary.get("selected_entity_ids"),
            ),
            "selected_labels": _normalized_source_key_list(
                chase_summary.get("selected_labels"),
            ),
            "selection_basis": (
                str(chase_summary.get("selection_basis"))
                if isinstance(chase_summary.get("selection_basis"), str)
                else "Deterministic chase-round selection."
            ),
        }
    pending_summary = _pending_chase_round_summary(workspace_snapshot)
    if pending_summary.get("round_number") != round_number:
        return {"round_number": round_number}
    selection = _chase_selection_from_summary(summary=pending_summary)
    if selection is None:
        return {"round_number": round_number}
    return {
        "round_number": round_number,
        "selected_entity_ids": list(selection.selected_entity_ids),
        "selected_labels": list(selection.selected_labels),
        "selection_basis": selection.selection_basis,
    }


def _chase_round_metadata_from_workspace(
    *,
    workspace_snapshot: JSONObject,
    round_number: int,
) -> JSONObject:
    chase_summary = workspace_snapshot.get(f"chase_round_{round_number}")
    if isinstance(chase_summary, dict):
        return dict(chase_summary)
    pending_summary = _pending_chase_round_summary(workspace_snapshot)
    if pending_summary.get("round_number") != round_number:
        return {}
    return dict(pending_summary)


def _chase_round_stop_reason(metadata: JSONObject) -> str:
    selection = _chase_selection_from_summary(summary=metadata)
    if selection is not None and selection.stop_reason:
        return selection.stop_reason
    return "threshold_not_met"


def _source_status(source_results: JSONObject, source_key: str) -> str | None:
    source_summary = source_results.get(source_key)
    if not isinstance(source_summary, dict):
        return None
    status = source_summary.get("status")
    return status if isinstance(status, str) else None


def _guarded_structured_verification_payload(
    *,
    source_results: JSONObject,
    action: JSONObject,
) -> tuple[str, str, JSONObject]:
    guarded_strategy = action.get("guarded_strategy")
    selected_source_key = action.get("applied_source_key")
    if not isinstance(selected_source_key, str):
        return (
            "verification_failed",
            "selected_source_missing",
            {
                "selected_source_key": selected_source_key,
                "source_results_present": bool(source_results),
            },
        )

    ordered_keys = _normalized_source_key_list(action.get("ordered_source_keys"))
    deferred_keys = _normalized_source_key_list(action.get("deferred_source_keys"))
    selected_source_status = _source_status(source_results, selected_source_key)
    ordered_source_statuses = {
        source_key: _source_status(source_results, source_key)
        for source_key in ordered_keys
    }
    deferred_source_statuses = {
        source_key: _source_status(source_results, source_key)
        for source_key in deferred_keys
    }
    incomplete_ordered_sources: list[JSONObject] = []
    unexpected_deferred_sources: list[JSONObject] = []

    if guarded_strategy == _GUARDED_STRATEGY_STRUCTURED_SOURCE:
        for source_key, ordered_status in ordered_source_statuses.items():
            if ordered_status not in {"completed", "failed"}:
                incomplete_ordered_sources.append(
                    {"source_key": source_key, "status": ordered_status},
                )
            source_summary = source_results.get(source_key)
            if (
                isinstance(source_summary, dict)
                and source_summary.get("deferred_reason") == "guarded_source_selection"
            ):
                unexpected_deferred_sources.append(
                    {"source_key": source_key, "status": ordered_status},
                )
    else:
        for source_key, deferred_status in deferred_source_statuses.items():
            if deferred_status not in {"deferred", "skipped"}:
                incomplete_ordered_sources.append(
                    {"source_key": source_key, "status": deferred_status},
                )

    verification_status, verification_reason = _guarded_structured_verification_outcome(
        guarded_strategy=guarded_strategy,
        selected_source_status=selected_source_status,
        incomplete_ordered_sources=incomplete_ordered_sources,
        unexpected_deferred_sources=unexpected_deferred_sources,
    )

    return (
        verification_status,
        verification_reason,
        {
            "guarded_strategy": guarded_strategy,
            "ordered_source_keys": ordered_keys,
            "ordered_source_statuses": ordered_source_statuses,
            "selected_source_key": selected_source_key,
            "selected_source_status": selected_source_status,
            "deferred_source_statuses": deferred_source_statuses,
            "incomplete_ordered_sources": incomplete_ordered_sources,
            "unexpected_deferred_sources": unexpected_deferred_sources,
        },
    )


def _guarded_structured_verification_outcome(
    *,
    guarded_strategy: object,
    selected_source_status: str | None,
    incomplete_ordered_sources: list[JSONObject],
    unexpected_deferred_sources: list[JSONObject],
) -> tuple[str, str]:
    if selected_source_status not in {"completed", "failed"}:
        return "verification_failed", "selected_source_not_completed"
    if guarded_strategy == _GUARDED_STRATEGY_STRUCTURED_SOURCE:
        if incomplete_ordered_sources:
            return "verification_failed", "ordered_sources_not_completed"
        if unexpected_deferred_sources:
            return "verification_failed", "ordered_sources_deferred"
        return "verified", "ordered_sources_completed"
    if incomplete_ordered_sources:
        return "verification_failed", "deferred_sources_executed"
    return "verified", "selected_source_completed"


def _source_decision_status(
    *,
    source_summary: JSONObject,
    pending_status: str,
) -> tuple[str, str | None]:
    source_status = source_summary.get("status")
    if source_status == "completed":
        return "completed", None
    if source_status == "failed":
        return "failed", "source_failed"
    if source_status == "pending":
        return pending_status, None
    if source_status == "deferred":
        deferred_reason = source_summary.get("deferred_reason")
        if deferred_reason == "guarded_source_selection":
            return "skipped", "guarded_source_deferred"
        return "skipped", "source_deferred"
    return "skipped", "source_not_executed"


__all__ = [
    "_chase_round_action_input_from_workspace",
    "_chase_round_metadata_from_workspace",
    "_chase_round_stop_reason",
    "_chase_selection_from_summary",
    "_guarded_structured_verification_outcome",
    "_guarded_structured_verification_payload",
    "_normalized_source_key_list",
    "_pending_chase_round_summary",
    "_planner_mode_value",
    "_source_decision_status",
    "_source_status",
    "_workspace_list",
    "_workspace_object",
]
