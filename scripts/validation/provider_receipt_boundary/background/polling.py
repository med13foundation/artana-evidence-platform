"""Monotonic polling of one acknowledged provider response ID."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from scripts.validation.provider_receipt_boundary.background.contracts import (
    BackgroundExecutionBudgets,
    PollingResult,
)
from scripts.validation.provider_receipt_boundary.background.states import (
    BackgroundDisposition,
    classify_background_status,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)

RetrieveResponse = Callable[[str], dict[str, object]]
ValidateResponse = Callable[[dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class PollingRuntime:
    retrieve: RetrieveResponse
    validate: ValidateResponse
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep


def poll_background_response(
    *,
    initial_response: dict[str, object],
    response_id: str,
    budgets: BackgroundExecutionBudgets,
    runtime: PollingRuntime,
) -> PollingResult:
    """Poll one response until completion or the first terminal failure."""

    disposition, initial_status = _validate_response(
        initial_response, response_id=response_id, runtime=runtime
    )
    statuses = [initial_status]
    if disposition == "COMPLETED":
        return PollingResult(initial_response, tuple(statuses), 0, 0.0)

    started = runtime.monotonic()
    retrieval_requests = 0
    while True:
        elapsed = runtime.monotonic() - started
        remaining = budgets.max_polling_seconds - elapsed
        if remaining <= 0:
            raise _polling_timeout(response_id, retrieval_requests, elapsed)
        runtime.sleep(min(budgets.polling_interval_seconds, remaining))
        elapsed = runtime.monotonic() - started
        if elapsed >= budgets.max_polling_seconds:
            raise _polling_timeout(response_id, retrieval_requests, elapsed)
        retrieval_requests += 1
        try:
            response = runtime.retrieve(response_id)
        except ProviderExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - polling never retries a failed GET.
            raise ProviderExecutionError(
                "BACKGROUND_POLL_RETRIEVAL",
                type(exc).__name__,
                diagnostics={
                    "response_id": response_id,
                    "polling_retrieval_requests": retrieval_requests,
                },
            ) from exc
        disposition, status = _validate_response(
            response, response_id=response_id, runtime=runtime
        )
        statuses.append(status)
        if disposition == "COMPLETED":
            return PollingResult(
                response,
                tuple(statuses),
                retrieval_requests,
                runtime.monotonic() - started,
            )


def _status(response: dict[str, object]) -> str:
    value = response.get("status")
    if not isinstance(value, str):
        raise ProviderExecutionError(
            "BACKGROUND_UNKNOWN_STATUS",
            "provider status is malformed",
        )
    return value


def _validate_response(
    response: dict[str, object],
    *,
    response_id: str,
    runtime: PollingRuntime,
) -> tuple[BackgroundDisposition, str]:
    try:
        runtime.validate(response)
        return classify_background_status(response), _status(response)
    except ProviderExecutionError as exc:
        if "response_id" in exc.diagnostics:
            raise
        raise ProviderExecutionError(
            exc.stage,
            exc.root_cause,
            diagnostics={**exc.diagnostics, "response_id": response_id},
        ) from exc


def _polling_timeout(
    response_id: str, retrieval_requests: int, elapsed: float
) -> ProviderExecutionError:
    return ProviderExecutionError(
        "BACKGROUND_POLLING_TIMEOUT",
        "background response exceeded the polling budget",
        diagnostics={
            "response_id": response_id,
            "polling_retrieval_requests": retrieval_requests,
            "polling_seconds": elapsed,
            "creation_repeated": False,
        },
    )


__all__ = ["PollingRuntime", "poll_background_response"]
