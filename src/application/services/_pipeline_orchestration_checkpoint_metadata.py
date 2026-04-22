"""Metadata builders shared by pipeline orchestration checkpoint helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services._pipeline_orchestration_contracts import (
        PipelineStageName,
        PipelineStageStatus,
    )
    from src.type_definitions.common import JSONObject


def coerce_json_object(raw_value: object) -> JSONObject:
    """Convert arbitrary metadata payloads into JSON-serializable objects."""
    if not isinstance(raw_value, dict):
        return {}
    return {str(key): to_json_value(value) for key, value in raw_value.items()}


def build_pipeline_metadata(  # noqa: PLR0913
    *,
    existing_metadata: object,
    run_id: str,
    research_space_id: UUID,
    resume_from_stage: PipelineStageName | None,
    overall_status: Literal[
        "queued",
        "retrying",
        "running",
        "completed",
        "failed",
        "cancelled",
    ],
    stage_updates: dict[PipelineStageName, tuple[PipelineStageStatus, str | None]],
) -> JSONObject:
    """Merge queue, checkpoint, and timestamp metadata for one pipeline run."""
    metadata = coerce_json_object(existing_metadata)
    pipeline_raw = metadata.get("pipeline_run")
    pipeline_payload = (
        coerce_json_object(pipeline_raw) if isinstance(pipeline_raw, dict) else {}
    )
    checkpoints_raw = pipeline_payload.get("checkpoints")
    checkpoints = (
        coerce_json_object(checkpoints_raw) if isinstance(checkpoints_raw, dict) else {}
    )
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")

    for stage_name, (stage_status, stage_error) in stage_updates.items():
        checkpoint: JSONObject = {
            "stage": stage_name,
            "status": stage_status,
            "updated_at": timestamp,
        }
        if stage_error is not None and stage_error.strip():
            checkpoint["error"] = stage_error.strip()
        checkpoints[stage_name] = checkpoint

    accepted_at_raw = pipeline_payload.get("accepted_at")
    accepted_at = (
        accepted_at_raw
        if isinstance(accepted_at_raw, str) and accepted_at_raw.strip()
        else timestamp
    )
    started_at_raw = pipeline_payload.get("started_at")
    existing_started_at: str | None = (
        started_at_raw
        if isinstance(started_at_raw, str) and started_at_raw.strip()
        else None
    )
    started_at: str | None
    if overall_status == "running":
        started_at = existing_started_at or timestamp
    elif overall_status in {"completed", "failed", "cancelled"}:
        started_at = existing_started_at or accepted_at
    else:
        started_at = existing_started_at
    completed_at = (
        timestamp if overall_status in {"completed", "failed", "cancelled"} else None
    )

    pipeline_payload.update(
        {
            "run_id": run_id,
            "research_space_id": str(research_space_id),
            "resume_from_stage": resume_from_stage,
            "status": overall_status,
            "queue_status": overall_status,
            "accepted_at": accepted_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "updated_at": timestamp,
            "checkpoints": checkpoints,
        },
    )
    metadata["pipeline_run"] = pipeline_payload
    return metadata


__all__ = ["build_pipeline_metadata", "coerce_json_object"]
