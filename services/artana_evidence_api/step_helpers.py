"""Service-local helpers for Artana single-step execution."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol, runtime_checkable

from artana_evidence_api.runtime_support import ReplayPolicy
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)
_FAILURE_BREAKER_THRESHOLD = 3
_STEP_EXECUTION_LOCK = Lock()


class StepResultLike(Protocol):
    """Protocol for structured step results returned by the kernel client."""

    output: object


@runtime_checkable
class StepClientLike(Protocol):
    """Runtime-checkable protocol for clients exposing ``step`` execution."""

    async def step(  # noqa: PLR0913 - mirrors the kernel step contract
        self,
        *,
        run_id: str,
        tenant: object,
        model: str,
        prompt: str,
        output_schema: type[object],
        step_key: str,
        replay_policy: ReplayPolicy,
        context_version: object | None = None,
    ) -> StepResultLike: ...


class StepExecutionHealth(BaseModel):
    """Summary of recent shared model-step execution health."""

    model_config = ConfigDict(strict=True)

    status: str
    total_calls: int
    consecutive_failures: int
    circuit_state: str
    last_model: str | None = None
    last_step_key: str | None = None
    last_run_id: str | None = None
    last_replay_policy: str | None = None
    last_context_version: str | None = None
    last_duration_seconds: float | None = None
    last_error: str | None = None
    last_completed_at: str | None = None


@dataclass(slots=True)
class _StepExecutionState:
    total_calls: int = 0
    consecutive_failures: int = 0
    last_model: str | None = None
    last_step_key: str | None = None
    last_run_id: str | None = None
    last_replay_policy: str | None = None
    last_context_version: str | None = None
    last_duration_seconds: float | None = None
    last_error: str | None = None
    last_completed_at: float | None = None


_STEP_EXECUTION_STATE = _StepExecutionState()


def _snapshot_step_execution_state() -> StepExecutionHealth:
    with _STEP_EXECUTION_LOCK:
        completed_at = _STEP_EXECUTION_STATE.last_completed_at
        return StepExecutionHealth(
            status=(
                "degraded"
                if _STEP_EXECUTION_STATE.consecutive_failures
                >= _FAILURE_BREAKER_THRESHOLD
                else "healthy"
            ),
            total_calls=_STEP_EXECUTION_STATE.total_calls,
            consecutive_failures=_STEP_EXECUTION_STATE.consecutive_failures,
            circuit_state=(
                "open"
                if _STEP_EXECUTION_STATE.consecutive_failures
                >= _FAILURE_BREAKER_THRESHOLD
                else "closed"
            ),
            last_model=_STEP_EXECUTION_STATE.last_model,
            last_step_key=_STEP_EXECUTION_STATE.last_step_key,
            last_run_id=_STEP_EXECUTION_STATE.last_run_id,
            last_replay_policy=_STEP_EXECUTION_STATE.last_replay_policy,
            last_context_version=_STEP_EXECUTION_STATE.last_context_version,
            last_duration_seconds=_STEP_EXECUTION_STATE.last_duration_seconds,
            last_error=_STEP_EXECUTION_STATE.last_error,
            last_completed_at=(
                datetime.fromtimestamp(completed_at, tz=UTC).isoformat()
                if completed_at is not None
                else None
            ),
        )


def get_step_execution_health() -> StepExecutionHealth:
    """Return the latest shared model-step execution health snapshot."""
    return _snapshot_step_execution_state()


def reset_step_execution_health() -> None:
    """Reset the shared model-step execution health snapshot."""
    with _STEP_EXECUTION_LOCK:
        _STEP_EXECUTION_STATE.total_calls = 0
        _STEP_EXECUTION_STATE.consecutive_failures = 0
        _STEP_EXECUTION_STATE.last_model = None
        _STEP_EXECUTION_STATE.last_step_key = None
        _STEP_EXECUTION_STATE.last_run_id = None
        _STEP_EXECUTION_STATE.last_replay_policy = None
        _STEP_EXECUTION_STATE.last_context_version = None
        _STEP_EXECUTION_STATE.last_duration_seconds = None
        _STEP_EXECUTION_STATE.last_error = None
        _STEP_EXECUTION_STATE.last_completed_at = None


def _record_step_attempt(
    *,
    run_id: str,
    model: str,
    step_key: str,
    replay_policy: ReplayPolicy,
    context_version: object | None,
) -> None:
    with _STEP_EXECUTION_LOCK:
        _STEP_EXECUTION_STATE.total_calls += 1
        _STEP_EXECUTION_STATE.last_model = model
        _STEP_EXECUTION_STATE.last_step_key = step_key
        _STEP_EXECUTION_STATE.last_run_id = run_id
        _STEP_EXECUTION_STATE.last_replay_policy = replay_policy
        _STEP_EXECUTION_STATE.last_context_version = (
            None if context_version is None else str(context_version)
        )


def _record_step_success(*, elapsed_seconds: float) -> None:
    with _STEP_EXECUTION_LOCK:
        _STEP_EXECUTION_STATE.consecutive_failures = 0
        _STEP_EXECUTION_STATE.last_duration_seconds = elapsed_seconds
        _STEP_EXECUTION_STATE.last_error = None
        _STEP_EXECUTION_STATE.last_completed_at = time.time()


def _record_step_failure(*, elapsed_seconds: float, error: Exception) -> None:
    with _STEP_EXECUTION_LOCK:
        _STEP_EXECUTION_STATE.consecutive_failures += 1
        _STEP_EXECUTION_STATE.last_duration_seconds = elapsed_seconds
        _STEP_EXECUTION_STATE.last_error = str(error)
        _STEP_EXECUTION_STATE.last_completed_at = time.time()


def _record_replayed_terminal(*, elapsed_seconds: float) -> None:
    with _STEP_EXECUTION_LOCK:
        _STEP_EXECUTION_STATE.last_duration_seconds = elapsed_seconds
        _STEP_EXECUTION_STATE.last_error = None
        _STEP_EXECUTION_STATE.last_completed_at = time.time()


def _is_replayed_model_terminal_exception(error: Exception) -> bool:
    return str(error).startswith("Replayed model terminal outcome=")


def _log_step_failure(
    *,
    model: str,
    run_id: str,
    step_key: str,
    elapsed_seconds: float,
    error: Exception,
) -> None:
    log_extra = {
        "artana_model": model,
        "artana_run_id": run_id,
        "artana_step_key": step_key,
        "artana_elapsed_seconds": elapsed_seconds,
        "artana_error": str(error),
    }
    if _is_replayed_model_terminal_exception(error):
        logger.info(
            "Artana model step replay surfaced historical terminal failure",
            extra={
                **log_extra,
                "artana_replayed_terminal": True,
            },
        )
        return
    logger.warning(
        "Artana model step failed",
        extra=log_extra,
        exc_info=True,
    )


async def run_single_step_with_policy(  # noqa: PLR0913
    client: object,
    *,
    run_id: str,
    tenant: object,
    model: str,
    prompt: str,
    output_schema: type[object],
    step_key: str,
    replay_policy: ReplayPolicy,
    context_version: object | None = None,
) -> StepResultLike:
    """Execute ``SingleStepModelClient.step`` with replay policy support."""
    if not isinstance(client, StepClientLike):
        msg = "Client does not expose a compatible callable 'step' method."
        raise TypeError(msg)
    _record_step_attempt(
        run_id=run_id,
        model=model,
        step_key=step_key,
        replay_policy=replay_policy,
        context_version=context_version,
    )
    started_at = time.perf_counter()
    logger.info(
        "Starting Artana model step",
        extra={
            "artana_model": model,
            "artana_run_id": run_id,
            "artana_step_key": step_key,
            "artana_replay_policy": replay_policy,
        },
    )
    if context_version is not None:
        try:
            result = await client.step(
                run_id=run_id,
                tenant=tenant,
                model=model,
                prompt=prompt,
                output_schema=output_schema,
                step_key=step_key,
                replay_policy=replay_policy,
                context_version=context_version,
            )
        except Exception as exc:
            elapsed_seconds = time.perf_counter() - started_at
            if _is_replayed_model_terminal_exception(exc):
                _record_replayed_terminal(elapsed_seconds=elapsed_seconds)
            else:
                _record_step_failure(elapsed_seconds=elapsed_seconds, error=exc)
            _log_step_failure(
                model=model,
                run_id=run_id,
                step_key=step_key,
                elapsed_seconds=elapsed_seconds,
                error=exc,
            )
            raise
        elapsed_seconds = time.perf_counter() - started_at
        _record_step_success(elapsed_seconds=elapsed_seconds)
        logger.info(
            "Completed Artana model step",
            extra={
                "artana_model": model,
                "artana_run_id": run_id,
                "artana_step_key": step_key,
                "artana_elapsed_seconds": elapsed_seconds,
            },
        )
        return result
    try:
        result = await client.step(
            run_id=run_id,
            tenant=tenant,
            model=model,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            replay_policy=replay_policy,
        )
    except Exception as exc:
        elapsed_seconds = time.perf_counter() - started_at
        if _is_replayed_model_terminal_exception(exc):
            _record_replayed_terminal(elapsed_seconds=elapsed_seconds)
        else:
            _record_step_failure(elapsed_seconds=elapsed_seconds, error=exc)
        _log_step_failure(
            model=model,
            run_id=run_id,
            step_key=step_key,
            elapsed_seconds=elapsed_seconds,
            error=exc,
        )
        raise
    elapsed_seconds = time.perf_counter() - started_at
    _record_step_success(elapsed_seconds=elapsed_seconds)
    logger.info(
        "Completed Artana model step",
        extra={
            "artana_model": model,
            "artana_run_id": run_id,
            "artana_step_key": step_key,
            "artana_elapsed_seconds": elapsed_seconds,
        },
    )
    return result


__all__ = [
    "StepExecutionHealth",
    "get_step_execution_health",
    "reset_step_execution_health",
    "run_single_step_with_policy",
]
