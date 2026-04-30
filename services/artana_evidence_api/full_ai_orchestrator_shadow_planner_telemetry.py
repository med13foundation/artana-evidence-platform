"""Telemetry collection for the full-AI shadow planner."""

from __future__ import annotations

import json
from contextlib import suppress
from typing import Literal, cast

from artana_evidence_api.full_ai_orchestrator_shadow_planner_models import (
    _COST_PAYLOAD_KEYS,
    _COST_SUMMARY_TYPES,
    ShadowPlannerTelemetry,
)
from artana_evidence_api.types.common import JSONObject


def _unavailable_shadow_planner_telemetry() -> ShadowPlannerTelemetry:
    return ShadowPlannerTelemetry(
        status="unavailable",
        model_terminal_count=0,
    )


def _shadow_planner_telemetry_payload(
    telemetry: ShadowPlannerTelemetry | None,
) -> JSONObject:
    if telemetry is None:
        telemetry = _unavailable_shadow_planner_telemetry()
    return {
        "status": telemetry.status,
        "model_terminal_count": telemetry.model_terminal_count,
        "prompt_tokens": telemetry.prompt_tokens,
        "completion_tokens": telemetry.completion_tokens,
        "total_tokens": telemetry.total_tokens,
        "cost_usd": telemetry.cost_usd,
        "latency_seconds": telemetry.latency_seconds,
        "tool_call_count": telemetry.tool_call_count,
    }


async def _collect_shadow_planner_telemetry(  # noqa: PLR0912, PLR0915
    *,
    store: object,
    run_ids: tuple[str, ...],
) -> ShadowPlannerTelemetry:
    get_events_for_run = getattr(store, "get_events_for_run", None)
    if not callable(get_events_for_run) or not run_ids:
        return _unavailable_shadow_planner_telemetry()

    from artana.events import EventType, ModelTerminalPayload

    model_terminal_count = 0
    prompt_tokens_total = 0
    completion_tokens_total = 0
    cost_total = 0.0
    latency_ms_total = 0
    tool_call_count = 0
    prompt_tokens_seen = False
    completion_tokens_seen = False
    cost_seen = False
    latency_seen = False

    for run_id in run_ids:
        events = await get_events_for_run(run_id)
        if not isinstance(events, list):
            continue
        run_cost_total = 0.0
        run_cost_seen = False
        for event in events:
            event_type = getattr(event, "event_type", None)
            payload = getattr(event, "payload", None)
            if event_type not in {
                EventType.MODEL_TERMINAL,
                EventType.MODEL_TERMINAL.value,
            }:
                continue
            if not isinstance(payload, ModelTerminalPayload):
                continue
            model_terminal_count += 1
            latency_ms_total += payload.elapsed_ms
            latency_seen = True
            tool_call_count += len(payload.tool_calls)
            if payload.prompt_tokens is not None:
                prompt_tokens_total += payload.prompt_tokens
                prompt_tokens_seen = True
            if payload.completion_tokens is not None:
                completion_tokens_total += payload.completion_tokens
                completion_tokens_seen = True
            model_terminal_cost_usd = _effective_shadow_planner_model_terminal_cost_usd(
                payload,
            )
            if model_terminal_cost_usd is not None:
                run_cost_total += model_terminal_cost_usd
                run_cost_seen = True

        summary_cost_usd = await _read_shadow_planner_run_cost_summary(
            store=store,
            run_id=run_id,
        )
        selected_cost_usd = _select_shadow_planner_run_cost_usd(
            summary_cost_usd=summary_cost_usd,
            model_terminal_cost_usd=run_cost_total if run_cost_seen else None,
        )
        if selected_cost_usd is not None:
            cost_total += selected_cost_usd
            cost_seen = True

    if model_terminal_count == 0 and not cost_seen:
        return _unavailable_shadow_planner_telemetry()

    prompt_tokens = prompt_tokens_total if prompt_tokens_seen else None
    completion_tokens = completion_tokens_total if completion_tokens_seen else None
    total_tokens = None
    if prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    status: Literal["available", "partial", "unavailable"] = "partial"
    if prompt_tokens is not None and completion_tokens is not None and cost_seen:
        status = "available"
    return ShadowPlannerTelemetry(
        status=status,
        model_terminal_count=model_terminal_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=round(cost_total, 8) if cost_seen else None,
        latency_seconds=round(latency_ms_total / 1000.0, 6) if latency_seen else None,
        tool_call_count=tool_call_count,
    )


async def _read_shadow_planner_run_cost_summary(
    *,
    store: object,
    run_id: str,
) -> float | None:
    get_latest_run_summary = getattr(store, "get_latest_run_summary", None)
    if not callable(get_latest_run_summary):
        return None

    for summary_type in _COST_SUMMARY_TYPES:
        with suppress(Exception):
            summary = await get_latest_run_summary(run_id, summary_type)
        if summary is None:
            continue
        payload = _shadow_planner_summary_payload(summary)
        if payload is None:
            continue
        cost_usd = _shadow_planner_cost_from_summary_payload(payload)
        if cost_usd is not None:
            return cost_usd
    return None


def _shadow_planner_summary_payload(summary: object) -> JSONObject | None:
    summary_json = getattr(summary, "summary_json", None)
    if not isinstance(summary_json, str):
        return None
    with suppress(json.JSONDecodeError):
        payload = json.loads(summary_json)
        if isinstance(payload, dict):
            return cast("JSONObject", payload)
    return None


def _shadow_planner_cost_from_summary_payload(payload: JSONObject) -> float | None:
    for key in _COST_PAYLOAD_KEYS:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            return round(float(value), 8)
    return None


def _select_shadow_planner_run_cost_usd(
    *,
    summary_cost_usd: float | None,
    model_terminal_cost_usd: float | None,
) -> float | None:
    if summary_cost_usd is not None and summary_cost_usd > 0.0:
        return round(summary_cost_usd, 8)
    if model_terminal_cost_usd is not None and model_terminal_cost_usd > 0.0:
        return round(model_terminal_cost_usd, 8)
    if summary_cost_usd == 0.0:
        return 0.0
    if model_terminal_cost_usd == 0.0:
        return 0.0
    return None


def _effective_shadow_planner_model_terminal_cost_usd(payload: object) -> float | None:
    reported_cost_usd = getattr(payload, "cost_usd", None)
    if isinstance(reported_cost_usd, int | float) and not isinstance(
        reported_cost_usd,
        bool,
    ):
        normalized_reported_cost = round(float(reported_cost_usd), 8)
        if normalized_reported_cost > 0.0:
            return normalized_reported_cost
        derived_cost_usd = _derive_shadow_planner_model_terminal_cost_usd(payload)
        if derived_cost_usd is not None:
            return derived_cost_usd
        return 0.0
    return _derive_shadow_planner_model_terminal_cost_usd(payload)


def _derive_shadow_planner_model_terminal_cost_usd(payload: object) -> float | None:
    model_id = getattr(payload, "model", None)
    prompt_tokens = getattr(payload, "prompt_tokens", None)
    completion_tokens = getattr(payload, "completion_tokens", None)
    if not isinstance(model_id, str):
        return None
    if not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool):
        return None
    if not isinstance(completion_tokens, int) or isinstance(completion_tokens, bool):
        return None

    normalized_model_id = _normalize_shadow_planner_cost_model_id(model_id)
    if ":" in normalized_model_id and not normalized_model_id.startswith("openai:"):
        return None

    from artana_evidence_api.llm_costs import calculate_openai_usage_cost_usd

    with suppress(Exception):
        cost_usd = calculate_openai_usage_cost_usd(
            model_id=normalized_model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        if cost_usd > 0.0:
            return cost_usd
    return None


def _normalize_shadow_planner_cost_model_id(model_id: str) -> str:
    normalized = model_id.strip()
    if normalized == "":
        return normalized
    if ":" in normalized:
        return normalized
    if "/" in normalized:
        provider, model_name = normalized.split("/", 1)
        if provider.strip() and model_name.strip():
            return f"{provider.strip()}:{model_name.strip()}"
    return normalized
