"""HTTP response serialization for full-AI orchestrator runs."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
    FullAIOrchestratorRunResponse,
)
from artana_evidence_api.full_ai_orchestrator_runtime_models import (
    FullAIOrchestratorExecutionResult,
)
from artana_evidence_api.response_serialization import serialize_run_record


def build_full_ai_orchestrator_run_response(
    result: FullAIOrchestratorExecutionResult,
) -> FullAIOrchestratorRunResponse:
    """Serialize one completed orchestrator run for HTTP responses."""
    return FullAIOrchestratorRunResponse(
        planner_mode=result.planner_mode,
        guarded_rollout_profile=_guarded_rollout_profile_response_value(
            result.guarded_rollout_profile,
        ),
        run=serialize_run_record(run=result.run),
        action_history=list(result.action_history),
        workspace_summary=result.workspace_summary,
        source_execution_summary=result.source_execution_summary,
        bootstrap_summary=result.bootstrap_summary,
        brief_metadata=result.brief_metadata,
        shadow_planner=result.shadow_planner,
        guarded_execution=result.guarded_execution,
        guarded_decision_proofs=result.guarded_decision_proofs,
        errors=list(result.errors),
    )


def _guarded_rollout_profile_response_value(
    value: str | None,
) -> FullAIOrchestratorGuardedRolloutProfile | None:
    if value is None:
        return None
    try:
        return FullAIOrchestratorGuardedRolloutProfile(value)
    except ValueError:
        return None


