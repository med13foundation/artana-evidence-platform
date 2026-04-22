"""Developer-facing Artana observability read models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.application.services._artana_observability_models import (
    _RunResolution,
    _RunSnapshotRow,
)
from src.application.services._artana_observability_payloads import (
    _resolve_budget_warning,
    _resolve_unknown_outcome_alert,
    build_alerts,
    build_list_counters,
    build_list_item,
    build_trace_payload,
    emit_alert_logs,
)
from src.application.services._artana_observability_queries import (
    get_snapshot_row,
    list_snapshot_rows,
    load_linked_records,
    resolve_space_run,
)
from src.application.services._artana_observability_support import (
    _has_drift_alert,
    _matches_query,
    _normalize_snapshot_status_filter,
    _require_run_id,
    _string_list,
)
from src.application.services._source_workflow_monitor_shared import (
    normalize_optional_string,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.application.services.ports.agent_run_state_port import AgentRunStatePort
    from src.application.services.ports.artana_run_trace_port import (
        ArtanaRunTracePort,
        ArtanaRunTraceRecord,
    )
    from src.type_definitions.common import JSONObject
    from src.type_definitions.data_sources import AgentRunTableSummary
else:
    Session = object
    JSONObject = dict[str, object]


class ArtanaObservabilityService:
    """Compose run traces, linked research records, and alert derivation."""

    def __init__(
        self,
        session: Session,
        *,
        run_trace: ArtanaRunTracePort | None = None,
        raw_state: AgentRunStatePort | None = None,
    ) -> None:
        self._session = session
        self._run_trace = run_trace
        self._raw_state = raw_state

    def get_admin_run_trace(self, *, run_id: str) -> JSONObject:
        normalized_run_id = _require_run_id(run_id)
        snapshot = self._get_snapshot_row(run_id=normalized_run_id)
        if snapshot is None:
            msg = f"Artana run '{normalized_run_id}' not found."
            raise LookupError(msg)
        trace = self._require_trace(
            run_id=normalized_run_id,
            tenant_id=snapshot.tenant_id,
        )
        linked_records = self._load_linked_records(
            run_id=trace.run_id,
            research_space_id=snapshot.tenant_id,
        )
        alerts = self._build_alerts(
            trace=trace,
            fallback_snapshot=snapshot,
            now=datetime.now(UTC),
        )
        self._emit_alert_logs(
            run_id=trace.run_id,
            space_id=snapshot.tenant_id,
            alerts=alerts,
            linked_records=linked_records,
        )
        raw_tables = (
            self._raw_state.get_run_table_summaries(trace.run_id)
            if self._raw_state is not None
            else []
        )
        return self._build_trace_payload(
            requested_run_id=normalized_run_id,
            trace=trace,
            candidate_run_ids=[trace.run_id],
            alerts=alerts,
            linked_records=linked_records,
            raw_tables=raw_tables,
        )

    def get_space_run_trace(
        self,
        *,
        space_id: UUID,
        run_id: str,
    ) -> JSONObject:
        normalized_run_id = _require_run_id(run_id)
        requested_space_id = str(space_id)
        resolution = self._resolve_space_run(
            research_space_id=requested_space_id,
            requested_run_id=normalized_run_id,
        )
        if resolution is None:
            msg = (
                f"Artana run or pipeline run '{normalized_run_id}' not found in this "
                "research space."
            )
            raise LookupError(msg)
        trace = self._require_trace(
            run_id=resolution.resolved_run_id,
            tenant_id=requested_space_id,
        )
        linked_records = self._load_linked_records(
            run_id=trace.run_id,
            research_space_id=requested_space_id,
        )
        alerts = self._build_alerts(
            trace=trace,
            fallback_snapshot=resolution.snapshot,
            now=datetime.now(UTC),
        )
        self._emit_alert_logs(
            run_id=trace.run_id,
            space_id=requested_space_id,
            alerts=alerts,
            linked_records=linked_records,
        )
        return self._build_trace_payload(
            requested_run_id=normalized_run_id,
            trace=trace,
            candidate_run_ids=resolution.candidate_run_ids,
            alerts=alerts,
            linked_records=linked_records,
            raw_tables=None,
        )

    def list_admin_runs(  # noqa: PLR0913 - explicit filters are intentional
        self,
        *,
        q: str | None,
        status: str | None,
        space_id: str | None,
        source_type: str | None,
        alert_code: str | None,
        since_hours: int | None,
        page: int,
        per_page: int,
    ) -> JSONObject:
        normalized_space_id = normalize_optional_string(space_id)
        normalized_status = _normalize_snapshot_status_filter(status)
        updated_since = (
            datetime.now(UTC) - timedelta(hours=since_hours)
            if isinstance(since_hours, int) and since_hours > 0
            else None
        )
        snapshot_rows = self._list_snapshot_rows(
            run_id=None,
            tenant_id=normalized_space_id,
            status=normalized_status,
            updated_since=updated_since,
        )
        items: list[JSONObject] = []
        now = datetime.now(UTC)
        normalized_query = (q or "").strip().lower()
        normalized_source_type = (source_type or "").strip().lower()
        normalized_alert_code = normalize_optional_string(alert_code)

        for snapshot in snapshot_rows:
            trace = (
                self._require_trace(
                    run_id=snapshot.run_id,
                    tenant_id=snapshot.tenant_id,
                )
                if self._run_trace is not None
                else None
            )
            linked_records = self._load_linked_records(
                run_id=snapshot.run_id,
                research_space_id=snapshot.tenant_id,
            )
            alerts = self._build_alerts(
                trace=trace,
                fallback_snapshot=snapshot,
                now=now,
            )
            item = self._build_list_item(
                snapshot=snapshot,
                trace=trace,
                linked_records=linked_records,
                alerts=alerts,
            )
            if normalized_source_type and (
                item.get("source_type") != normalized_source_type
            ):
                continue
            alert_codes = _string_list(item.get("alert_codes"))
            if normalized_alert_code and normalized_alert_code not in alert_codes:
                continue
            if normalized_query and not _matches_query(
                item=item,
                query=normalized_query,
            ):
                continue
            items.append(item)

        counters = self._build_list_counters(items)
        total = len(items)
        page_value = max(page, 1)
        per_page_value = max(per_page, 1)
        offset = (page_value - 1) * per_page_value
        return {
            "runs": items[offset : offset + per_page_value],
            "total": total,
            "page": page_value,
            "per_page": per_page_value,
            "counters": counters,
        }

    def _require_trace(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> ArtanaRunTraceRecord:
        if self._run_trace is None:
            msg = "Artana observability reader is unavailable in this environment."
            raise RuntimeError(msg)
        trace = self._run_trace.get_run_trace(
            run_id=run_id,
            tenant_id=tenant_id,
        )
        if trace is None:
            msg = f"Artana trace '{run_id}' not found."
            raise LookupError(msg)
        return trace

    def _get_snapshot_row(self, *, run_id: str) -> _RunSnapshotRow | None:
        return get_snapshot_row(self._session, run_id=run_id)

    def _list_snapshot_rows(
        self,
        *,
        run_id: str | None,
        tenant_id: str | None,
        status: str | None,
        updated_since: datetime | None,
    ) -> list[_RunSnapshotRow]:
        return list_snapshot_rows(
            self._session,
            run_id=run_id,
            tenant_id=tenant_id,
            status=status,
            updated_since=updated_since,
        )

    def _resolve_space_run(
        self,
        *,
        research_space_id: str,
        requested_run_id: str,
    ) -> _RunResolution | None:
        return resolve_space_run(
            self._session,
            research_space_id=research_space_id,
            requested_run_id=requested_run_id,
        )

    def _load_linked_records(
        self,
        *,
        run_id: str,
        research_space_id: str | None,
    ) -> list[JSONObject]:
        return load_linked_records(
            self._session,
            run_id=run_id,
            research_space_id=research_space_id,
        )

    def _build_trace_payload(  # noqa: PLR0913 - explicit response shape is intentional
        self,
        *,
        requested_run_id: str,
        trace: ArtanaRunTraceRecord,
        candidate_run_ids: list[str],
        alerts: list[JSONObject],
        linked_records: list[JSONObject],
        raw_tables: list[AgentRunTableSummary] | None,
    ) -> JSONObject:
        return build_trace_payload(
            requested_run_id=requested_run_id,
            trace=trace,
            candidate_run_ids=candidate_run_ids,
            alerts=alerts,
            linked_records=linked_records,
            raw_tables=raw_tables,
        )

    def _build_alerts(
        self,
        *,
        trace: ArtanaRunTraceRecord | None,
        fallback_snapshot: _RunSnapshotRow | None,
        now: datetime,
    ) -> list[JSONObject]:
        return build_alerts(
            trace=trace,
            fallback_snapshot=fallback_snapshot,
            now=now,
        )

    def _emit_alert_logs(
        self,
        *,
        run_id: str,
        space_id: str,
        alerts: list[JSONObject],
        linked_records: list[JSONObject],
    ) -> None:
        emit_alert_logs(
            run_id=run_id,
            space_id=space_id,
            alerts=alerts,
            linked_records=linked_records,
        )

    def _build_list_item(
        self,
        *,
        snapshot: _RunSnapshotRow,
        trace: ArtanaRunTraceRecord | None,
        linked_records: list[JSONObject],
        alerts: list[JSONObject],
    ) -> JSONObject:
        return build_list_item(
            snapshot=snapshot,
            trace=trace,
            linked_records=linked_records,
            alerts=alerts,
        )

    @staticmethod
    def _build_list_counters(items: list[JSONObject]) -> dict[str, int]:
        return build_list_counters(items)


__all__ = [
    "ArtanaObservabilityService",
    "_RunResolution",
    "_RunSnapshotRow",
    "_has_drift_alert",
    "_resolve_budget_warning",
    "_resolve_unknown_outcome_alert",
]
