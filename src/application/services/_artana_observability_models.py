"""Shared snapshot models and constants for Artana observability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.application.services._artana_observability_support import (
    _coerce_datetime,
    _normalize_effective_status,
    _safe_int,
)
from src.application.services._source_workflow_monitor_shared import (
    normalize_optional_string,
)
from src.type_definitions.json_utils import as_float, to_json_value

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.engine import RowMapping

_DOCUMENT_METADATA_RUN_KEYS: tuple[str, ...] = (
    "content_enrichment_agent_run_id",
    "entity_recognition_run_id",
    "extraction_stage_run_id",
    "extraction_run_id",
    "graph_agent_run_id",
    "graph_connection_run_id",
    "graph_run_id",
)
_EXTRACTION_METADATA_RUN_KEYS: tuple[str, ...] = (
    "agent_run_id",
    "extraction_run_id",
    "graph_agent_run_id",
    "graph_connection_run_id",
    "graph_run_id",
)

_SNAPSHOT_LIST_QUERY = text(
    """
    SELECT
        run_id,
        tenant_id,
        last_event_seq,
        last_event_type,
        updated_at,
        status,
        blocked_on,
        failure_reason,
        error_category,
        diagnostics_json,
        last_step_key,
        drift_count,
        last_stage,
        last_tool,
        model_cost_total,
        open_pause_count,
        explain_status,
        explain_failure_reason,
        explain_failure_step
    FROM artana.run_state_snapshots
    WHERE (:run_id IS NULL OR run_id = :run_id)
      AND (:tenant_id IS NULL OR tenant_id = :tenant_id)
      AND (:status IS NULL OR status = :status)
      AND (:updated_since IS NULL OR updated_at >= :updated_since)
    ORDER BY updated_at DESC
    """,
)


@dataclass(frozen=True, slots=True)
class _RunSnapshotRow:
    run_id: str
    tenant_id: str
    last_event_seq: int
    last_event_type: str | None
    updated_at: datetime | None
    status: str
    blocked_on: str | None
    failure_reason: str | None
    error_category: str | None
    diagnostics_json: str | None
    last_step_key: str | None
    drift_count: int
    last_stage: str | None
    last_tool: str | None
    model_cost_total: float
    open_pause_count: int
    explain_status: str | None
    explain_failure_reason: str | None
    explain_failure_step: str | None


@dataclass(frozen=True, slots=True)
class _RunResolution:
    resolved_run_id: str
    candidate_run_ids: list[str]
    snapshot: _RunSnapshotRow | None


def _snapshot_from_row(row: RowMapping) -> _RunSnapshotRow:
    return _RunSnapshotRow(
        run_id=str(row["run_id"]),
        tenant_id=str(row["tenant_id"]),
        last_event_seq=_safe_int(row["last_event_seq"]),
        last_event_type=normalize_optional_string(row["last_event_type"]),
        updated_at=_coerce_datetime(row["updated_at"]),
        status=_normalize_effective_status(row["status"]) or "unknown",
        blocked_on=normalize_optional_string(row["blocked_on"]),
        failure_reason=normalize_optional_string(row["failure_reason"]),
        error_category=normalize_optional_string(row["error_category"]),
        diagnostics_json=normalize_optional_string(row["diagnostics_json"]),
        last_step_key=normalize_optional_string(row["last_step_key"]),
        drift_count=_safe_int(row["drift_count"]),
        last_stage=normalize_optional_string(row["last_stage"]),
        last_tool=normalize_optional_string(row["last_tool"]),
        model_cost_total=as_float(to_json_value(row["model_cost_total"])) or 0.0,
        open_pause_count=_safe_int(row["open_pause_count"]),
        explain_status=normalize_optional_string(row["explain_status"]),
        explain_failure_reason=normalize_optional_string(row["explain_failure_reason"]),
        explain_failure_step=normalize_optional_string(row["explain_failure_step"]),
    )


__all__ = [
    "_DOCUMENT_METADATA_RUN_KEYS",
    "_EXTRACTION_METADATA_RUN_KEYS",
    "_RunResolution",
    "_RunSnapshotRow",
    "_SNAPSHOT_LIST_QUERY",
    "_snapshot_from_row",
]
