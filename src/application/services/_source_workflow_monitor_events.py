"""Workflow event timeline helpers for source workflow monitor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, select

from src.models.database.pipeline_run_event import PipelineRunEventModel

from ._source_workflow_monitor_pipeline import SourceWorkflowMonitorPipelineMixin
from ._source_workflow_monitor_shared import normalize_optional_string

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub


def _parse_timestamp(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    candidate = normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _scope_kind_to_category(scope_kind: str) -> str:
    if scope_kind in {"run", "query", "cost"}:
        return "run"
    if scope_kind == "document":
        return "document"
    if scope_kind in {"dictionary", "concept", "relation"}:
        return "review"
    if scope_kind == "graph":
        return "graph"
    return "stage"


class SourceWorkflowMonitorEventsMixin(SourceWorkflowMonitorPipelineMixin):
    """Workflow event shaping helpers for source workflow monitoring."""

    _session: Session

    @staticmethod
    def _serialize_event_row(
        *,
        row: PipelineRunEventModel,
        source_id: UUID,
    ) -> JSONObject:
        return {
            "event_id": f"{row.pipeline_run_id}:{row.seq}",
            "source_id": str(source_id),
            "run_id": row.pipeline_run_id,
            "occurred_at": row.occurred_at.isoformat(),
            "category": _scope_kind_to_category(row.scope_kind),
            "event_type": row.event_type,
            "stage": row.stage,
            "status": row.status,
            "level": row.level,
            "scope_kind": row.scope_kind,
            "scope_id": row.scope_id,
            "agent_kind": row.agent_kind,
            "agent_run_id": row.agent_run_id,
            "error_code": row.error_code,
            "message": row.message,
            "started_at": (
                row.started_at.isoformat() if row.started_at is not None else None
            ),
            "completed_at": (
                row.completed_at.isoformat() if row.completed_at is not None else None
            ),
            "duration_ms": row.duration_ms,
            "queue_wait_ms": row.queue_wait_ms,
            "timeout_budget_ms": row.timeout_budget_ms,
            "payload": dict(row.payload),
        }

    def list_workflow_events(  # noqa: C901, PLR0913
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        run_id: str | None,
        limit: int,
        since: str | None,
        stage: str | None = None,
        level: str | None = None,
        scope_kind: str | None = None,
        scope_id: str | None = None,
        agent_kind: str | None = None,
    ) -> JSONObject:
        self._require_source(space_id=space_id, source_id=source_id)
        since_timestamp = _parse_timestamp(since) if since is not None else None
        if since is not None and since_timestamp is None:
            msg = "since must be a valid ISO-8601 datetime"
            raise ValueError(msg)

        selected_run_id = run_id
        if selected_run_id is None or not selected_run_id.strip():
            run_records = self._load_pipeline_runs(source_id=source_id, limit=1)
            selected_run_id = run_records[0].run_id if run_records else None

        if selected_run_id is None:
            return {
                "source_id": str(source_id),
                "run_id": None,
                "generated_at": datetime.now(UTC).isoformat(),
                "events": [],
                "total": 0,
                "has_more": False,
            }

        statement = (
            select(PipelineRunEventModel)
            .where(PipelineRunEventModel.research_space_id == str(space_id))
            .where(PipelineRunEventModel.source_id == str(source_id))
            .where(PipelineRunEventModel.pipeline_run_id == selected_run_id)
        )
        normalized_stage = normalize_optional_string(stage)
        if normalized_stage is not None:
            statement = statement.where(PipelineRunEventModel.stage == normalized_stage)
        normalized_level = normalize_optional_string(level)
        if normalized_level is not None:
            statement = statement.where(PipelineRunEventModel.level == normalized_level)
        normalized_scope_kind = normalize_optional_string(scope_kind)
        if normalized_scope_kind is not None:
            statement = statement.where(
                PipelineRunEventModel.scope_kind == normalized_scope_kind,
            )
        normalized_scope_id = normalize_optional_string(scope_id)
        if normalized_scope_id is not None:
            statement = statement.where(
                PipelineRunEventModel.scope_id == normalized_scope_id,
            )
        normalized_agent_kind = normalize_optional_string(agent_kind)
        if normalized_agent_kind is not None:
            statement = statement.where(
                PipelineRunEventModel.agent_kind == normalized_agent_kind,
            )
        if since_timestamp is not None:
            statement = statement.where(
                PipelineRunEventModel.occurred_at >= since_timestamp,
            )

        rows = (
            self._session.execute(
                statement.order_by(
                    desc(PipelineRunEventModel.occurred_at),
                    desc(PipelineRunEventModel.seq),
                ).limit(max(limit, 1) + 1),
            )
            .scalars()
            .all()
        )
        has_more = len(rows) > max(limit, 1)
        selected_rows = rows[: max(limit, 1)]
        events = [
            self._serialize_event_row(row=row, source_id=source_id)
            for row in selected_rows
        ]

        return {
            "source_id": str(source_id),
            "run_id": selected_run_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "events": events,
            "total": len(events),
            "has_more": has_more,
        }


__all__ = ["SourceWorkflowMonitorEventsMixin"]
