"""Artana-kernel-backed run progress reader for workflow monitor views."""

from __future__ import annotations

import asyncio
import logging
from threading import Event, Thread
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from src.application.services.ports.run_progress_port import (
    RunProgressPort,
    RunProgressSnapshot,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    get_shared_artana_postgres_store,
)

if TYPE_CHECKING:
    from datetime import datetime

    from artana.models import TenantContext
    from artana.ports.model import ModelRequest, ModelResult
    from artana.store import PostgresStore

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.kernel import ArtanaKernel
except ImportError as exc:  # pragma: no cover - environment dependent
    _ARTANA_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)
OutputT = TypeVar("OutputT", bound=BaseModel)

_RUNNING_STATUSES: frozenset[str] = frozenset({"running"})
_COMPLETED_STATUSES: frozenset[str] = frozenset({"completed"})
_FAILED_STATUSES: frozenset[str] = frozenset({"failed"})
_PAUSED_STATUSES: frozenset[str] = frozenset({"paused"})
_TERMINAL_FAILURE_EVENTS: frozenset[str] = frozenset(
    {
        "run_failed",
        "run_error",
        "model_failed",
        "tool_failed",
        "step_failed",
    },
)
_TERMINAL_COMPLETION_EVENTS: frozenset[str] = frozenset(
    {
        "run_completed",
        "run_summary",
        "workflow_completed",
        "step_completed",
    },
)
_MODEL_TERMINAL_FAILURE_OUTCOMES: frozenset[str] = frozenset(
    {"failed", "timeout", "cancelled", "abandoned"},
)
_MODEL_TERMINAL_COMPLETION_OUTCOMES: frozenset[str] = frozenset({"completed"})
_FULL_PROGRESS_PERCENT = 100


class _NoopModelPort:
    """Minimal model-port stub; run-progress calls do not execute model steps."""

    async def complete(
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]:
        _ = request
        msg = "Model execution is not supported by run-progress reader."
        raise RuntimeError(msg)


class _AsyncLoopRunner:
    """Own one event loop thread for all async kernel/store interactions."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._started = Event()
        self._closed = False
        self._thread = Thread(
            target=self._run_loop,
            daemon=True,
            name="artana-run-progress-loop",
        )
        self._thread.start()
        if not self._started.wait(timeout=2.0):
            msg = "Timed out starting Artana run-progress event loop thread."
            raise RuntimeError(msg)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

    def run(self, coroutine: object) -> object:
        if self._closed:
            msg = "Artana run-progress loop is closed."
            raise RuntimeError(msg)
        if not asyncio.iscoroutine(coroutine):
            msg = "Expected coroutine for Artana run-progress call."
            raise TypeError(msg)

        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            logger.warning("Timed out closing Artana run-progress loop thread.")
        else:
            self._loop.close()


class ArtanaKernelRunProgressRepository(RunProgressPort):
    """Load run progress through the public Artana kernel lifecycle API."""

    def __init__(self, *, artana_store: PostgresStore | None = None) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
            msg = (
                "artana-kernel is required for run-progress monitoring. Install dependency "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._runner = _AsyncLoopRunner()
        try:
            resolved_artana_store = artana_store or get_shared_artana_postgres_store()
            self._kernel = ArtanaKernel(
                store=resolved_artana_store,
                model_port=_NoopModelPort(),
            )
        except Exception:
            self._runner.close()
            raise

    def get_run_progress(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> RunProgressSnapshot | None:
        normalized_run_id = run_id.strip()
        normalized_tenant_id = tenant_id.strip()
        if not normalized_run_id or not normalized_tenant_id:
            return None

        try:
            tenant = self._tenant_context(tenant_id=normalized_tenant_id)
            progress = self._runner.run(
                self._kernel.get_run_progress(
                    run_id=normalized_run_id,
                    tenant=tenant,
                ),
            )
        except ValueError:
            logger.debug(
                "No Artana progress events available for run id '%s'.",
                normalized_run_id,
            )
            return None
        except Exception as exc:  # noqa: BLE001 - optional monitor enrichment
            logger.debug(
                "Unable to resolve Artana progress for run id '%s': %s",
                normalized_run_id,
                exc,
            )
            return None

        status_value = _normalize_status(
            _normalize_optional_string(getattr(progress, "status", None)),
        )
        if status_value is None:
            return None

        percent_value = _coerce_percent(getattr(progress, "percent", None))
        run_status = (
            self._load_run_status(
                normalized_run_id,
                normalized_tenant_id,
            )
            if _should_load_run_status(status_value=status_value, percent=percent_value)
            else None
        )
        effective_status = _resolve_effective_status(
            progress_status=status_value,
            percent=percent_value,
            run_status=run_status,
        )
        effective_percent = (
            max(percent_value, _FULL_PROGRESS_PERCENT)
            if effective_status == "completed"
            else percent_value
        )
        updated_at = _coalesce_latest_datetime(
            _coerce_datetime(getattr(progress, "updated_at", None)),
            _coerce_datetime(getattr(run_status, "updated_at", None)),
        )

        return RunProgressSnapshot(
            run_id=normalized_run_id,
            status=effective_status,
            percent=effective_percent,
            current_stage=_normalize_optional_string(
                getattr(progress, "current_stage", None),
            ),
            completed_stages=_coerce_completed_stages(
                getattr(progress, "completed_stages", None),
            ),
            started_at=_coerce_datetime(getattr(progress, "started_at", None)),
            updated_at=updated_at,
            eta_seconds=_coerce_int_or_none(getattr(progress, "eta_seconds", None)),
        )

    def _load_run_status(
        self,
        run_id: str,
        tenant_id: str,
    ) -> object | None:
        try:
            tenant = self._tenant_context(tenant_id=tenant_id)
            return self._runner.run(
                self._kernel.get_run_status(
                    run_id=run_id,
                    tenant=tenant,
                ),
            )
        except ValueError:
            return None
        except Exception as exc:  # noqa: BLE001 - optional monitor enrichment
            logger.debug(
                "Unable to resolve Artana run status for run id '%s': %s",
                run_id,
                exc,
            )
            return None

    def _tenant_context(self, *, tenant_id: str) -> TenantContext:
        from artana.models import TenantContext

        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=10.0,
        )

    def close(self) -> None:
        """Best-effort cleanup for kernel/store resources."""
        self._runner.close()


def _normalize_optional_string(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
    elif value is None:
        return None
    else:
        normalized = str(value).strip()
    return normalized or None


def _normalize_status(value: str | None) -> str | None:
    normalized = _normalize_optional_string(value)
    if normalized is None:
        return None
    token = normalized.lower()
    if token in {"running", "active", "in_progress", "in-progress"}:
        return "running"
    if token in {"completed", "complete", "success", "succeeded"}:
        return "completed"
    if token in {"failed", "failure", "error"}:
        return "failed"
    if token in {"paused", "blocked"}:
        return "paused"
    return token


def _normalize_event_type(value: object) -> str | None:
    normalized = _normalize_optional_string(value)
    return normalized.lower() if normalized is not None else None


def _should_load_run_status(*, status_value: str, percent: int) -> bool:
    if status_value in _RUNNING_STATUSES:
        return True
    return percent < _FULL_PROGRESS_PERCENT


def _resolve_effective_status(
    *,
    progress_status: str,
    percent: int,
    run_status: object | None,
) -> str:
    if run_status is None:
        return progress_status

    run_status_value = _normalize_status(
        _normalize_optional_string(getattr(run_status, "status", None)),
    )
    last_event_type = _normalize_event_type(
        getattr(run_status, "last_event_type", None),
    )
    failure_reason = _normalize_optional_string(
        getattr(run_status, "failure_reason", None),
    )
    blocked_on = _normalize_optional_string(getattr(run_status, "blocked_on", None))
    model_terminal_outcome = _resolve_model_terminal_outcome(run_status)

    if (
        failure_reason is not None
        or run_status_value in _FAILED_STATUSES
        or last_event_type in _TERMINAL_FAILURE_EVENTS
        or (
            last_event_type == "model_terminal"
            and model_terminal_outcome in _MODEL_TERMINAL_FAILURE_OUTCOMES
        )
    ):
        return "failed"
    if run_status_value in _PAUSED_STATUSES or blocked_on is not None:
        return "paused"
    if run_status_value in _COMPLETED_STATUSES:
        return "completed"
    if (
        progress_status in _RUNNING_STATUSES
        and percent == 0
        and (
            last_event_type in _TERMINAL_COMPLETION_EVENTS
            or (
                last_event_type == "model_terminal"
                and model_terminal_outcome in _MODEL_TERMINAL_COMPLETION_OUTCOMES
            )
        )
    ):
        return "completed"
    return progress_status


def _resolve_model_terminal_outcome(run_status: object) -> str | None:
    for field_name in (
        "last_event_outcome",
        "last_model_outcome",
        "model_outcome",
        "outcome",
    ):
        value = _normalize_optional_string(getattr(run_status, field_name, None))
        if value is not None:
            return value.lower()
    return None


def _coalesce_latest_datetime(
    first: datetime | None,
    second: datetime | None,
) -> datetime | None:
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


def _coerce_percent(value: object) -> int:
    if isinstance(value, int):
        return max(0, min(value, 100))
    if isinstance(value, float):
        return max(0, min(int(value), 100))
    return 0


def _coerce_completed_stages(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    normalized: list[str] = []
    for item in value:
        stage = _normalize_optional_string(item)
        if stage is None:
            continue
        normalized.append(stage)
    return tuple(normalized)


def _coerce_datetime(value: object) -> datetime | None:
    from datetime import datetime

    return value if isinstance(value, datetime) else None


def _coerce_int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


__all__ = ["ArtanaKernelRunProgressRepository"]
