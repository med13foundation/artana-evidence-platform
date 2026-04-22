"""Artana run-progress helpers for source workflow monitor."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ._source_workflow_monitor_shared import (
    coerce_json_object,
    normalize_optional_string,
)

if TYPE_CHECKING:
    from src.application.services.ports.run_progress_port import (
        RunProgressPort,
        RunProgressSnapshot,
    )
    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub


_ARTANA_STAGE_ORDER: tuple[str, ...] = (
    "pipeline",
    "enrichment",
    "extraction",
    "graph",
)
_PIPELINE_STAGE_ORDER: tuple[str, ...] = (
    "ingestion",
    "enrichment",
    "extraction",
    "graph",
)
_GRAPH_RUN_ID_PREFIXES: tuple[str, ...] = (
    "graph:",
    "graph_connection:",
    "graph_search:",
)
_GRAPH_RUN_ID_FIELDS: tuple[str, ...] = (
    "graph_agent_run_id",
    "graph_connection_run_id",
    "graph_run_id",
)
_FULL_PROGRESS_PERCENT = 100
_NEAR_COMPLETE_PROGRESS_PERCENT = 99
_PIPELINE_STATUS_ALIASES: dict[str, str] = {
    "running": "running",
    "active": "running",
    "in_progress": "running",
    "in-progress": "running",
    "completed": "completed",
    "complete": "completed",
    "success": "completed",
    "succeeded": "completed",
    "failed": "failed",
    "failure": "failed",
    "error": "failed",
    "queued": "queued",
    "pending": "queued",
    "retrying": "retrying",
    "skipped": "skipped",
    "cancelled": "cancelled",
}
_ACTIVE_PIPELINE_PROGRESS_STATUSES: frozenset[str] = frozenset(
    {"queued", "retrying", "running"},
)
_TERMINAL_PIPELINE_PROGRESS_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "partial"},
)


class SourceWorkflowMonitorProgressMixin:
    """Run-progress shaping helpers for source workflow monitoring."""

    _run_progress: RunProgressPort | None

    def _build_artana_progress(  # noqa: PLR0913 - explicit monitor payload shaping
        self,
        *,
        tenant_id: str,
        selected_run_id: str | None,
        selected_run_payload: JSONObject | None = None,
        documents: list[JSONObject],
        extraction_rows: list[JSONObject],
        relation_rows: list[JSONObject],
    ) -> JSONObject:
        stage_candidates = self._resolve_stage_run_candidates(
            selected_run_id=selected_run_id,
            documents=documents,
            extraction_rows=extraction_rows,
            relation_rows=relation_rows,
        )

        payload: JSONObject = {}
        for stage_name, candidates in stage_candidates.items():
            snapshot = self._find_first_progress_snapshot(
                candidates,
                tenant_id=tenant_id,
            )
            if stage_name == "pipeline":
                resolved_pipeline_payload = (
                    self._resolve_pipeline_stage_progress_payload(
                        selected_run_payload=selected_run_payload,
                        snapshot=snapshot,
                        candidate_run_ids=candidates,
                    )
                )
                if resolved_pipeline_payload is not None:
                    payload[stage_name] = resolved_pipeline_payload
                    continue
            elif snapshot is not None:
                payload[stage_name] = self._snapshot_to_payload(
                    stage=stage_name,
                    snapshot=snapshot,
                    candidate_run_ids=candidates,
                )
                continue

            payload[stage_name] = self._empty_stage_progress_payload(
                stage=stage_name,
                candidate_run_ids=candidates,
            )
        return payload

    def _resolve_pipeline_stage_progress_payload(
        self,
        *,
        selected_run_payload: JSONObject | None,
        snapshot: RunProgressSnapshot | None,
        candidate_run_ids: list[str],
    ) -> JSONObject | None:
        fallback_payload = self._pipeline_stage_fallback_payload(
            selected_run_payload=selected_run_payload,
            candidate_run_ids=candidate_run_ids,
        )
        if snapshot is None:
            return fallback_payload

        snapshot_payload = self._snapshot_to_payload(
            stage="pipeline",
            snapshot=snapshot,
            candidate_run_ids=candidate_run_ids,
        )
        if fallback_payload is None:
            return snapshot_payload

        fallback_status = _normalize_pipeline_status(fallback_payload.get("status"))
        snapshot_status = _normalize_pipeline_status(snapshot.status)
        if (
            fallback_status in _TERMINAL_PIPELINE_PROGRESS_STATUSES
            and snapshot_status in _ACTIVE_PIPELINE_PROGRESS_STATUSES
        ):
            return fallback_payload
        return snapshot_payload

    def _resolve_stage_run_candidates(  # noqa: PLR0913 - explicit stage mapping
        self,
        *,
        selected_run_id: str | None,
        documents: list[JSONObject],
        extraction_rows: list[JSONObject],
        relation_rows: list[JSONObject],
    ) -> dict[str, list[str]]:
        stage_candidates: dict[str, list[str]] = {
            stage_name: [] for stage_name in _ARTANA_STAGE_ORDER
        }
        self._append_unique_run_id(stage_candidates["pipeline"], selected_run_id)

        for document in documents:
            document_metadata = coerce_json_object(document.get("metadata"))
            self._append_unique_run_id(
                stage_candidates["enrichment"],
                document.get("enrichment_agent_run_id"),
            )
            self._append_unique_run_id(
                stage_candidates["enrichment"],
                document_metadata.get("content_enrichment_agent_run_id"),
            )
            self._append_unique_run_id(
                stage_candidates["extraction"],
                document.get("extraction_agent_run_id"),
            )
            self._append_unique_run_id(
                stage_candidates["extraction"],
                document_metadata.get("entity_recognition_run_id"),
            )
            self._append_unique_run_id(
                stage_candidates["extraction"],
                document_metadata.get("extraction_run_id"),
            )

        for extraction in extraction_rows:
            extraction_metadata = coerce_json_object(extraction.get("metadata"))
            self._append_unique_run_id(
                stage_candidates["extraction"],
                extraction_metadata.get("extraction_run_id"),
            )
            for field_name in _GRAPH_RUN_ID_FIELDS:
                self._append_graph_run_id(
                    stage_candidates["graph"],
                    extraction_metadata.get(field_name),
                )

        for relation in relation_rows:
            relation_payload = coerce_json_object(relation)
            relation_metadata = coerce_json_object(relation_payload.get("metadata"))
            self._append_graph_run_id(
                stage_candidates["graph"],
                relation_payload.get("agent_run_id"),
            )
            for field_name in _GRAPH_RUN_ID_FIELDS:
                self._append_graph_run_id(
                    stage_candidates["graph"],
                    relation_payload.get(field_name),
                )
                self._append_graph_run_id(
                    stage_candidates["graph"],
                    relation_metadata.get(field_name),
                )

        return stage_candidates

    @staticmethod
    def _append_unique_run_id(bucket: list[str], value: object) -> None:
        run_id = normalize_optional_string(value)
        if run_id is None or run_id in bucket:
            return
        bucket.append(run_id)

    @staticmethod
    def _append_graph_run_id(bucket: list[str], value: object) -> None:
        run_id = normalize_optional_string(value)
        if run_id is None:
            return
        normalized = run_id.lower()
        if not normalized.startswith(_GRAPH_RUN_ID_PREFIXES):
            return
        if run_id in bucket:
            return
        bucket.append(run_id)

    def _find_first_progress_snapshot(
        self,
        candidates: list[str],
        *,
        tenant_id: str,
    ) -> RunProgressSnapshot | None:
        if self._run_progress is None:
            return None
        for run_id in candidates:
            snapshot = self._run_progress.get_run_progress(
                run_id=run_id,
                tenant_id=tenant_id,
            )
            if snapshot is not None:
                return snapshot
        return None

    def _pipeline_stage_fallback_payload(
        self,
        *,
        selected_run_payload: JSONObject | None,
        candidate_run_ids: list[str],
    ) -> JSONObject | None:
        if selected_run_payload is None:
            return None
        run_status = _normalize_pipeline_status(selected_run_payload.get("status"))
        if run_status is None:
            return None
        stage_statuses = coerce_json_object(selected_run_payload.get("stage_statuses"))
        completed_stages = _resolve_completed_pipeline_stages(stage_statuses)
        return {
            "stage": "pipeline",
            "run_id": normalize_optional_string(selected_run_payload.get("run_id"))
            or (candidate_run_ids[0] if candidate_run_ids else None),
            "status": run_status,
            "percent": _resolve_pipeline_percent(
                status=run_status,
                stage_statuses=stage_statuses,
            ),
            "current_stage": _resolve_pipeline_current_stage(
                status=run_status,
                stage_statuses=stage_statuses,
                completed_stages=completed_stages,
            ),
            "completed_stages": completed_stages,
            "started_at": _to_iso_timestamp(
                selected_run_payload.get("started_at"),
            )
            or _to_iso_timestamp(selected_run_payload.get("triggered_at")),
            "updated_at": _to_iso_timestamp(
                selected_run_payload.get("completed_at"),
            )
            or _to_iso_timestamp(selected_run_payload.get("started_at"))
            or _to_iso_timestamp(selected_run_payload.get("triggered_at")),
            "eta_seconds": None,
            "candidate_run_ids": list(candidate_run_ids),
        }

    def _snapshot_to_payload(
        self,
        *,
        stage: str,
        snapshot: RunProgressSnapshot,
        candidate_run_ids: list[str],
    ) -> JSONObject:
        return {
            "stage": stage,
            "run_id": snapshot.run_id,
            "status": snapshot.status,
            "percent": snapshot.percent,
            "current_stage": snapshot.current_stage,
            "completed_stages": list(snapshot.completed_stages),
            "started_at": (
                snapshot.started_at.isoformat()
                if snapshot.started_at is not None
                else None
            ),
            "updated_at": (
                snapshot.updated_at.isoformat()
                if snapshot.updated_at is not None
                else None
            ),
            "eta_seconds": snapshot.eta_seconds,
            "candidate_run_ids": list(candidate_run_ids),
        }

    @staticmethod
    def _empty_stage_progress_payload(
        *,
        stage: str,
        candidate_run_ids: list[str],
    ) -> JSONObject:
        selected_run_id = candidate_run_ids[0] if candidate_run_ids else None
        return {
            "stage": stage,
            "run_id": selected_run_id,
            "status": None,
            "percent": None,
            "current_stage": None,
            "completed_stages": [],
            "started_at": None,
            "updated_at": None,
            "eta_seconds": None,
            "candidate_run_ids": list(candidate_run_ids),
        }


def _resolve_completed_pipeline_stages(stage_statuses: JSONObject) -> list[str]:
    completed: list[str] = []
    for stage_name in _PIPELINE_STAGE_ORDER:
        normalized = _normalize_pipeline_status(stage_statuses.get(stage_name))
        if normalized in {"completed", "skipped"}:
            completed.append(stage_name)
    return completed


def _resolve_pipeline_current_stage(  # noqa: PLR0911
    *,
    status: str,
    stage_statuses: JSONObject,
    completed_stages: list[str],
) -> str | None:
    if status == "completed":
        return completed_stages[-1] if completed_stages else None
    if status == "failed":
        for stage_name in _PIPELINE_STAGE_ORDER:
            if _normalize_pipeline_status(stage_statuses.get(stage_name)) == "failed":
                return stage_name
        return completed_stages[-1] if completed_stages else None
    if status in {"queued", "retrying"}:
        return _PIPELINE_STAGE_ORDER[0] if _PIPELINE_STAGE_ORDER else None
    for stage_name in _PIPELINE_STAGE_ORDER:
        stage_status = _normalize_pipeline_status(stage_statuses.get(stage_name))
        if stage_status in {"running", "queued", "retrying"}:
            return stage_name
    for stage_name in _PIPELINE_STAGE_ORDER:
        stage_status = _normalize_pipeline_status(stage_statuses.get(stage_name))
        if stage_status not in {"completed", "skipped"}:
            return stage_name
    return completed_stages[-1] if completed_stages else None


def _resolve_pipeline_percent(*, status: str, stage_statuses: JSONObject) -> int:
    if status == "completed":
        return _FULL_PROGRESS_PERCENT
    if status in {"queued", "retrying"}:
        return 0
    total = len(_PIPELINE_STAGE_ORDER)
    if total == 0:
        return 0
    completed_count = len(_resolve_completed_pipeline_stages(stage_statuses))
    if completed_count <= 0:
        return 0
    percent = int((completed_count * _FULL_PROGRESS_PERCENT) / total)
    if (
        status in {"running", "failed", "cancelled"}
        and percent >= _FULL_PROGRESS_PERCENT
    ):
        return _NEAR_COMPLETE_PROGRESS_PERCENT
    return percent


def _normalize_pipeline_status(raw_value: object) -> str | None:
    normalized = normalize_optional_string(raw_value)
    if normalized is None:
        return None
    status_key = normalized.lower()
    return _PIPELINE_STATUS_ALIASES.get(status_key, status_key)


def _to_iso_timestamp(raw_value: object) -> str | None:
    if isinstance(raw_value, datetime):
        return raw_value.isoformat()
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


__all__ = ["SourceWorkflowMonitorProgressMixin"]
