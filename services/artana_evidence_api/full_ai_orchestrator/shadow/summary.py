"""Shadow planner summary and telemetry helpers."""

from __future__ import annotations

from typing import cast

from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
    _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
    _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
    _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
)
from artana_evidence_api.full_ai_orchestrator.shadow_planner import (
    ShadowPlannerRecommendationResult,
)
from artana_evidence_api.types.common import JSONObject


def _build_shadow_planner_summary(  # noqa: PLR0912, PLR0915
    *,
    timeline: list[JSONObject],
    mode: str,
) -> JSONObject:
    latest_entry = timeline[-1] if timeline else {}
    latest_workspace_summary = (
        latest_entry.get("workspace_summary")
        if isinstance(latest_entry.get("workspace_summary"), dict)
        else {}
    )
    latest_recommendation = (
        latest_entry.get("recommendation")
        if isinstance(latest_entry.get("recommendation"), dict)
        else {}
    )
    latest_comparison = (
        latest_entry.get("comparison")
        if isinstance(latest_entry.get("comparison"), dict)
        else {}
    )
    action_matches = 0
    source_matches = 0
    planner_failures = 0
    invalid_recommendations = 0
    disabled_source_violations = 0
    budget_violations = 0
    fallback_recommendations = 0
    qualitative_rationale_present_count = 0
    telemetry_available_checkpoints = 0
    cost_available_checkpoints = 0
    token_available_checkpoints = 0
    latency_available_checkpoints = 0
    planner_total_prompt_tokens = 0
    planner_total_completion_tokens = 0
    planner_total_cost_usd = 0.0
    planner_total_latency_seconds = 0.0
    for entry in timeline:
        comparison = entry.get("comparison")
        if isinstance(comparison, dict):
            if comparison.get("action_match") is True:
                action_matches += 1
            if comparison.get("source_match") is True:
                source_matches += 1
            if comparison.get("budget_violation") is True:
                budget_violations += 1
            if comparison.get("qualitative_rationale_present") is True:
                qualitative_rationale_present_count += 1
        recommendation = entry.get("recommendation")
        if isinstance(recommendation, dict):
            planner_status = recommendation.get("planner_status")
            if planner_status in {"failed", "invalid"}:
                planner_failures += 1
            if recommendation.get("used_fallback") is True:
                fallback_recommendations += 1
            decision = recommendation.get("decision")
            if (
                isinstance(decision, dict)
                and decision.get("fallback_reason") is not None
            ):
                invalid_recommendations += 1
                if decision.get("fallback_reason") == "source_disabled":
                    disabled_source_violations += 1
            telemetry = _shadow_planner_telemetry_from_recommendation(recommendation)
            if telemetry.get("status") in {"available", "partial"}:
                telemetry_available_checkpoints += 1
            prompt_tokens = _optional_int(telemetry.get("prompt_tokens"))
            completion_tokens = _optional_int(telemetry.get("completion_tokens"))
            cost_usd = _optional_float(telemetry.get("cost_usd"))
            latency_seconds = _optional_float(telemetry.get("latency_seconds"))
            if prompt_tokens is not None and completion_tokens is not None:
                token_available_checkpoints += 1
                planner_total_prompt_tokens += prompt_tokens
                planner_total_completion_tokens += completion_tokens
            if cost_usd is not None:
                cost_available_checkpoints += 1
                planner_total_cost_usd += cost_usd
            if latency_seconds is not None:
                latency_available_checkpoints += 1
                planner_total_latency_seconds += latency_seconds
    planner_total_tokens = None
    if token_available_checkpoints > 0:
        planner_total_tokens = (
            planner_total_prompt_tokens + planner_total_completion_tokens
        )
    cost_tracking = _build_shadow_planner_cost_tracking(
        total_checkpoints=len(timeline),
        telemetry_available_checkpoints=telemetry_available_checkpoints,
        cost_available_checkpoints=cost_available_checkpoints,
        token_available_checkpoints=token_available_checkpoints,
        latency_available_checkpoints=latency_available_checkpoints,
        planner_total_prompt_tokens=(
            planner_total_prompt_tokens if token_available_checkpoints > 0 else None
        ),
        planner_total_completion_tokens=(
            planner_total_completion_tokens if token_available_checkpoints > 0 else None
        ),
        planner_total_tokens=planner_total_tokens,
        planner_total_cost_usd=(
            round(planner_total_cost_usd, 8) if cost_available_checkpoints > 0 else None
        ),
        planner_total_latency_seconds=(
            round(planner_total_latency_seconds, 6)
            if latency_available_checkpoints > 0
            else None
        ),
    )
    return {
        "mode": mode,
        "workspace_key": _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
        "recommendation_key": _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
        "comparison_key": _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
        "timeline_key": _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
        "timeline": timeline,
        "summary": {
            "checkpoint_count": len(timeline),
            "action_match_count": action_matches,
            "source_match_count": source_matches,
            "planner_failure_count": planner_failures,
            "invalid_recommendation_count": invalid_recommendations,
            "fallback_recommendation_count": fallback_recommendations,
            "qualitative_rationale_present_count": (
                qualitative_rationale_present_count
            ),
            "telemetry_available_checkpoints": telemetry_available_checkpoints,
            "cost_available_checkpoints": cost_available_checkpoints,
            "planner_total_cost_usd": cost_tracking.get("planner_total_cost_usd"),
            "latest_checkpoint_key": latest_entry.get("checkpoint_key"),
        },
        "evaluation": {
            "total_checkpoints": len(timeline),
            "action_matches": action_matches,
            "source_matches": source_matches,
            "planner_failures": planner_failures,
            "invalid_recommendations": invalid_recommendations,
            "disabled_source_violations": disabled_source_violations,
            "budget_violations": budget_violations,
            "fallback_recommendations": fallback_recommendations,
            "qualitative_rationale_present_count": (
                qualitative_rationale_present_count
            ),
            "telemetry_available_checkpoints": telemetry_available_checkpoints,
            "cost_available_checkpoints": cost_available_checkpoints,
            "token_available_checkpoints": token_available_checkpoints,
            "latency_available_checkpoints": latency_available_checkpoints,
            "planner_total_prompt_tokens": (
                cost_tracking.get("planner_total_prompt_tokens")
            ),
            "planner_total_completion_tokens": (
                cost_tracking.get("planner_total_completion_tokens")
            ),
            "planner_total_tokens": cost_tracking.get("planner_total_tokens"),
            "planner_total_cost_usd": cost_tracking.get("planner_total_cost_usd"),
            "planner_total_latency_seconds": (
                cost_tracking.get("planner_total_latency_seconds")
            ),
        },
        "cost_tracking": cost_tracking,
        "latest_workspace_summary": latest_workspace_summary,
        "latest_recommendation": latest_recommendation,
        "latest_comparison": latest_comparison,
    }


def _shadow_planner_recommendation_payload(
    *,
    planner_result: object,
    mode: str,
) -> JSONObject:
    typed_planner_result = cast("ShadowPlannerRecommendationResult", planner_result)
    decision = typed_planner_result.decision
    return {
        "mode": mode,
        "planner_status": typed_planner_result.planner_status,
        "used_fallback": typed_planner_result.used_fallback,
        "model_id": typed_planner_result.model_id,
        "agent_run_id": typed_planner_result.agent_run_id,
        "prompt_version": typed_planner_result.prompt_version,
        "validation_error": typed_planner_result.validation_error,
        "error": typed_planner_result.error,
        "telemetry": _shadow_planner_telemetry_payload(
            getattr(planner_result, "telemetry", None),
        ),
        "decision": decision.model_dump(mode="json"),
    }


def _shadow_planner_telemetry_payload(telemetry: object) -> JSONObject:
    if telemetry is None:
        return {
            "status": "unavailable",
            "model_terminal_count": 0,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cost_usd": None,
            "latency_seconds": None,
            "tool_call_count": 0,
        }
    return {
        "status": getattr(telemetry, "status", "unavailable"),
        "model_terminal_count": getattr(telemetry, "model_terminal_count", 0),
        "prompt_tokens": getattr(telemetry, "prompt_tokens", None),
        "completion_tokens": getattr(telemetry, "completion_tokens", None),
        "total_tokens": getattr(telemetry, "total_tokens", None),
        "cost_usd": getattr(telemetry, "cost_usd", None),
        "latency_seconds": getattr(telemetry, "latency_seconds", None),
        "tool_call_count": getattr(telemetry, "tool_call_count", 0),
    }


def _shadow_planner_telemetry_from_recommendation(
    recommendation: JSONObject,
) -> JSONObject:
    telemetry = recommendation.get("telemetry")
    return dict(telemetry) if isinstance(telemetry, dict) else {}


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, int):
        return float(value)
    return value if isinstance(value, float) else None


def _build_shadow_planner_cost_tracking(  # noqa: PLR0913
    *,
    total_checkpoints: int,
    telemetry_available_checkpoints: int,
    cost_available_checkpoints: int,
    token_available_checkpoints: int,
    latency_available_checkpoints: int,
    planner_total_prompt_tokens: int | None,
    planner_total_completion_tokens: int | None,
    planner_total_tokens: int | None,
    planner_total_cost_usd: float | None,
    planner_total_latency_seconds: float | None,
) -> JSONObject:
    status = "unavailable"
    if (
        total_checkpoints > 0
        and cost_available_checkpoints == total_checkpoints
        and token_available_checkpoints == total_checkpoints
        and latency_available_checkpoints == total_checkpoints
    ):
        status = "available"
    elif (
        telemetry_available_checkpoints > 0
        or cost_available_checkpoints > 0
        or token_available_checkpoints > 0
        or latency_available_checkpoints > 0
    ):
        status = "partial"
    return {
        "status": status,
        "total_checkpoints": total_checkpoints,
        "telemetry_available_checkpoints": telemetry_available_checkpoints,
        "cost_available_checkpoints": cost_available_checkpoints,
        "token_available_checkpoints": token_available_checkpoints,
        "latency_available_checkpoints": latency_available_checkpoints,
        "planner_total_prompt_tokens": planner_total_prompt_tokens,
        "planner_total_completion_tokens": planner_total_completion_tokens,
        "planner_total_tokens": planner_total_tokens,
        "planner_total_cost_usd": planner_total_cost_usd,
        "planner_total_latency_seconds": planner_total_latency_seconds,
    }


__all__ = [
    "_build_shadow_planner_cost_tracking",
    "_build_shadow_planner_summary",
    "_optional_float",
    "_optional_int",
    "_shadow_planner_recommendation_payload",
    "_shadow_planner_telemetry_from_recommendation",
    "_shadow_planner_telemetry_payload",
]
