"""Artana-kernel-backed lifecycle and artifact adapters for graph-harness."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, select

from .artana_store_records import (
    _fallback_events,
    _kernel_event_record,
    _summary_event_payload,
)
from .models import HarnessRunModel
from .run_registry import (
    HarnessRunEventRecord,
    HarnessRunProgressRecord,
    HarnessRunRecord,
    HarnessRunRegistry,
    _default_message_for_status,
    _default_phase_for_status,
    _default_progress_percent,
)
from .sqlalchemy_unit_of_work import commit_or_flush, run_after_commit_or_now

if TYPE_CHECKING:
    from uuid import UUID

    from artana.events import RunSummaryPayload
    from artana_evidence_api.types.common import JSONObject
    from sqlalchemy.orm import Session

    from .composition import GraphHarnessKernelRuntime


_RUN_STATE_SUMMARY = "harness::run_state"
_PROGRESS_SUMMARY = "harness::progress"
_WORKSPACE_SUMMARY = "harness::workspace"
_ARTIFACT_PREFIX = "artifact::"
_EVENT_PREFIX = "event::"
_FAST_READ_TIMEOUT_SECONDS = float(
    os.getenv(
        "ARTANA_EVIDENCE_API_FAST_SUMMARY_READ_TIMEOUT_SECONDS",
        "10.0",
    ).strip()
    or "10.0",
)
_SUMMARY_WRITE_MAX_ATTEMPTS = int(
    os.getenv(
        "ARTANA_EVIDENCE_API_SUMMARY_WRITE_MAX_ATTEMPTS",
        "5",
    ).strip()
    or "5",
)
_SUMMARY_WRITE_RETRY_DELAY_SECONDS = float(
    os.getenv(
        "ARTANA_EVIDENCE_API_SUMMARY_WRITE_RETRY_DELAY_SECONDS",
        "0.25",
    ).strip()
    or "0.25",
)
_PROGRESS_PERSISTENCE_BACKOFF_SECONDS = float(
    os.getenv(
        "ARTANA_EVIDENCE_API_PROGRESS_PERSISTENCE_BACKOFF_SECONDS",
        "30.0",
    ).strip()
    or "30.0",
)
_LOGGER = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _summary_payload(summary: RunSummaryPayload | None) -> JSONObject | None:
    if summary is None:
        return None
    try:
        payload = json.loads(summary.summary_json)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _payload_string(
    payload: JSONObject,
    key: str,
    *,
    default: str,
) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else default


def _payload_float(
    payload: JSONObject,
    key: str,
    *,
    default: float,
) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return float(value)


def _payload_int(
    payload: JSONObject,
    key: str,
    *,
    default: int,
) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


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




def _step_key(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _append_run_summary_with_retry(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run_id: str,
    tenant_id: str,
    summary_type: str,
    summary_json: str,
    step_key: str,
    parent_step_key: str | None = None,
) -> int:
    last_error: TimeoutError | None = None
    for attempt in range(1, _SUMMARY_WRITE_MAX_ATTEMPTS + 1):
        try:
            return runtime.append_run_summary(
                run_id=run_id,
                tenant_id=tenant_id,
                summary_type=summary_type,
                summary_json=summary_json,
                step_key=step_key,
                parent_step_key=parent_step_key,
            )
        except TimeoutError as exc:
            last_error = exc
            if attempt >= _SUMMARY_WRITE_MAX_ATTEMPTS:
                break
            time.sleep(_SUMMARY_WRITE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1)))
    if last_error is not None:
        raise last_error
    raise RuntimeError("summary write retry exhausted without a timeout cause")


def _append_run_summary_once(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run_id: str,
    tenant_id: str,
    summary_type: str,
    summary_json: str,
    step_key: str,
    parent_step_key: str | None = None,
) -> int:
    return runtime.append_run_summary(
        run_id=run_id,
        tenant_id=tenant_id,
        summary_type=summary_type,
        summary_json=summary_json,
        step_key=step_key,
        parent_step_key=parent_step_key,
    )
    raise TimeoutError("Run summary write failed without a captured timeout error.")


def _summary_updated_at(payload: JSONObject | None) -> datetime | None:
    if not isinstance(payload, dict):
        return None
    return _parse_timestamp(payload.get("updated_at"))


def _catalog_progress_record(
    *,
    run: HarnessRunRecord,
    current: HarnessRunProgressRecord | None = None,
    updated_at: datetime | None = None,
) -> HarnessRunProgressRecord:
    if current is None and run.status.strip().lower() == "queued":
        default_progress = _default_progress_record(run)
        return HarnessRunProgressRecord(
            space_id=default_progress.space_id,
            run_id=default_progress.run_id,
            status=default_progress.status,
            phase=default_progress.phase,
            message=default_progress.message,
            progress_percent=default_progress.progress_percent,
            completed_steps=default_progress.completed_steps,
            total_steps=default_progress.total_steps,
            resume_point=default_progress.resume_point,
            metadata=default_progress.metadata,
            created_at=default_progress.created_at,
            updated_at=updated_at or default_progress.updated_at,
        )
    return HarnessRunProgressRecord(
        space_id=run.space_id,
        run_id=run.id,
        status=run.status,
        phase=_default_phase_for_status(run.status),
        message=_default_message_for_status(run.status),
        progress_percent=_default_progress_percent(
            status=run.status,
            current=(current.progress_percent if current is not None else None),
        ),
        completed_steps=current.completed_steps if current is not None else 0,
        total_steps=current.total_steps if current is not None else None,
        resume_point=(
            current.resume_point
            if current is not None and run.status.strip().lower() == "paused"
            else None
        ),
        metadata=current.metadata if current is not None else {},
        created_at=current.created_at if current is not None else run.created_at,
        updated_at=updated_at or run.updated_at,
    )


def _run_record_from_model(
    *,
    model: HarnessRunModel,
    status: str,
    updated_at: datetime,
) -> HarnessRunRecord:
    return HarnessRunRecord(
        id=model.id,
        space_id=model.space_id,
        harness_id=model.harness_id,
        title=model.title,
        status=status,
        input_payload=(
            model.input_payload if isinstance(model.input_payload, dict) else {}
        ),
        graph_service_status=model.graph_service_status,
        graph_service_version=model.graph_service_version,
        created_at=_parse_timestamp(model.created_at) or _utcnow(),
        updated_at=_parse_timestamp(updated_at) or _utcnow(),
    )


def _default_progress_record(run: HarnessRunRecord) -> HarnessRunProgressRecord:
    return HarnessRunProgressRecord(
        space_id=run.space_id,
        run_id=run.id,
        status=run.status,
        phase="queued",
        message="Run created and queued.",
        progress_percent=0.0,
        completed_steps=0,
        total_steps=None,
        resume_point=None,
        metadata={},
        created_at=run.created_at,
        updated_at=run.updated_at,
    )




class ArtanaBackedHarnessRunRegistry(HarnessRunRegistry):
    """Store harness lifecycle state in Artana summaries and events."""

    def __init__(
        self,
        *,
        session: Session,
        runtime: GraphHarnessKernelRuntime,
    ) -> None:
        super().__init__()
        self._session = session
        self._runtime = runtime
        self._progress_persistence_backoff_until: dict[tuple[str, str], float] = {}

    def _get_run_model(self, *, run_id: UUID | str) -> HarnessRunModel | None:
        return self._session.get(HarnessRunModel, str(run_id))

    def _latest_run_state(self, *, space_id: str, run_id: str) -> JSONObject | None:
        return _summary_payload(
            self._runtime.get_latest_run_summary(
                run_id=run_id,
                tenant_id=space_id,
                summary_type=_RUN_STATE_SUMMARY,
                timeout_seconds=_FAST_READ_TIMEOUT_SECONDS,
            ),
        )

    def _latest_progress(self, *, space_id: str, run_id: str) -> JSONObject | None:
        return _summary_payload(
            self._runtime.get_latest_run_summary(
                run_id=run_id,
                tenant_id=space_id,
                summary_type=_PROGRESS_SUMMARY,
                timeout_seconds=_FAST_READ_TIMEOUT_SECONDS,
            ),
        )

    def _hydrate_run(self, *, model: HarnessRunModel) -> HarnessRunRecord:
        progress_payload: JSONObject | None = None
        state_payload: JSONObject | None = None
        model_updated_at = _parse_timestamp(model.updated_at) or _utcnow()
        try:
            progress_payload = self._latest_progress(
                space_id=model.space_id,
                run_id=model.id,
            )
            progress_updated_at = _summary_updated_at(progress_payload)
            if (
                not isinstance(progress_payload, dict)
                or progress_updated_at is None
                or progress_updated_at < model_updated_at
            ):
                state_payload = self._latest_run_state(
                    space_id=model.space_id,
                    run_id=model.id,
                )
        except TimeoutError:
            return _run_record_from_model(
                model=model,
                status=model.status,
                updated_at=model_updated_at,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to hydrate harness run summaries; falling back to catalog metadata.",
                extra={
                    "run_id": model.id,
                    "space_id": model.space_id,
                    "harness_id": model.harness_id,
                },
                exc_info=exc,
            )
            return _run_record_from_model(
                model=model,
                status=model.status,
                updated_at=model_updated_at,
            )
        updated_at = max(
            (
                timestamp
                for timestamp in (
                    _summary_updated_at(progress_payload),
                    _summary_updated_at(state_payload),
                    model_updated_at,
                )
                if timestamp is not None
            ),
            default=model_updated_at,
        )
        return _run_record_from_model(
            model=model,
            status=model.status,
            updated_at=updated_at,
        )

    def _catalog_run_record(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunRecord | None:
        model = self._get_run_model(run_id=run_id)
        if model is None or model.space_id != str(space_id):
            return None
        return _run_record_from_model(
            model=model,
            status=model.status,
            updated_at=model.updated_at,
        )

    def get_run_fast(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunRecord | None:
        return self._catalog_run_record(space_id=space_id, run_id=run_id)

    def has_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> bool:
        model = self._get_run_model(run_id=run_id)
        return model is not None and model.space_id == str(space_id)

    def _write_summary(
        self,
        *,
        run_id: str,
        space_id: str,
        summary_type: str,
        payload: JSONObject,
        step_prefix: str,
    ) -> None:
        _append_run_summary_with_retry(
            runtime=self._runtime,
            run_id=run_id,
            tenant_id=space_id,
            summary_type=summary_type,
            summary_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            step_key=_step_key(step_prefix),
        )

    def _write_summary_once(
        self,
        *,
        run_id: str,
        space_id: str,
        summary_type: str,
        payload: JSONObject,
        step_prefix: str,
    ) -> None:
        _append_run_summary_once(
            runtime=self._runtime,
            run_id=run_id,
            tenant_id=space_id,
            summary_type=summary_type,
            summary_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            step_key=_step_key(step_prefix),
        )

    def _write_event_summary(  # noqa: PLR0913
        self,
        *,
        space_id: str,
        run_id: str,
        event_type: str,
        status: str,
        message: str,
        payload: JSONObject,
        progress_percent: float | None,
    ) -> HarnessRunEventRecord:
        now = _utcnow()
        record = HarnessRunEventRecord(
            id=str(uuid4()),
            space_id=space_id,
            run_id=run_id,
            event_type=event_type,
            status=status,
            message=message,
            progress_percent=progress_percent,
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        self._write_summary(
            run_id=run_id,
            space_id=space_id,
            summary_type=f"{_EVENT_PREFIX}{record.id}",
            payload={
                "id": record.id,
                "event_type": record.event_type,
                "status": record.status,
                "message": record.message,
                "progress_percent": record.progress_percent,
                "payload": record.payload,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
            },
            step_prefix="event",
        )
        return record

    def _write_event_summary_once(  # noqa: PLR0913
        self,
        *,
        space_id: str,
        run_id: str,
        event_type: str,
        status: str,
        message: str,
        payload: JSONObject,
        progress_percent: float | None,
    ) -> HarnessRunEventRecord:
        now = _utcnow()
        record = HarnessRunEventRecord(
            id=str(uuid4()),
            space_id=space_id,
            run_id=run_id,
            event_type=event_type,
            status=status,
            message=message,
            progress_percent=progress_percent,
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        self._write_summary_once(
            run_id=run_id,
            space_id=space_id,
            summary_type=f"{_EVENT_PREFIX}{record.id}",
            payload={
                "id": record.id,
                "event_type": record.event_type,
                "status": record.status,
                "message": record.message,
                "progress_percent": record.progress_percent,
                "payload": record.payload,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat(),
            },
            step_prefix="event",
        )
        return record

    def _progress_backoff_key(self, *, run_id: str, kind: str) -> tuple[str, str]:
        return (run_id, kind)

    def _progress_persistence_backoff_active(
        self,
        *,
        run_id: str,
        kind: str,
    ) -> bool:
        resume_at = self._progress_persistence_backoff_until.get(
            self._progress_backoff_key(run_id=run_id, kind=kind),
        )
        return resume_at is not None and time.monotonic() < resume_at

    def _activate_progress_persistence_backoff(
        self,
        *,
        run_id: str,
        kind: str,
    ) -> None:
        self._progress_persistence_backoff_until[
            self._progress_backoff_key(run_id=run_id, kind=kind)
        ] = time.monotonic() + _PROGRESS_PERSISTENCE_BACKOFF_SECONDS

    def _clear_progress_persistence_backoff(
        self,
        *,
        run_id: str,
        kind: str,
    ) -> None:
        self._progress_persistence_backoff_until.pop(
            self._progress_backoff_key(run_id=run_id, kind=kind),
            None,
        )

    def create_run(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        harness_id: str,
        title: str,
        input_payload: JSONObject,
        graph_service_status: str,
        graph_service_version: str,
    ) -> HarnessRunRecord:
        normalized_space_id = str(space_id)
        model = HarnessRunModel(
            space_id=normalized_space_id,
            harness_id=harness_id,
            title=title,
            status="queued",
            input_payload=input_payload,
            graph_service_status=graph_service_status,
            graph_service_version=graph_service_version,
        )
        self._session.add(model)
        commit_or_flush(self._session)
        self._session.refresh(model)
        record = _run_record_from_model(
            model=model,
            status="queued",
            updated_at=model.created_at,
        )
        progress = _default_progress_record(record)

        def write_runtime_state() -> None:
            self._runtime.ensure_run(run_id=record.id, tenant_id=normalized_space_id)
            self._write_summary(
                run_id=record.id,
                space_id=normalized_space_id,
                summary_type=_RUN_STATE_SUMMARY,
                payload={
                    "status": "queued",
                    "updated_at": record.created_at.isoformat(),
                },
                step_prefix="run_state",
            )
            self._write_summary(
                run_id=record.id,
                space_id=normalized_space_id,
                summary_type=_PROGRESS_SUMMARY,
                payload={
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
                },
                step_prefix="progress",
            )
            self._write_event_summary(
                space_id=normalized_space_id,
                run_id=record.id,
                event_type="run.created",
                status="queued",
                message="Run created and queued.",
                payload={"harness_id": harness_id, "title": title},
                progress_percent=0.0,
            )

        run_after_commit_or_now(
            self._session,
            write_runtime_state,
        )
        return record

    def list_runs(self, *, space_id: UUID | str) -> list[HarnessRunRecord]:
        stmt = (
            select(HarnessRunModel)
            .where(HarnessRunModel.space_id == str(space_id))
            .order_by(HarnessRunModel.created_at.desc())
        )
        models = self._session.execute(stmt).scalars().all()
        return [self._hydrate_run(model=model) for model in models]

    def count_runs(self, *, space_id: UUID | str) -> int:
        stmt = (
            select(func.count())
            .select_from(HarnessRunModel)
            .where(
                HarnessRunModel.space_id == str(space_id),
            )
        )
        return int(self._session.execute(stmt).scalar_one())

    def get_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunRecord | None:
        model = self._get_run_model(run_id=run_id)
        if model is None or model.space_id != str(space_id):
            return None
        return self._hydrate_run(model=model)

    def replace_run_input_payload(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        input_payload: JSONObject,
    ) -> HarnessRunRecord | None:
        model = self._get_run_model(run_id=run_id)
        if model is None or model.space_id != str(space_id):
            return None
        model.input_payload = input_payload
        model.updated_at = _utcnow()
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._hydrate_run(model=model)

    def get_progress(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunProgressRecord | None:
        run = self._catalog_run_record(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        try:
            payload = self._latest_progress(space_id=run.space_id, run_id=run.id)
        except TimeoutError:
            return _catalog_progress_record(run=run)
        if isinstance(payload, dict):
            payload_updated_at = _summary_updated_at(payload)
            payload_progress = HarnessRunProgressRecord(
                space_id=run.space_id,
                run_id=run.id,
                status=_payload_string(payload, "status", default=run.status),
                phase=_payload_string(
                    payload,
                    "phase",
                    default=_default_phase_for_status(run.status),
                ),
                message=_payload_string(
                    payload,
                    "message",
                    default=_default_message_for_status(run.status),
                ),
                progress_percent=_payload_float(
                    payload,
                    "progress_percent",
                    default=_default_progress_percent(status=run.status),
                ),
                completed_steps=_payload_int(payload, "completed_steps", default=0),
                total_steps=_payload_optional_int(payload, "total_steps"),
                resume_point=_payload_optional_string(payload, "resume_point"),
                metadata=_payload_json_object(payload, "metadata"),
                created_at=_parse_timestamp(payload.get("created_at"))
                or run.created_at,
                updated_at=payload_updated_at or run.updated_at,
            )
            if payload_updated_at is not None and payload_updated_at >= run.updated_at:
                return payload_progress
            return _catalog_progress_record(
                run=run,
                current=payload_progress,
                updated_at=run.updated_at,
            )
        return _catalog_progress_record(run=run)

    def get_progress_fast(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunProgressRecord | None:
        run = self._catalog_run_record(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        return _catalog_progress_record(run=run)

    def set_run_status(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        status: str,
        existing_progress: HarnessRunProgressRecord | None = None,
    ) -> HarnessRunRecord | None:
        run = self._catalog_run_record(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        now = _utcnow()
        model = self._get_run_model(run_id=run.id)
        if model is not None:
            model.status = status
            model.updated_at = now
            self._session.add(model)
            commit_or_flush(self._session)
        updated_run = HarnessRunRecord(
            id=run.id,
            space_id=run.space_id,
            harness_id=run.harness_id,
            title=run.title,
            status=status,
            input_payload=run.input_payload,
            graph_service_status=run.graph_service_status,
            graph_service_version=run.graph_service_version,
            created_at=run.created_at,
            updated_at=now,
        )
        if existing_progress is not None and (
            existing_progress.run_id != run.id
            or existing_progress.space_id != run.space_id
        ):
            existing_progress = None
        progress_record = _catalog_progress_record(
            run=updated_run,
            current=existing_progress,
            updated_at=now,
        )

        def write_runtime_state() -> None:
            run_status_write_timed_out = False
            try:
                self._write_summary(
                    run_id=run.id,
                    space_id=run.space_id,
                    summary_type=_RUN_STATE_SUMMARY,
                    payload={
                        "status": status,
                        "updated_at": now.isoformat(),
                    },
                    step_prefix="run_state",
                )
            except TimeoutError:
                run_status_write_timed_out = True
            progress_write_timed_out = False
            try:
                self._write_summary(
                    run_id=run.id,
                    space_id=run.space_id,
                    summary_type=_PROGRESS_SUMMARY,
                    payload={
                        "status": progress_record.status,
                        "phase": progress_record.phase,
                        "message": progress_record.message,
                        "progress_percent": progress_record.progress_percent,
                        "completed_steps": progress_record.completed_steps,
                        "total_steps": progress_record.total_steps,
                        "resume_point": progress_record.resume_point,
                        "metadata": progress_record.metadata,
                        "created_at": progress_record.created_at.isoformat(),
                        "updated_at": progress_record.updated_at.isoformat(),
                    },
                    step_prefix="progress",
                )
            except TimeoutError:
                progress_write_timed_out = True
            event_write_timed_out = False
            try:
                self._write_event_summary(
                    space_id=run.space_id,
                    run_id=run.id,
                    event_type="run.status_changed",
                    status=status,
                    message=progress_record.message,
                    payload={"phase": progress_record.phase},
                    progress_percent=progress_record.progress_percent,
                )
            except TimeoutError:
                event_write_timed_out = True
            if (
                run_status_write_timed_out
                or progress_write_timed_out
                or event_write_timed_out
            ):
                _LOGGER.warning(
                    "Artana run status persistence timed out; catalog state remains authoritative.",
                    extra={
                        "run_id": run.id,
                        "space_id": run.space_id,
                        "status": status,
                        "run_state_write_timed_out": run_status_write_timed_out,
                        "progress_write_timed_out": progress_write_timed_out,
                        "event_write_timed_out": event_write_timed_out,
                    },
                )

        run_after_commit_or_now(
            self._session,
            write_runtime_state,
        )
        return updated_run

    def set_progress(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int | None = None,
        total_steps: int | None = None,
        resume_point: str | None = None,
        clear_resume_point: bool = False,
        metadata: JSONObject | None = None,
        merge_existing: bool = True,
    ) -> HarnessRunProgressRecord | None:
        run = self._catalog_run_record(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        existing = (
            self.get_progress(space_id=space_id, run_id=run_id)
            if merge_existing
            else None
        )
        now = _utcnow()
        merged_metadata: JSONObject = {
            **(existing.metadata if existing is not None else {}),
            **(metadata or {}),
        }
        updated = HarnessRunProgressRecord(
            space_id=run.space_id,
            run_id=run.id,
            status=run.status,
            phase=phase.strip()
            or (existing.phase if existing is not None else run.status),
            message=message.strip()
            or (
                existing.message
                if existing is not None
                else _default_message_for_status(run.status)
            ),
            progress_percent=max(0.0, min(progress_percent, 1.0)),
            completed_steps=(
                completed_steps
                if completed_steps is not None
                else (existing.completed_steps if existing is not None else 0)
            ),
            total_steps=(
                total_steps
                if total_steps is not None
                else (existing.total_steps if existing is not None else None)
            ),
            resume_point=(
                None
                if clear_resume_point
                else (
                    resume_point
                    if resume_point is not None
                    else (existing.resume_point if existing is not None else None)
                )
            ),
            metadata=merged_metadata,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        model = self._get_run_model(run_id=run.id)
        if model is not None:
            model.updated_at = now
            self._session.add(model)
            self._session.commit()
        if not self._progress_persistence_backoff_active(
            run_id=run.id,
            kind="summary",
        ):
            try:
                self._write_summary_once(
                    run_id=run.id,
                    space_id=run.space_id,
                    summary_type=_PROGRESS_SUMMARY,
                    payload={
                        "status": updated.status,
                        "phase": updated.phase,
                        "message": updated.message,
                        "progress_percent": updated.progress_percent,
                        "completed_steps": updated.completed_steps,
                        "total_steps": updated.total_steps,
                        "resume_point": updated.resume_point,
                        "metadata": updated.metadata,
                        "created_at": updated.created_at.isoformat(),
                        "updated_at": updated.updated_at.isoformat(),
                    },
                    step_prefix="progress",
                )
                self._clear_progress_persistence_backoff(
                    run_id=run.id,
                    kind="summary",
                )
            except TimeoutError:
                self._activate_progress_persistence_backoff(
                    run_id=run.id,
                    kind="summary",
                )
                _LOGGER.info(
                    "Entering Artana progress summary backoff after timeout; catalog state remains authoritative.",
                    extra={"run_id": run.id, "space_id": run.space_id},
                )
        if not self._progress_persistence_backoff_active(
            run_id=run.id,
            kind="event",
        ):
            try:
                self._write_event_summary_once(
                    space_id=run.space_id,
                    run_id=run.id,
                    event_type="run.progress",
                    status=run.status,
                    message=updated.message,
                    payload={
                        "phase": updated.phase,
                        "resume_point": updated.resume_point,
                        "completed_steps": updated.completed_steps,
                        "total_steps": updated.total_steps,
                        "metadata": updated.metadata,
                    },
                    progress_percent=updated.progress_percent,
                )
                self._clear_progress_persistence_backoff(
                    run_id=run.id,
                    kind="event",
                )
            except TimeoutError:
                self._activate_progress_persistence_backoff(
                    run_id=run.id,
                    kind="event",
                )
                _LOGGER.info(
                    "Entering Artana progress event backoff after timeout; catalog state remains authoritative.",
                    extra={"run_id": run.id, "space_id": run.space_id},
                )
        return updated

    def list_events(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        limit: int = 100,
    ) -> list[HarnessRunEventRecord]:
        run = self._catalog_run_record(space_id=space_id, run_id=run_id)
        if run is None:
            return []
        events: list[HarnessRunEventRecord] = []
        try:
            runtime_events = self._runtime.get_events(
                run_id=run.id,
                tenant_id=run.space_id,
                timeout_seconds=_FAST_READ_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            progress = self.get_progress_fast(space_id=run.space_id, run_id=run.id)
            return _fallback_events(
                run=run,
                progress=progress,
                degraded_reason="events_read_timeout",
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to load Artana run events; falling back to degraded event payload.",
                extra={"run_id": run.id, "space_id": run.space_id},
                exc_info=exc,
            )
            progress = self.get_progress_fast(space_id=run.space_id, run_id=run.id)
            return _fallback_events(
                run=run,
                progress=progress,
                degraded_reason="events_read_error",
            )
        for event in runtime_events:
            if event.event_type.value == "run_summary":
                summary_event = _summary_event_payload(event)
                if summary_event is None:
                    continue
                summary_type, payload = summary_event
                if summary_type.startswith(_EVENT_PREFIX):
                    events.append(
                        HarnessRunEventRecord(
                            id=_payload_string(payload, "id", default=event.event_id),
                            space_id=run.space_id,
                            run_id=run.id,
                            event_type=_payload_string(
                                payload,
                                "event_type",
                                default="run.event",
                            ),
                            status=_payload_string(
                                payload,
                                "status",
                                default=run.status,
                            ),
                            message=_payload_string(
                                payload,
                                "message",
                                default="Run event recorded.",
                            ),
                            progress_percent=(
                                _payload_float(payload, "progress_percent", default=0.0)
                                if isinstance(
                                    payload.get("progress_percent"),
                                    int | float,
                                )
                                and not isinstance(
                                    payload.get("progress_percent"),
                                    bool,
                                )
                                else None
                            ),
                            payload=_payload_json_object(payload, "payload"),
                            created_at=_parse_timestamp(payload.get("created_at"))
                            or event.timestamp,
                            updated_at=_parse_timestamp(payload.get("updated_at"))
                            or event.timestamp,
                        ),
                    )
                continue
            events.append(_kernel_event_record(run=run, event=event))
        return events[:limit]

    def record_event(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        event_type: str,
        message: str,
        payload: JSONObject | None = None,
        progress_percent: float | None = None,
    ) -> HarnessRunEventRecord | None:
        run = self.get_run(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        return self._write_event_summary(
            space_id=run.space_id,
            run_id=run.id,
            event_type=event_type.strip() or "run.event",
            status=run.status,
            message=message.strip() or "Run event recorded.",
            payload=payload or {},
            progress_percent=progress_percent,
        )

    def delete_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> bool:
        """Delete one catalog run row without using the in-memory registry path.

        The Artana runtime does not yet expose summary/event deletion, but claim
        curation cleanup only needs the catalog record removed so subsequent lookups
        stop resolving the failed run.
        """

        model = self._get_run_model(run_id=run_id)
        if model is None or model.space_id != str(space_id):
            return False
        self._session.delete(model)
        self._session.commit()
        return True




from .artana_artifact_store import ArtanaBackedHarnessArtifactStore  # noqa: E402,I001

__all__ = ["ArtanaBackedHarnessArtifactStore", "ArtanaBackedHarnessRunRegistry"]
