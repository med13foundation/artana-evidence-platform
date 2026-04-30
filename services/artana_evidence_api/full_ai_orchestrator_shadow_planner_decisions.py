"""Decision payload construction for the full-AI shadow planner."""

from __future__ import annotations

import json

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_models import (
    ShadowPlannerRecommendationOutput,
    ShadowPlannerTelemetry,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_telemetry import (
    _shadow_planner_telemetry_payload,
)
from artana_evidence_api.runtime_support import stable_sha256_digest
from artana_evidence_api.types.common import JSONObject


def _build_shadow_decision(
    *,
    output: ShadowPlannerRecommendationOutput,
    checkpoint_key: str,
    planner_status: str,
    model_id: str | None,
    agent_run_id: str,
    prompt_version: str,
    harness_id: str,
    step_key_version: str,
    initial_validation_error: str | None = None,
    repair_attempted: bool = False,
    repair_succeeded: bool = False,
    telemetry: ShadowPlannerTelemetry | None = None,
) -> ResearchOrchestratorDecision:
    step_key = _build_shadow_step_key(
        checkpoint_key=checkpoint_key,
        action_type=output.action_type,
        source_key=output.source_key,
        harness_id=harness_id,
        step_key_version=step_key_version,
    )
    payload = json.dumps(
        {
            "checkpoint_key": checkpoint_key,
            "action_type": output.action_type.value,
            "source_key": output.source_key,
            "step_key": step_key,
            "agent_run_id": agent_run_id,
        },
        sort_keys=True,
    )
    return ResearchOrchestratorDecision(
        decision_id=f"shadow-planner:{stable_sha256_digest(payload, length=24)}",
        round_number=0,
        action_type=output.action_type,
        action_input=_shadow_action_input(
            output=output,
            checkpoint_key=checkpoint_key,
            agent_run_id=agent_run_id,
        ),
        source_key=output.source_key,
        evidence_basis=output.evidence_basis,
        stop_reason=output.stop_reason,
        step_key=step_key,
        status="recommended",
        expected_value_band=output.expected_value_band,
        qualitative_rationale=output.qualitative_rationale,
        risk_level=output.risk_level,
        requires_approval=output.requires_approval,
        budget_estimate=output.budget_estimate,
        fallback_reason=output.fallback_reason,
        metadata={
            "checkpoint_key": checkpoint_key,
            "planner_status": planner_status,
            "model_id": model_id,
            "agent_run_id": agent_run_id,
            "prompt_version": prompt_version,
            "initial_validation_error": initial_validation_error,
            "repair_attempted": repair_attempted,
            "repair_succeeded": repair_succeeded,
            "telemetry": _shadow_planner_telemetry_payload(telemetry),
        },
    )


def _shadow_action_input(
    *,
    output: ShadowPlannerRecommendationOutput,
    checkpoint_key: str,
    agent_run_id: str,
) -> JSONObject:
    action_input: JSONObject = {
        "mode": "shadow",
        "checkpoint_key": checkpoint_key,
        "agent_run_id": agent_run_id,
    }
    if output.action_type is ResearchOrchestratorActionType.RUN_CHASE_ROUND:
        action_input["selected_entity_ids"] = list(output.selected_entity_ids)
        action_input["selected_labels"] = list(output.selected_labels)
        if output.selection_basis is not None:
            action_input["selection_basis"] = output.selection_basis
    return action_input


def _build_shadow_step_key(
    *,
    checkpoint_key: str,
    action_type: ResearchOrchestratorActionType,
    source_key: str | None,
    harness_id: str,
    step_key_version: str,
) -> str:
    source_segment = source_key if source_key is not None else "control"
    return (
        f"{harness_id}.{step_key_version}.shadow.{checkpoint_key}."
        f"{source_segment}.{action_type.value.casefold()}"
    )


def _build_agent_run_id(
    *,
    objective: str,
    checkpoint_key: str,
    workspace_summary: JSONObject,
) -> str:
    digest = stable_sha256_digest(
        json.dumps(
            {
                "objective": objective,
                "checkpoint_key": checkpoint_key,
                "workspace_summary": workspace_summary,
            },
            sort_keys=True,
            default=str,
        ),
        length=24,
    )
    return f"full-ai-shadow-planner:{digest}"

