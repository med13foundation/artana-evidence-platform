"""Write-side helpers for pipeline trace events, timing, ownership, and cost."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.application.services._artana_observability_queries import list_snapshot_rows
from src.application.services._pipeline_run_trace_parsing import (
    parse_cost_summary,
    parse_timing_summary,
)
from src.application.services._pipeline_run_trace_run_id_loader import (
    _PipelineRunTraceRunIdLoader,
)
from src.application.services._source_workflow_monitor_shared import (
    coerce_json_object,
    normalize_optional_string,
)
from src.domain.entities.pipeline_run_event import (
    PipelineRunEvent,
    resolve_pipeline_run_event_level,
    resolve_pipeline_run_event_scope_kind,
)
from src.models.database.user_data_source import UserDataSourceModel
from src.type_definitions.data_sources import (
    PipelineRunCostMetadata,
    PipelineRunOwnerMetadata,
    PipelineRunTimingMetadata,
    PipelineStageTimingMetadata,
)
from src.type_definitions.json_utils import as_float

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.application.services._artana_observability_models import _RunSnapshotRow
    from src.domain.repositories.pipeline_run_event_repository import (
        PipelineRunEventRepository,
    )
    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]

logger = logging.getLogger(__name__)
_MAX_SCOPE_ID_LENGTH = 255
_TRUNCATED_SCOPE_ID_HASH_LENGTH = 16


class PipelineRunTraceService(_PipelineRunTraceRunIdLoader):
    """Persist pipeline trace events and derive owner/timing/cost summaries."""

    def __init__(
        self,
        session: Session,
        *,
        event_repository: PipelineRunEventRepository,
    ) -> None:
        self._session = session
        self._events = event_repository

    def record_event(  # noqa: PLR0913
        self,
        *,
        research_space_id: UUID,
        source_id: UUID,
        pipeline_run_id: str,
        event_type: str,
        scope_kind: str,
        message: str,
        occurred_at: datetime | None = None,
        stage: str | None = None,
        scope_id: str | None = None,
        level: str = "info",
        status: str | None = None,
        agent_kind: str | None = None,
        agent_run_id: str | None = None,
        error_code: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        duration_ms: int | None = None,
        queue_wait_ms: int | None = None,
        timeout_budget_ms: int | None = None,
        payload: JSONObject | None = None,
    ) -> PipelineRunEvent:
        normalized_scope_id, full_scope_id = self._normalize_scope_id(scope_id)
        payload_to_store = dict(payload or {})
        if full_scope_id is not None and "scope_id_full" not in payload_to_store:
            payload_to_store["scope_id_full"] = full_scope_id
        return self._events.append(
            PipelineRunEvent(
                research_space_id=research_space_id,
                source_id=source_id,
                pipeline_run_id=pipeline_run_id,
                event_type=event_type,
                stage=stage,
                scope_kind=resolve_pipeline_run_event_scope_kind(scope_kind),
                scope_id=normalized_scope_id,
                level=resolve_pipeline_run_event_level(level),
                status=status,
                agent_kind=agent_kind,
                agent_run_id=agent_run_id,
                error_code=error_code,
                message=message,
                occurred_at=occurred_at or datetime.now(UTC),
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                queue_wait_ms=queue_wait_ms,
                timeout_budget_ms=timeout_budget_ms,
                payload=payload_to_store,
            ),
        )

    @staticmethod
    def _normalize_scope_id(scope_id: str | None) -> tuple[str | None, str | None]:
        normalized_scope_id = normalize_optional_string(scope_id)
        if normalized_scope_id is None:
            return None, None
        if len(normalized_scope_id) <= _MAX_SCOPE_ID_LENGTH:
            return normalized_scope_id, None

        digest = hashlib.sha256(normalized_scope_id.encode("utf-8")).hexdigest()[
            :_TRUNCATED_SCOPE_ID_HASH_LENGTH
        ]
        suffix = f"...#{digest}"
        prefix_length = max(_MAX_SCOPE_ID_LENGTH - len(suffix), 0)
        truncated_scope_id = f"{normalized_scope_id[:prefix_length]}{suffix}"
        return truncated_scope_id, normalized_scope_id

    def resolve_run_owner(
        self,
        *,
        source_id: UUID,
        triggered_by_user_id: UUID | None,
    ) -> PipelineRunOwnerMetadata:
        if triggered_by_user_id is not None:
            return PipelineRunOwnerMetadata(
                run_owner_user_id=str(triggered_by_user_id),
                run_owner_source="triggered_by",
            )

        source = self._session.get(UserDataSourceModel, str(source_id))
        owner_id = source.owner_id if source is not None else None
        if isinstance(owner_id, str) and owner_id.strip():
            return PipelineRunOwnerMetadata(
                run_owner_user_id=owner_id.strip(),
                run_owner_source="source_owner",
            )
        return PipelineRunOwnerMetadata(
            run_owner_user_id=None,
            run_owner_source="system",
        )

    @staticmethod
    def build_stage_timing(  # noqa: PLR0913
        *,
        stage: str,
        status: str | None,
        started_at: datetime | None,
        completed_at: datetime | None,
        duration_ms: int | None,
        queue_wait_ms: int | None = None,
        timeout_budget_ms: int | None = None,
    ) -> PipelineStageTimingMetadata:
        return PipelineStageTimingMetadata(
            stage=stage,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            queue_wait_ms=queue_wait_ms,
            timeout_budget_ms=timeout_budget_ms,
        )

    @staticmethod
    def merge_timing_summary(
        *,
        existing_summary: object,
        stage_timing: PipelineStageTimingMetadata,
        total_duration_ms: int | None = None,
    ) -> PipelineRunTimingMetadata:
        existing_payload = (
            coerce_json_object(existing_summary)
            if isinstance(existing_summary, dict)
            else {}
        )
        raw_stage_timings = existing_payload.get("stage_timings")
        stage_timings_payload = (
            coerce_json_object(raw_stage_timings)
            if isinstance(raw_stage_timings, dict)
            else {}
        )
        merged_stage_timings: dict[str, PipelineStageTimingMetadata] = {}
        for stage_name, raw_value in stage_timings_payload.items():
            if not isinstance(raw_value, dict):
                continue
            try:
                merged_stage_timings[str(stage_name)] = (
                    PipelineStageTimingMetadata.model_validate(raw_value)
                )
            except ValueError as exc:
                logger.warning(
                    "Skipping invalid persisted stage timing metadata",
                    extra={"stage_name": stage_name, "error": str(exc)},
                )
                continue
        merged_stage_timings[stage_timing.stage] = stage_timing
        existing_total = existing_payload.get("total_duration_ms")
        resolved_total_duration_ms = total_duration_ms
        if resolved_total_duration_ms is None and isinstance(existing_total, int):
            resolved_total_duration_ms = max(existing_total, 0)
        return PipelineRunTimingMetadata(
            total_duration_ms=resolved_total_duration_ms,
            stage_timings=merged_stage_timings,
        )

    def resolve_cost_summary(
        self,
        *,
        research_space_id: UUID,
        pipeline_run_id: str,
        additional_stage_costs_usd: dict[str, float] | None = None,
    ) -> PipelineRunCostMetadata:
        stage_run_ids = self._load_stage_run_ids(
            research_space_id=str(research_space_id),
            pipeline_run_id=pipeline_run_id,
        )
        candidate_run_ids = sorted(
            {run_id for run_ids in stage_run_ids.values() for run_id in run_ids},
        )
        if not candidate_run_ids:
            return PipelineRunCostMetadata()

        snapshots = self._load_snapshots_by_run_id(candidate_run_ids)
        kernel_event_costs = self._load_kernel_event_costs_by_run_id(candidate_run_ids)

        stage_costs: dict[str, float] = {}
        for stage_name, run_ids in stage_run_ids.items():
            stage_cost = sum(
                self._resolve_run_cost_usd(
                    run_id=run_id,
                    snapshots=snapshots,
                    kernel_event_costs=kernel_event_costs,
                )
                for run_id in run_ids
            )
            stage_costs[stage_name] = round(stage_cost, 8)

        for stage_name, raw_cost in (additional_stage_costs_usd or {}).items():
            normalized_stage_name = normalize_optional_string(stage_name)
            if normalized_stage_name is None:
                continue
            stage_costs[normalized_stage_name] = round(max(float(raw_cost), 0.0), 8)

        total_cost = round(sum(stage_costs.values()), 8)
        return PipelineRunCostMetadata(
            total_cost_usd=total_cost,
            stage_costs_usd=stage_costs,
            linked_run_ids=candidate_run_ids,
        )

    @staticmethod
    def _resolve_run_cost_usd(
        *,
        run_id: str,
        snapshots: dict[str, _RunSnapshotRow],
        kernel_event_costs: dict[str, float],
    ) -> float:
        snapshot_cost = 0.0
        snapshot = snapshots.get(run_id)
        if snapshot is not None:
            snapshot_cost = max(snapshot.model_cost_total, 0.0)
        if snapshot_cost > 0.0:
            return snapshot_cost
        return max(kernel_event_costs.get(run_id, 0.0), 0.0)

    def _load_snapshots_by_run_id(
        self,
        candidate_run_ids: list[str],
    ) -> dict[str, _RunSnapshotRow]:
        snapshots_by_run_id: dict[str, _RunSnapshotRow] = {}
        for run_id in candidate_run_ids:
            snapshot_rows = list_snapshot_rows(
                self._session,
                run_id=run_id,
                tenant_id=None,
                status=None,
                updated_since=None,
            )
            if not snapshot_rows:
                continue
            snapshots_by_run_id[run_id] = snapshot_rows[0]
        return snapshots_by_run_id

    def _load_kernel_event_costs_by_run_id(
        self,
        candidate_run_ids: list[str],
    ) -> dict[str, float]:
        if not candidate_run_ids:
            return {}
        try:
            rows = (
                self._session.execute(
                    text(
                        """
                        SELECT
                            run_id,
                            SUM(
                                COALESCE(
                                    NULLIF((payload_json::jsonb)->>'cost_usd', '')::double precision,
                                    0.0
                                )
                            ) AS total_cost_usd
                        FROM artana.kernel_events
                        WHERE run_id = ANY(:run_ids)
                          AND event_type = 'model_terminal'
                        GROUP BY run_id
                        """,
                    ),
                    {"run_ids": candidate_run_ids},
                )
                .mappings()
                .all()
            )
        except SQLAlchemyError as exc:
            logger.debug(
                "Artana kernel_events cost query unavailable; falling back to snapshots only. %s",
                exc,
            )
            return {}

        costs_by_run_id: dict[str, float] = {}
        for row in rows:
            run_id = normalize_optional_string(row.get("run_id"))
            if run_id is None:
                continue
            total_cost = as_float(row.get("total_cost_usd"))
            if total_cost is None or total_cost <= 0.0:
                continue
            costs_by_run_id[run_id] = round(total_cost, 8)
        return costs_by_run_id

    def record_cost_event_if_available(
        self,
        *,
        research_space_id: UUID,
        source_id: UUID,
        pipeline_run_id: str,
        additional_stage_costs_usd: dict[str, float] | None = None,
    ) -> PipelineRunCostMetadata:
        cost_summary = self.resolve_cost_summary(
            research_space_id=research_space_id,
            pipeline_run_id=pipeline_run_id,
            additional_stage_costs_usd=additional_stage_costs_usd,
        )
        if cost_summary.total_cost_usd > 0 or cost_summary.linked_run_ids:
            self.record_event(
                research_space_id=research_space_id,
                source_id=source_id,
                pipeline_run_id=pipeline_run_id,
                event_type="cost_snapshot",
                stage=None,
                scope_kind="cost",
                message=(
                    "Captured direct AI/tool cost snapshot "
                    f"(${cost_summary.total_cost_usd:.4f} USD)."
                ),
                status="captured",
                payload=cost_summary.to_json_object(),
            )
        return cost_summary


__all__ = [
    "PipelineRunTraceService",
    "parse_cost_summary",
    "parse_timing_summary",
]
