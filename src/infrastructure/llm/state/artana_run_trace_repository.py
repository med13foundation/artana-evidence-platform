"""Artana public-kernel-backed run trace reader."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from threading import Event, Thread
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from src.application.services.ports.artana_run_trace_port import (
    ArtanaRunTraceEventRecord,
    ArtanaRunTracePort,
    ArtanaRunTraceRecord,
    ArtanaRunTraceSummaryRecord,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    get_shared_artana_postgres_store,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Coroutine, Iterable

    from artana.events import KernelEvent
    from artana.models import TenantContext
    from artana.ports.model import ModelRequest, ModelResult

    from src.type_definitions.common import JSONObject, JSONValue

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.kernel import ArtanaKernel
except ImportError as exc:  # pragma: no cover - environment dependent
    _ARTANA_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)
OutputT = TypeVar("OutputT", bound=BaseModel)
ResultT = TypeVar("ResultT")


class _NoopModelPort:
    """Minimal model-port stub; trace reads never execute model steps."""

    async def complete(
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]:
        _ = request
        msg = "Model execution is not supported by Artana run-trace reader."
        raise RuntimeError(msg)


class _AsyncLoopRunner:
    """Own one event loop thread for async kernel interactions."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._started = Event()
        self._closed = False
        self._thread = Thread(
            target=self._run_loop,
            daemon=True,
            name="artana-run-trace-loop",
        )
        self._thread.start()
        if not self._started.wait(timeout=2.0):
            msg = "Timed out starting Artana run-trace event loop thread."
            raise RuntimeError(msg)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

    def run(self, coroutine: Coroutine[object, object, ResultT]) -> ResultT:
        if self._closed:
            msg = "Artana run-trace loop is closed."
            raise RuntimeError(msg)
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            logger.warning("Timed out closing Artana run-trace loop thread.")
        else:
            self._loop.close()


class ArtanaKernelRunTraceRepository(ArtanaRunTracePort):
    """Load one run trace through the public Artana kernel lifecycle API."""

    def __init__(self) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
            msg = (
                "artana-kernel is required for run-trace monitoring. Install dependency "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._runner = _AsyncLoopRunner()
        try:
            self._kernel = ArtanaKernel(
                store=get_shared_artana_postgres_store(),
                model_port=_NoopModelPort(),
            )
        except Exception:
            self._runner.close()
            raise

    def get_run_trace(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> ArtanaRunTraceRecord | None:
        normalized_run_id = run_id.strip()
        normalized_tenant_id = tenant_id.strip()
        if not normalized_run_id or not normalized_tenant_id:
            return None

        try:
            tenant = self._tenant_context(tenant_id=normalized_tenant_id)
            status = self._runner.run(
                self._kernel.get_run_status(
                    run_id=normalized_run_id,
                    tenant=tenant,
                ),
            )
            progress = self._runner.run(
                self._kernel.get_run_progress(
                    run_id=normalized_run_id,
                    tenant=tenant,
                ),
            )
            explain = self._runner.run(
                self._kernel.explain_run(
                    normalized_run_id,
                    tenant=tenant,
                ),
            )
            events = self._runner.run(
                self._kernel.get_events(
                    run_id=normalized_run_id,
                    tenant=tenant,
                ),
            )
        except ValueError:
            return None
        except Exception as exc:  # noqa: BLE001 - observability should degrade quietly
            logger.debug(
                "Unable to resolve Artana trace for run id '%s': %s",
                normalized_run_id,
                exc,
            )
            return None

        explain_payload = _as_object(to_json_value(explain))
        event_records = tuple(_normalize_event_records(events))
        return ArtanaRunTraceRecord(
            run_id=normalized_run_id,
            tenant_id=_normalize_text(getattr(status, "tenant_id", None))
            or normalized_tenant_id,
            status=_normalize_text(getattr(progress, "status", None))
            or _normalize_text(getattr(status, "status", None))
            or "unknown",
            last_event_seq=_coerce_int(getattr(status, "last_event_seq", None)),
            last_event_type=_normalize_text(getattr(status, "last_event_type", None)),
            updated_at=_coerce_datetime(getattr(status, "updated_at", None))
            or _coerce_datetime(getattr(progress, "updated_at", None)),
            blocked_on=_normalize_text(getattr(status, "blocked_on", None)),
            failure_reason=_normalize_text(getattr(status, "failure_reason", None))
            or _normalize_text(explain_payload.get("failure_reason")),
            error_category=_normalize_text(getattr(status, "error_category", None))
            or _normalize_text(explain_payload.get("error_category")),
            progress_percent=_coerce_int(getattr(progress, "percent", None)),
            current_stage=_normalize_text(getattr(progress, "current_stage", None)),
            completed_stages=tuple(
                _normalize_string_list(getattr(progress, "completed_stages", None)),
            ),
            started_at=_coerce_datetime(getattr(progress, "started_at", None)),
            eta_seconds=_coerce_int(getattr(progress, "eta_seconds", None)),
            explain=explain_payload,
            events=event_records,
            summaries=tuple(_latest_summaries_from_events(event_records)),
        )

    def _tenant_context(self, *, tenant_id: str) -> TenantContext:
        from artana.models import TenantContext

        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=10.0,
        )


def _normalize_event_records(
    events: Iterable[KernelEvent],
) -> list[ArtanaRunTraceEventRecord]:
    normalized: list[ArtanaRunTraceEventRecord] = []
    for event in events:
        payload_dict = _as_object(to_json_value(event.payload.model_dump(mode="json")))
        normalized.append(
            ArtanaRunTraceEventRecord(
                seq=event.seq,
                event_id=event.event_id,
                event_type=event.event_type.value,
                timestamp=event.timestamp,
                parent_step_key=event.parent_step_key,
                payload=payload_dict,
                tool_name=_normalize_tool_name(
                    event_type=event.event_type.value,
                    payload=payload_dict,
                ),
                tool_outcome=_normalize_tool_outcome(
                    event_type=event.event_type.value,
                    payload=payload_dict,
                ),
                step_key=_normalize_text(payload_dict.get("step_key")),
            ),
        )
    return normalized


def _latest_summaries_from_events(
    events: tuple[ArtanaRunTraceEventRecord, ...],
) -> list[ArtanaRunTraceSummaryRecord]:
    summaries: list[ArtanaRunTraceSummaryRecord] = []
    seen_summary_types: set[str] = set()
    for event in reversed(events):
        if event.event_type != "run_summary":
            continue
        payload = event.payload
        summary_type = _normalize_text(payload.get("summary_type"))
        if summary_type is None or summary_type in seen_summary_types:
            continue
        summary_payload = _parse_summary_payload(payload.get("summary_json"))
        summaries.append(
            ArtanaRunTraceSummaryRecord(
                summary_type=summary_type,
                timestamp=event.timestamp,
                step_key=_normalize_text(payload.get("step_key")),
                payload=summary_payload,
            ),
        )
        seen_summary_types.add(summary_type)
    return summaries


def _parse_summary_payload(raw_value: object) -> JSONValue:
    raw_text = _normalize_text(raw_value)
    if raw_text is None:
        return {}
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    return to_json_value(parsed)


def _normalize_tool_name(
    *,
    event_type: str,
    payload: JSONObject,
) -> str | None:
    if event_type not in {"tool_requested", "tool_completed"}:
        return None
    return _normalize_text(payload.get("tool_name"))


def _normalize_tool_outcome(
    *,
    event_type: str,
    payload: JSONObject,
) -> str | None:
    if event_type == "tool_completed":
        return _normalize_text(payload.get("outcome"))
    if event_type == "model_terminal":
        return _normalize_text(payload.get("outcome"))
    return None


def _normalize_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _as_object(value: JSONValue) -> JSONObject:
    return value if isinstance(value, dict) else {}


__all__ = ["ArtanaKernelRunTraceRepository"]
