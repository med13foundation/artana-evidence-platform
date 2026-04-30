"""Model telemetry helpers for Phase 1 comparison."""

from __future__ import annotations

import json
from collections import deque
from typing import Literal

from artana_evidence_api.phase1_compare_summaries import (
    _normalized_unique_strings,
)
from artana_evidence_api.runtime_support import create_artana_postgres_store
from artana_evidence_api.types.common import JSONObject


def _collect_run_ids_from_payload(value: object) -> list[str]:
    collected: list[str] = []
    visited_json_strings: set[str] = set()

    def _visit(node: object) -> None:
        if isinstance(node, dict):
            for key, nested_value in node.items():
                normalized_key = key.casefold() if isinstance(key, str) else ""
                if normalized_key.endswith("run_ids") and isinstance(
                    nested_value, list
                ):
                    collected.extend(
                        item for item in nested_value if isinstance(item, str)
                    )
                elif normalized_key.endswith("run_id") and isinstance(
                    nested_value, str
                ):
                    collected.append(nested_value)
                _visit(nested_value)
            return
        if isinstance(node, list):
            for item in node:
                _visit(item)
            return
        if isinstance(node, str):
            trimmed = node.strip()
            if trimmed == "" or trimmed in visited_json_strings:
                return
            if trimmed[0] not in {"{", "["}:
                return
            try:
                parsed = json.loads(trimmed)
            except ValueError:
                return
            visited_json_strings.add(trimmed)
            _visit(parsed)

    _visit(value)
    return _normalized_unique_strings(collected)


def _collect_baseline_run_ids(
    *,
    baseline_run_id: str,
    workspace_snapshot: JSONObject | None,
    artifact_contents: list[JSONObject],
) -> list[str]:
    collected = [baseline_run_id]
    if workspace_snapshot is not None:
        collected.extend(_collect_run_ids_from_payload(workspace_snapshot))
    for artifact_content in artifact_contents:
        collected.extend(_collect_run_ids_from_payload(artifact_content))
    return _normalized_unique_strings(collected)


def _collect_shadow_planner_run_ids(
    *,
    decision_history: JSONObject | None,
    latest_shadow_planner_summary: JSONObject | None,
) -> list[str]:
    collected: list[str] = []
    if decision_history is not None:
        collected.extend(_collect_run_ids_from_payload(decision_history))
    if latest_shadow_planner_summary is not None:
        collected.extend(_collect_run_ids_from_payload(latest_shadow_planner_summary))
    return _normalized_unique_strings(collected)


def _unavailable_model_telemetry() -> JSONObject:
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


async def _collect_model_telemetry(
    *,
    store: object,
    run_ids: tuple[str, ...],
) -> JSONObject:
    get_events_for_run = getattr(store, "get_events_for_run", None)
    if not callable(get_events_for_run) or not run_ids:
        return _unavailable_model_telemetry()

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
            if payload.cost_usd is not None:
                cost_total += payload.cost_usd
                cost_seen = True

    if model_terminal_count == 0:
        return _unavailable_model_telemetry()

    prompt_tokens = prompt_tokens_total if prompt_tokens_seen else None
    completion_tokens = completion_tokens_total if completion_tokens_seen else None
    total_tokens = None
    if prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    status: Literal["available", "partial", "unavailable"] = "partial"
    if prompt_tokens is not None and completion_tokens is not None and cost_seen:
        status = "available"
    return {
        "status": status,
        "model_terminal_count": model_terminal_count,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_total, 8) if cost_seen else None,
        "latency_seconds": (
            round(latency_ms_total / 1000.0, 6) if latency_seen else None
        ),
        "tool_call_count": tool_call_count,
    }


async def _resolve_run_event_time_window(
    *,
    store: object,
    run_id: str,
) -> tuple[object, object] | None:
    get_events_for_run = getattr(store, "get_events_for_run", None)
    if not callable(get_events_for_run):
        return None

    events = await get_events_for_run(run_id)
    if not isinstance(events, list) or not events:
        return None
    started_at = getattr(events[0], "timestamp", None)
    finished_at = getattr(events[-1], "timestamp", None)
    if started_at is None or finished_at is None:
        return None
    return (started_at, finished_at)


async def _collect_model_terminal_run_ids_for_tenant_window(
    *,
    store: object,
    tenant_id: str,
    started_at: object,
    finished_at: object,
    excluded_run_id_prefixes: tuple[str, ...] = (),
) -> list[str]:
    fetch = getattr(store, "_fetch", None)
    if not callable(fetch):
        return []

    from artana.events import EventType

    rows = await fetch(
        """
        SELECT DISTINCT run_id
        FROM kernel_events
        WHERE tenant_id = $1
          AND event_type = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY run_id ASC
        """,
        tenant_id,
        EventType.MODEL_TERMINAL.value,
        started_at,
        finished_at,
    )
    collected: list[str] = []
    for row in rows:
        run_id = row["run_id"]
        if not isinstance(run_id, str):
            continue
        if any(run_id.startswith(prefix) for prefix in excluded_run_id_prefixes):
            continue
        collected.append(run_id)
    return collected


async def _expand_run_lineage_from_events(
    *,
    store: object,
    run_ids: tuple[str, ...],
) -> list[str]:
    get_events_for_run = getattr(store, "get_events_for_run", None)
    if not callable(get_events_for_run) or not run_ids:
        return list(run_ids)

    discovered = list(run_ids)
    seen = set(run_ids)
    pending: deque[str] = deque(run_ids)

    while pending:
        current_run_id = pending.popleft()
        events = await get_events_for_run(current_run_id)
        if not isinstance(events, list):
            continue
        for event in events:
            payload = getattr(event, "payload", None)
            payload_model_dump = getattr(payload, "model_dump", None)
            if callable(payload_model_dump):
                payload = payload_model_dump(mode="json")
            if not isinstance(payload, dict | list | str):
                continue
            for discovered_run_id in _collect_run_ids_from_payload(payload):
                if discovered_run_id in seen:
                    continue
                seen.add(discovered_run_id)
                discovered.append(discovered_run_id)
                pending.append(discovered_run_id)

    return discovered


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, int):
        return float(value)
    return value if isinstance(value, float) else None


def _build_phase1_cost_comparison(
    *,
    baseline_telemetry: JSONObject,
    shadow_cost_tracking: JSONObject | None,
) -> JSONObject:
    if shadow_cost_tracking is None:
        shadow_cost_tracking = {}

    baseline_status = str(baseline_telemetry.get("status", "unavailable"))
    planner_status = str(shadow_cost_tracking.get("status", "unavailable"))
    baseline_total_cost_usd = _optional_float(baseline_telemetry.get("cost_usd"))
    baseline_total_tokens = _optional_int(baseline_telemetry.get("total_tokens"))
    baseline_latency_seconds = _optional_float(
        baseline_telemetry.get("latency_seconds"),
    )
    planner_total_cost_usd = _optional_float(
        shadow_cost_tracking.get("planner_total_cost_usd"),
    )
    planner_total_tokens = _optional_int(
        shadow_cost_tracking.get("planner_total_tokens"),
    )
    planner_latency_seconds = _optional_float(
        shadow_cost_tracking.get("planner_total_latency_seconds"),
    )

    ratio = None
    within_limit = None
    evaluated = False
    notes = (
        "Cost comparison is unavailable until both deterministic baseline and "
        "shadow planner telemetry are present."
    )
    if baseline_total_cost_usd is not None and planner_total_cost_usd is not None:
        evaluated = True
        if baseline_total_cost_usd > 0:
            ratio = round(planner_total_cost_usd / baseline_total_cost_usd, 6)
            within_limit = planner_total_cost_usd <= baseline_total_cost_usd * 2.0
            notes = (
                "Planner cost can now be compared against the real deterministic "
                "baseline from the Phase 1 replay."
            )
        else:
            notes = (
                "Deterministic baseline telemetry is present, but its recorded "
                "cost is zero, so a planner-to-baseline ratio cannot be computed."
            )
    return {
        "status": (
            "available"
            if evaluated
            else (
                "partial"
                if baseline_status != "unavailable" or planner_status != "unavailable"
                else "unavailable"
            )
        ),
        "evaluated": evaluated,
        "baseline_status": baseline_status,
        "planner_status": planner_status,
        "baseline_total_cost_usd": baseline_total_cost_usd,
        "baseline_total_tokens": baseline_total_tokens,
        "baseline_latency_seconds": baseline_latency_seconds,
        "planner_total_cost_usd": planner_total_cost_usd,
        "planner_total_tokens": planner_total_tokens,
        "planner_latency_seconds": planner_latency_seconds,
        "planner_vs_baseline_cost_ratio": ratio,
        "gate_within_2x_baseline": within_limit,
        "notes": notes,
    }



async def _collect_baseline_telemetry_for_compare(
    *,
    space_id: str,
    baseline_run_id: str,
    workspace_snapshot: JSONObject | None,
    artifact_contents: list[JSONObject],
) -> tuple[list[str], JSONObject]:
    baseline_telemetry_run_ids = _collect_baseline_run_ids(
        baseline_run_id=baseline_run_id,
        workspace_snapshot=workspace_snapshot,
        artifact_contents=artifact_contents,
    )
    telemetry_store = create_artana_postgres_store()
    try:
        baseline_time_window = await _resolve_run_event_time_window(
            store=telemetry_store,
            run_id=baseline_run_id,
        )
        baseline_telemetry_run_ids = await _expand_run_lineage_from_events(
            store=telemetry_store,
            run_ids=tuple(baseline_telemetry_run_ids),
        )
        if baseline_time_window is not None:
            tenant_scoped_run_ids = (
                await _collect_model_terminal_run_ids_for_tenant_window(
                    store=telemetry_store,
                    tenant_id=space_id,
                    started_at=baseline_time_window[0],
                    finished_at=baseline_time_window[1],
                    excluded_run_id_prefixes=("full-ai-shadow-planner:",),
                )
            )
            baseline_telemetry_run_ids = _normalized_unique_strings(
                baseline_telemetry_run_ids + tenant_scoped_run_ids,
            )
        baseline_telemetry = await _collect_model_telemetry(
            store=telemetry_store,
            run_ids=tuple(baseline_telemetry_run_ids),
        )
    finally:
        await telemetry_store.close()
    return baseline_telemetry_run_ids, baseline_telemetry



__all__ = [
    "_build_phase1_cost_comparison",
    "_collect_baseline_run_ids",
    "_collect_baseline_telemetry_for_compare",
    "_collect_run_ids_from_payload",
    "_collect_shadow_planner_run_ids",
]
