"""Payload builders and alert derivation for Artana observability."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from src.application.services._artana_observability_support import (
    _event_to_payload,
    _has_drift_alert,
    _normalize_effective_status,
    _serialize_datetime,
    _string_list,
    _summary_to_payload,
    _unique_string_values,
)
from src.application.services._source_workflow_monitor_shared import (
    normalize_optional_string,
)
from src.type_definitions.json_utils import as_float, as_object, to_json_value

if TYPE_CHECKING:
    from src.application.services._artana_observability_models import _RunSnapshotRow
    from src.application.services.ports.artana_run_trace_port import (
        ArtanaRunTraceEventRecord,
        ArtanaRunTraceRecord,
    )
    from src.type_definitions.common import JSONObject
    from src.type_definitions.data_sources import AgentRunTableSummary
else:
    JSONObject = dict[str, object]

alert_logger = logging.getLogger("artana.alerts.artana")

_TRACE_EVENT_LIMIT = 50
_STUCK_RUN_AGE = timedelta(minutes=10)
_UNKNOWN_OUTCOME_AGE = timedelta(minutes=5)
_BUDGET_WARNING_THRESHOLD = 0.8
_NON_TERMINAL_STATUSES = frozenset({"running", "paused"})
_ARTANA_SUMMARY_TYPES_OF_INTEREST: tuple[str, ...] = (
    "trace::state_transition",
    "trace::cost",
    "trace::cost_snapshot",
    "trace::drift",
    "trace::tool_validation",
    "artana::stage_transition",
    "artana::document_outcome",
    "artana::persistence_outcome",
    "agent_model_step",
    "agent_verify_step",
    "agent_acceptance_gate",
    "agent_tool_step",
)
_COST_KEYS: tuple[str, ...] = (
    "total_cost",
    "cost_usd",
    "total_cost_usd",
    "model_cost",
)
_BUDGET_KEYS: tuple[str, ...] = (
    "budget_usd_limit",
    "budget_limit_usd",
    "budget_limit",
    "tenant_budget_usd_limit",
    "run_budget_usd_limit",
)


def build_trace_payload(  # noqa: PLR0913 - explicit response shape is intentional
    *,
    requested_run_id: str,
    trace: ArtanaRunTraceRecord,
    candidate_run_ids: list[str],
    alerts: list[JSONObject],
    linked_records: list[JSONObject],
    raw_tables: list[AgentRunTableSummary] | None,
) -> JSONObject:
    source_ids = _unique_string_values(
        record.get("source_id") for record in linked_records
    )
    source_types = _unique_string_values(
        record.get("source_type") for record in linked_records
    )
    events = [_event_to_payload(event) for event in trace.events[-_TRACE_EVENT_LIMIT:]]
    summaries = [
        _summary_to_payload(summary)
        for summary in trace.summaries
        if summary.summary_type in _ARTANA_SUMMARY_TYPES_OF_INTEREST
    ]
    if not summaries:
        summaries = [_summary_to_payload(summary) for summary in trace.summaries]
    payload: JSONObject = {
        "requested_run_id": requested_run_id,
        "run_id": trace.run_id,
        "candidate_run_ids": candidate_run_ids,
        "space_id": trace.tenant_id,
        "source_ids": source_ids,
        "source_types": source_types,
        "status": trace.status,
        "last_event_seq": trace.last_event_seq,
        "last_event_type": trace.last_event_type,
        "progress_percent": trace.progress_percent,
        "current_stage": trace.current_stage,
        "completed_stages": list(trace.completed_stages),
        "started_at": _serialize_datetime(trace.started_at),
        "updated_at": _serialize_datetime(trace.updated_at),
        "eta_seconds": trace.eta_seconds,
        "blocked_on": trace.blocked_on,
        "failure_reason": trace.failure_reason,
        "error_category": trace.error_category,
        "explain": trace.explain,
        "alerts": alerts,
        "events": events,
        "summaries": summaries,
        "linked_records": linked_records,
    }
    if raw_tables is not None:
        payload["raw_tables"] = [
            {
                "table_name": table.table_name,
                "row_count": table.row_count,
                "latest_created_at": _serialize_datetime(table.latest_created_at),
                "sample_rows": table.sample_rows,
            }
            for table in raw_tables
        ]
    return payload


def build_alerts(
    *,
    trace: ArtanaRunTraceRecord | None,
    fallback_snapshot: _RunSnapshotRow | None,
    now: datetime,
) -> list[JSONObject]:
    alerts: list[JSONObject] = []
    effective_status = (
        _normalize_effective_status(trace.status)
        if trace is not None
        else _normalize_effective_status(
            fallback_snapshot.status if fallback_snapshot is not None else None,
        )
    )
    updated_at = (
        trace.updated_at
        if trace is not None and trace.updated_at is not None
        else (fallback_snapshot.updated_at if fallback_snapshot is not None else None)
    )
    if effective_status == "failed":
        alerts.append(
            {
                "code": "failed_run",
                "severity": "error",
                "title": "Run failed",
                "description": (
                    trace.failure_reason
                    if trace is not None and trace.failure_reason is not None
                    else (
                        fallback_snapshot.failure_reason
                        if fallback_snapshot is not None
                        else "Run entered a terminal failure state."
                    )
                ),
                "triggered_at": _serialize_datetime(updated_at),
                "metadata": {},
            },
        )
    if (
        effective_status in _NON_TERMINAL_STATUSES
        and updated_at is not None
        and now - updated_at >= _STUCK_RUN_AGE
    ):
        alerts.append(
            {
                "code": "stuck_run",
                "severity": "warning",
                "title": "Run may be stuck",
                "description": "Run is non-terminal and has not emitted a recent update.",
                "triggered_at": _serialize_datetime(updated_at),
                "metadata": {"updated_at": updated_at.isoformat()},
            },
        )
    unknown_outcome = (
        _resolve_unknown_outcome_alert(trace.events, now=now)
        if trace is not None
        else None
    )
    if unknown_outcome is not None:
        alerts.append(
            {
                "code": "tool_unknown_outcome",
                "severity": "warning",
                "title": "Tool or model outcome is unknown",
                "description": unknown_outcome["description"],
                "triggered_at": unknown_outcome["triggered_at"],
                "metadata": unknown_outcome["metadata"],
            },
        )
    if _has_drift_alert(trace=trace, fallback_snapshot=fallback_snapshot):
        alerts.append(
            {
                "code": "drift_detected",
                "severity": "warning",
                "title": "Prompt or replay drift detected",
                "description": "Run recorded drift or forked replay metadata.",
                "triggered_at": _serialize_datetime(updated_at),
                "metadata": {},
            },
        )
    budget_warning = _resolve_budget_warning(trace=trace)
    if budget_warning is not None:
        alerts.append(
            {
                "code": "budget_warning",
                "severity": "warning",
                "title": "Run spend is nearing budget",
                "description": budget_warning["description"],
                "triggered_at": budget_warning["triggered_at"],
                "metadata": budget_warning["metadata"],
            },
        )
    return alerts


def emit_alert_logs(
    *,
    run_id: str,
    space_id: str,
    alerts: list[JSONObject],
    linked_records: list[JSONObject],
) -> None:
    if not alerts:
        return
    source_ids = _unique_string_values(
        record.get("source_id") for record in linked_records
    )
    document_ids = _unique_string_values(
        record.get("document_id") for record in linked_records
    )
    for alert in alerts:
        payload = {
            "alert_code": alert.get("code"),
            "severity": alert.get("severity"),
            "run_id": run_id,
            "space_id": space_id,
            "source_ids": source_ids,
            "document_ids": document_ids,
            "metadata": as_object(to_json_value(alert.get("metadata"))),
        }
        message = json.dumps(payload, sort_keys=True)
        if alert.get("severity") == "error":
            alert_logger.error(message)
        else:
            alert_logger.warning(message)


def build_list_item(
    *,
    snapshot: _RunSnapshotRow,
    trace: ArtanaRunTraceRecord | None,
    linked_records: list[JSONObject],
    alerts: list[JSONObject],
) -> JSONObject:
    source_ids = _unique_string_values(
        record.get("source_id") for record in linked_records
    )
    source_types = _unique_string_values(
        record.get("source_type") for record in linked_records
    )
    alert_codes = [
        str(alert.get("code")) for alert in alerts if isinstance(alert.get("code"), str)
    ]
    return {
        "run_id": snapshot.run_id,
        "space_id": snapshot.tenant_id,
        "source_ids": source_ids,
        "source_type": source_types[0] if source_types else None,
        "status": (
            trace.status
            if trace is not None
            else _normalize_effective_status(snapshot.status)
        ),
        "current_stage": (
            trace.current_stage
            if trace is not None and trace.current_stage is not None
            else snapshot.last_stage
        ),
        "updated_at": _serialize_datetime(
            trace.updated_at if trace is not None else snapshot.updated_at,
        ),
        "started_at": _serialize_datetime(
            trace.started_at if trace is not None else None,
        ),
        "last_event_type": (
            trace.last_event_type
            if trace is not None and trace.last_event_type is not None
            else snapshot.last_event_type
        ),
        "alert_count": len(alert_codes),
        "alert_codes": alert_codes,
    }


def build_list_counters(items: list[JSONObject]) -> dict[str, int]:
    counters: dict[str, int] = {
        "running": 0,
        "failed": 0,
        "stuck": 0,
        "drift_detected": 0,
        "budget_warning": 0,
        "tool_unknown_outcome": 0,
    }
    for item in items:
        status = normalize_optional_string(item.get("status"))
        if status == "running":
            counters["running"] += 1
        if status == "failed":
            counters["failed"] += 1
        alert_codes = set(_string_list(item.get("alert_codes")))
        if "stuck_run" in alert_codes:
            counters["stuck"] += 1
        if "drift_detected" in alert_codes:
            counters["drift_detected"] += 1
        if "budget_warning" in alert_codes:
            counters["budget_warning"] += 1
        if "tool_unknown_outcome" in alert_codes:
            counters["tool_unknown_outcome"] += 1
    return counters


def _resolve_unknown_outcome_alert(
    events: tuple[ArtanaRunTraceEventRecord, ...],
    *,
    now: datetime,
) -> JSONObject | None:
    pending_requests: dict[str, ArtanaRunTraceEventRecord] = {}
    for event in events:
        requested_id = _requested_event_id(event)
        if requested_id is not None:
            pending_requests[requested_id] = event
            continue
        completed_id = _completed_event_id(event)
        if completed_id is not None:
            pending_requests.pop(completed_id, None)

    oldest_pending: ArtanaRunTraceEventRecord | None = None
    for pending in pending_requests.values():
        if now - pending.timestamp < _UNKNOWN_OUTCOME_AGE:
            continue
        if oldest_pending is None or pending.timestamp < oldest_pending.timestamp:
            oldest_pending = pending
    if oldest_pending is None:
        return None
    pending_label = oldest_pending.tool_name or oldest_pending.event_type
    return {
        "description": (
            f"Pending {pending_label} request has no terminal outcome after five minutes."
        ),
        "triggered_at": _serialize_datetime(oldest_pending.timestamp),
        "metadata": {
            "pending_event_id": oldest_pending.event_id,
            "pending_event_type": oldest_pending.event_type,
            "pending_tool_name": oldest_pending.tool_name,
        },
    }


def _requested_event_id(event: ArtanaRunTraceEventRecord) -> str | None:
    if event.event_type in {"tool_requested", "model_requested"}:
        return event.event_id
    return None


def _completed_event_id(event: ArtanaRunTraceEventRecord) -> str | None:
    if event.event_type == "tool_completed":
        return normalize_optional_string(event.payload.get("request_id"))
    if event.event_type == "model_terminal":
        return normalize_optional_string(
            event.payload.get("source_model_requested_event_id"),
        )
    return None


def _resolve_budget_warning(
    *,
    trace: ArtanaRunTraceRecord | None,
) -> JSONObject | None:
    if trace is None:
        return None
    summary = next(
        (
            item
            for item in trace.summaries
            if item.summary_type in {"trace::cost", "trace::cost_snapshot"}
        ),
        None,
    )
    if summary is None:
        return None
    payload = as_object(to_json_value(summary.payload))
    cost_value = next(
        (
            as_float(payload.get(key))
            for key in _COST_KEYS
            if payload.get(key) is not None
        ),
        None,
    )
    budget_value = next(
        (
            as_float(payload.get(key))
            for key in _BUDGET_KEYS
            if payload.get(key) is not None
        ),
        None,
    )
    if cost_value is None or budget_value is None or budget_value <= 0:
        return None
    ratio = cost_value / budget_value
    if ratio < _BUDGET_WARNING_THRESHOLD:
        return None
    return {
        "description": (
            f"Run cost is {cost_value:.4f} USD against a {budget_value:.4f} USD budget."
        ),
        "triggered_at": _serialize_datetime(summary.timestamp),
        "metadata": {
            "cost_usd": cost_value,
            "budget_usd_limit": budget_value,
            "budget_ratio": ratio,
        },
    }


__all__ = [
    "_resolve_budget_warning",
    "_resolve_unknown_outcome_alert",
    "build_alerts",
    "build_list_counters",
    "build_list_item",
    "build_trace_payload",
    "emit_alert_logs",
]
