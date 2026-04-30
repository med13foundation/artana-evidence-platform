"""Guarded rollout proof payload helpers."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    _STRUCTURED_ENRICHMENT_SOURCES,
)
from artana_evidence_api.phase1_compare_summaries import (
    _dict_value,
    build_guarded_evaluation,
    summarize_workspace,
)
from artana_evidence_api.types.common import JSONObject


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




__all__ = [
    "_available_structured_sources_from_workspace",
    "_checkpoint_workspace_summary",
    "_rollout_proof_summary",
]
