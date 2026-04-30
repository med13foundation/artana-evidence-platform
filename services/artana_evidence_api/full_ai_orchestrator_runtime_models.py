"""Result models for the full-AI orchestrator runtime."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.research_init_runtime import ResearchInitExecutionResult
from artana_evidence_api.run_registry import HarnessRunRecord
from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True, slots=True)
class FullAIOrchestratorExecutionResult:
    """Terminal result for one deterministic full AI orchestrator run."""

    run: HarnessRunRecord
    planner_mode: FullAIOrchestratorPlannerMode
    guarded_rollout_profile: str | None
    guarded_rollout_profile_source: str | None
    research_init_result: ResearchInitExecutionResult
    action_history: tuple[ResearchOrchestratorDecision, ...]
    workspace_summary: JSONObject
    source_execution_summary: JSONObject
    bootstrap_summary: JSONObject | None
    brief_metadata: JSONObject
    shadow_planner: JSONObject | None
    guarded_execution: JSONObject | None
    guarded_decision_proofs: JSONObject | None
    errors: list[str]
















