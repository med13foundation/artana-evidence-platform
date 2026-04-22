"""Shared helpers for Artana observability payload normalization."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.application.services._source_workflow_monitor_shared import (
    normalize_optional_string,
)
from src.type_definitions.json_utils import as_object, extend_unique, to_json_value

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.application.services.ports.artana_run_trace_port import (
        ArtanaRunTraceEventRecord,
        ArtanaRunTraceRecord,
        ArtanaRunTraceSummaryRecord,
    )
    from src.models.database.source_document import SourceDocumentModel
    from src.type_definitions.common import JSONObject


def _require_run_id(run_id: str) -> str:
    normalized = run_id.strip()
    if not normalized:
        msg = "Run id must be non-empty."
        raise ValueError(msg)
    return normalized


def _parse_uuid(raw_value: str | None) -> UUID | None:
    normalized = normalize_optional_string(raw_value)
    if normalized is None:
        return None
    try:
        return UUID(normalized)
    except ValueError:
        return None


def _append_unique(bucket: list[str], value: object) -> None:
    normalized = normalize_optional_string(value)
    if normalized is None or normalized in bucket:
        return
    bucket.append(normalized)


def _metadata_contains_run(
    *,
    metadata: JSONObject,
    run_id: str,
    candidate_keys: tuple[str, ...],
) -> bool:
    return any(
        normalize_optional_string(metadata.get(key)) == run_id for key in candidate_keys
    )


def _document_matches_run(
    *,
    row: SourceDocumentModel,
    metadata: JSONObject,
    run_id: str,
    candidate_keys: tuple[str, ...],
) -> bool:
    if normalize_optional_string(row.enrichment_agent_run_id) == run_id:
        return True
    if normalize_optional_string(row.extraction_agent_run_id) == run_id:
        return True
    return _metadata_contains_run(
        metadata=metadata,
        run_id=run_id,
        candidate_keys=candidate_keys,
    )


def _event_to_payload(event: ArtanaRunTraceEventRecord) -> JSONObject:
    return {
        "seq": event.seq,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "timestamp": _serialize_datetime(event.timestamp),
        "parent_step_key": event.parent_step_key,
        "step_key": event.step_key,
        "tool_name": event.tool_name,
        "tool_outcome": event.tool_outcome,
        "payload": event.payload,
    }


def _summary_to_payload(summary: ArtanaRunTraceSummaryRecord) -> JSONObject:
    payload = summary.payload
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return {
        "summary_type": summary.summary_type,
        "timestamp": _serialize_datetime(summary.timestamp),
        "step_key": summary.step_key,
        "payload": payload,
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str)]


def _unique_string_values(values: Iterable[object]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        normalized = normalize_optional_string(value)
        if normalized is None:
            continue
        extend_unique(unique_values, [normalized])
    return unique_values


def _matches_query(*, item: JSONObject, query: str) -> bool:
    haystack: list[str] = []
    for key in (
        "run_id",
        "space_id",
        "source_type",
        "current_stage",
        "last_event_type",
    ):
        raw_value = item.get(key)
        if isinstance(raw_value, str):
            haystack.append(raw_value.lower())
    for key in ("source_ids", "alert_codes"):
        haystack.extend(value.lower() for value in _string_list(item.get(key)))
    return any(query in value for value in haystack)


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _coerce_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _normalize_effective_status(raw_status: object) -> str | None:
    normalized = normalize_optional_string(raw_status)
    if normalized is None:
        return None
    if normalized == "active":
        return "running"
    return normalized


def _normalize_snapshot_status_filter(raw_status: str | None) -> str | None:
    normalized = normalize_optional_string(raw_status)
    if normalized is None:
        return None
    if normalized == "running":
        return "active"
    return normalized


def _has_drift_alert(
    *,
    trace: ArtanaRunTraceRecord | None,
    fallback_snapshot: object | None,
) -> bool:
    if trace is not None:
        explain = as_object(to_json_value(trace.explain))
        drift_count = _safe_int(explain.get("drift_count"))
        if drift_count > 0:
            return True
        drift_summary = next(
            (
                summary
                for summary in trace.summaries
                if summary.summary_type == "trace::drift"
            ),
            None,
        )
        if drift_summary is not None:
            payload = as_object(to_json_value(drift_summary.payload))
            drift_fields = payload.get("drift_fields")
            if isinstance(drift_fields, list) and len(drift_fields) > 0:
                return True
            if payload.get("forked") is True:
                return True
    return bool(getattr(fallback_snapshot, "drift_count", 0))


__all__ = [
    "_append_unique",
    "_coerce_datetime",
    "_document_matches_run",
    "_event_to_payload",
    "_has_drift_alert",
    "_matches_query",
    "_metadata_contains_run",
    "_normalize_effective_status",
    "_normalize_snapshot_status_filter",
    "_parse_uuid",
    "_require_run_id",
    "_safe_int",
    "_serialize_datetime",
    "_string_list",
    "_summary_to_payload",
    "_unique_string_values",
]
