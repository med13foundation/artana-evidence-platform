"""Shadow planner timeline assembly."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _HARNESS_ID,
    _SHADOW_PLANNER_CHECKPOINT_ORDER,
    _STEP_KEY_VERSION,
)
from artana_evidence_api.full_ai_orchestrator.shadow.decisions import (
    _checkpoint_phase_record_map,
    _checkpoint_target_decision,
)
from artana_evidence_api.full_ai_orchestrator.shadow.summary import (
    _shadow_planner_recommendation_payload,
)
from artana_evidence_api.full_ai_orchestrator.shadow_planner import (
    build_shadow_planner_comparison,
    build_shadow_planner_workspace_summary,
    recommend_shadow_planner_action,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_array_or_empty,
    json_object,
)


async def _build_shadow_planner_timeline(  # noqa: PLR0913
    *,
    objective: str,
    seed_terms: list[str],
    sources: ResearchSpaceSourcePreferences,
    max_depth: int,
    max_hypotheses: int,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
    initial_workspace_summary: JSONObject,
    initial_decisions: list[ResearchOrchestratorDecision],
    phase_records: dict[str, list[JSONObject]],
    final_workspace_snapshot: JSONObject,
    final_decisions: list[ResearchOrchestratorDecision],
) -> list[JSONObject]:
    checkpoint_records = _checkpoint_phase_record_map(
        initial_workspace_summary=initial_workspace_summary,
        initial_decisions=initial_decisions,
        phase_records=phase_records,
        final_workspace_snapshot=final_workspace_snapshot,
        final_decisions=final_decisions,
    )
    timeline: list[JSONObject] = []
    for checkpoint_key in _SHADOW_PLANNER_CHECKPOINT_ORDER:
        record = checkpoint_records.get(checkpoint_key)
        if not isinstance(record, dict):
            continue
        record_workspace = record.get("workspace_summary")
        if isinstance(record_workspace, dict):
            workspace_summary = record_workspace
        else:
            workspace_snapshot = record.get("workspace_snapshot")
            workspace_summary = build_shadow_planner_workspace_summary(
                checkpoint_key=checkpoint_key,
                objective=objective,
                seed_terms=seed_terms,
                sources=sources,
                max_depth=max_depth,
                max_hypotheses=max_hypotheses,
                workspace_snapshot=(
                    workspace_snapshot if isinstance(workspace_snapshot, dict) else {}
                ),
                prior_decisions=[
                    decision_payload
                    for item in json_array_or_empty(record.get("decisions"))
                    if (decision_payload := json_object(item)) is not None
                ],
                action_registry=action_registry,
            )
        planner_result = await recommend_shadow_planner_action(
            checkpoint_key=checkpoint_key,
            objective=objective,
            workspace_summary=workspace_summary,
            sources=sources,
            action_registry=action_registry,
            harness_id=_HARNESS_ID,
            step_key_version=_STEP_KEY_VERSION,
        )
        comparison = build_shadow_planner_comparison(
            checkpoint_key=checkpoint_key,
            planner_result=planner_result,
            deterministic_target=_checkpoint_target_decision(
                checkpoint_key=checkpoint_key,
                decisions=final_decisions,
                workspace_summary=workspace_summary,
            ),
            workspace_summary=workspace_summary,
        )
        timeline.append(
            {
                "checkpoint_key": checkpoint_key,
                "workspace_summary": workspace_summary,
                "recommendation": _shadow_planner_recommendation_payload(
                    planner_result=planner_result,
                    mode="shadow",
                ),
                "comparison": comparison,
            }
        )
    return timeline


__all__ = ["_build_shadow_planner_timeline"]
