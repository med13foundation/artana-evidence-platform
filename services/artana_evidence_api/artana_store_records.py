"""Record and fallback serializers for Artana-backed stores."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from artana_evidence_api.artifact_store import (
    HarnessArtifactRecord,
    HarnessWorkspaceRecord,
)
from artana_evidence_api.run_registry import (
    HarnessRunEventRecord,
    HarnessRunProgressRecord,
    HarnessRunRecord,
)

if TYPE_CHECKING:
    from artana.events import KernelEvent
    from artana_evidence_api.types.common import JSONObject


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _payload_string(payload: JSONObject, key: str, *, default: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else default


def _payload_float(payload: JSONObject, key: str, *, default: float) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return float(value)


def _payload_optional_int(payload: JSONObject, key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _payload_json_object(payload: JSONObject, key: str) -> JSONObject:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _payload_optional_string(payload: JSONObject, key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _event_payload(event: KernelEvent) -> JSONObject:
    payload = event.payload.model_dump(mode="json")
    return payload if isinstance(payload, dict) else {}


def _pause_context_payload(payload: JSONObject) -> JSONObject:
    context_json = payload.get("context_json")
    if not isinstance(context_json, str) or context_json.strip() == "":
        return {}
    try:
        decoded = json.loads(context_json)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _kernel_event_record(
    *,
    run: HarnessRunRecord,
    event: KernelEvent,
) -> HarnessRunEventRecord:
    payload = _event_payload(event)
    event_type = event.event_type.value
    enriched_payload: JSONObject = dict(payload)
    message = event_type.replace("_", " ")
    progress_percent: float | None = None

    if event_type == "tool_requested":
        tool_name = payload.get("tool_name")
        if isinstance(tool_name, str):
            enriched_payload["decision_source"] = "tool"
            enriched_payload["tool_name"] = tool_name
            enriched_payload["status"] = "pending"
            enriched_payload["started_at"] = event.timestamp.isoformat()
            message = f"Tool '{tool_name}' requested."
    elif event_type == "tool_completed":
        tool_name = payload.get("tool_name")
        outcome = payload.get("outcome")
        if isinstance(tool_name, str):
            enriched_payload["decision_source"] = "tool"
            enriched_payload["tool_name"] = tool_name
            enriched_payload["status"] = "success" if outcome == "success" else "failed"
            enriched_payload["completed_at"] = event.timestamp.isoformat()
            message = f"Tool '{tool_name}' completed."
    elif event_type == "pause_requested":
        pause_context = _pause_context_payload(payload)
        approval_key = pause_context.get("approval_key")
        tool_name = pause_context.get("tool_name")
        if isinstance(tool_name, str):
            enriched_payload["decision_source"] = "tool"
            enriched_payload["tool_name"] = tool_name
            enriched_payload["status"] = "paused"
            message = f"Tool '{tool_name}' paused pending approval."
        if isinstance(approval_key, str):
            enriched_payload["approval_id"] = approval_key

    return HarnessRunEventRecord(
        id=event.event_id,
        space_id=run.space_id,
        run_id=run.id,
        event_type=event_type,
        status=run.status,
        message=message,
        progress_percent=progress_percent,
        payload=enriched_payload,
        created_at=event.timestamp,
        updated_at=event.timestamp,
    )


def _summary_event_payload(event: KernelEvent) -> tuple[str, JSONObject] | None:
    payload = _event_payload(event)
    summary_type = payload.get("summary_type")
    summary_json = payload.get("summary_json")
    if not isinstance(summary_type, str) or not isinstance(summary_json, str):
        return None
    try:
        decoded = json.loads(summary_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    return summary_type, decoded


def _fallback_manifest_content(run: HarnessRunRecord, *, degraded_reason: str) -> JSONObject:
    return {
        "run_id": run.id,
        "space_id": run.space_id,
        "harness_id": run.harness_id,
        "title": run.title,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "graph_service_status": run.graph_service_status,
        "graph_service_version": run.graph_service_version,
        "read_degraded": True,
        "read_degraded_reason": degraded_reason,
    }


def _fallback_workspace_snapshot(
    *,
    run: HarnessRunRecord,
    progress: HarnessRunProgressRecord | None,
    degraded_reason: str,
) -> JSONObject:
    snapshot: JSONObject = {
        "space_id": run.space_id,
        "run_id": run.id,
        "harness_id": run.harness_id,
        "title": run.title,
        "status": progress.status if progress is not None else run.status,
        "input_payload": run.input_payload,
        "graph_service": {
            "status": run.graph_service_status,
            "version": run.graph_service_version,
        },
        "artifact_keys": ["run_manifest"],
        "read_degraded": True,
        "read_degraded_reason": degraded_reason,
    }
    if progress is not None:
        snapshot["progress"] = {
            "status": progress.status,
            "phase": progress.phase,
            "message": progress.message,
            "progress_percent": progress.progress_percent,
            "completed_steps": progress.completed_steps,
            "total_steps": progress.total_steps,
            "resume_point": progress.resume_point,
            "metadata": progress.metadata,
            "created_at": progress.created_at.isoformat(),
            "updated_at": progress.updated_at.isoformat(),
        }
    return snapshot


def _fallback_workspace_record(
    *,
    run: HarnessRunRecord,
    progress: HarnessRunProgressRecord | None,
    degraded_reason: str,
) -> HarnessWorkspaceRecord:
    updated_at = progress.updated_at if progress is not None else run.updated_at
    return HarnessWorkspaceRecord(
        space_id=run.space_id,
        run_id=run.id,
        snapshot=_fallback_workspace_snapshot(
            run=run,
            progress=progress,
            degraded_reason=degraded_reason,
        ),
        created_at=run.created_at,
        updated_at=updated_at,
    )


def _fallback_manifest_artifact(
    *,
    run: HarnessRunRecord,
    degraded_reason: str,
) -> HarnessArtifactRecord:
    return HarnessArtifactRecord(
        space_id=run.space_id,
        run_id=run.id,
        key="run_manifest",
        media_type="application/json",
        content=_fallback_manifest_content(run, degraded_reason=degraded_reason),
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _fallback_events(
    *,
    run: HarnessRunRecord,
    progress: HarnessRunProgressRecord | None,
    degraded_reason: str,
) -> list[HarnessRunEventRecord]:
    payload: JSONObject = {
        "read_degraded": True,
        "read_degraded_reason": degraded_reason,
    }
    if progress is not None:
        payload["progress"] = {
            "phase": progress.phase,
            "message": progress.message,
            "progress_percent": progress.progress_percent,
            "completed_steps": progress.completed_steps,
            "total_steps": progress.total_steps,
            "resume_point": progress.resume_point,
            "metadata": progress.metadata,
            "updated_at": progress.updated_at.isoformat(),
        }
    timestamp = progress.updated_at if progress is not None else run.updated_at
    message = (
        "Run events are temporarily unavailable; returning degraded run status."
    )
    return [
        HarnessRunEventRecord(
            id=f"degraded-run-event:{run.id}",
            space_id=run.space_id,
            run_id=run.id,
            event_type="run.events_degraded",
            status=progress.status if progress is not None else run.status,
            message=message,
            progress_percent=(
                progress.progress_percent if progress is not None else None
            ),
            payload=payload,
            created_at=timestamp,
            updated_at=timestamp,
        ),
    ]


__all__ = [
    "_fallback_events",
    "_fallback_manifest_artifact",
    "_fallback_manifest_content",
    "_fallback_workspace_record",
    "_kernel_event_record",
    "_summary_event_payload",
]
