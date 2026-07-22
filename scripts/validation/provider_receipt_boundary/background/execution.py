"""Exactly-once background creation, polling, and receipt orchestration."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Protocol, TypeVar, cast

from openai import OpenAI
from pydantic import BaseModel

from scripts.validation.provider_receipt_boundary import (
    ReceiptBoundaryError,
    ReceiptExpectations,
    validate_provider_receipt,
    validate_retrieval_envelope,
)
from scripts.validation.provider_receipt_boundary.background.contracts import (
    BackgroundExecutionBudgets,
    BackgroundProviderExecution,
)
from scripts.validation.provider_receipt_boundary.background.polling import (
    PollingRuntime,
    poll_background_response,
)
from scripts.validation.provider_receipt_boundary.background.states import (
    classify_background_status,
)
from scripts.validation.provider_receipt_boundary.canonical_payload import (
    StructuredPayloadError,
    canonical_sha256,
    extract_canonical_payload,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
)

_OutputT = TypeVar("_OutputT", bound=BaseModel)


class _Dumpable(Protocol):
    def to_dict(
        self,
        *,
        mode: str,
        use_api_names: bool,
        exclude_unset: bool,
        exclude_none: bool,
    ) -> dict[str, object]: ...


class _InputPage(Protocol):
    def __iter__(self) -> Iterator[_Dumpable]: ...


class _InputItems(Protocol):
    def list(
        self,
        response_id: str,
        *,
        limit: int,
        order: str,
        timeout: float,
    ) -> _InputPage: ...


class _Responses(Protocol):
    def create(self, **kwargs: object) -> _Dumpable: ...

    def retrieve(self, response_id: str, *, timeout: float) -> _Dumpable: ...

    input_items: _InputItems


class _Client(Protocol):
    @property
    def responses(self) -> _Responses: ...


@dataclass(frozen=True, slots=True)
class BackgroundExecutionRuntime:
    client: object | None = None
    monotonic: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    on_acknowledged: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class _Acknowledgement:
    response: dict[str, object]
    response_id: str
    elapsed_seconds: float


def execute_background_provider_call(
    *,
    api_key: str,
    request: ProviderRequest,
    transport_budgets: BackgroundExecutionBudgets,
    output_model: type[_OutputT],
    runtime: BackgroundExecutionRuntime | None = None,
) -> BackgroundProviderExecution[_OutputT]:
    """Create once, poll one ID, then apply the strict completed receipt boundary."""

    execution_runtime = runtime or BackgroundExecutionRuntime()
    provider_client = cast(
        "_Client",
        execution_runtime.client
        or OpenAI(
            api_key=api_key,
            max_retries=0,
            timeout=transport_budgets.acknowledgement_timeout_seconds,
        ),
    )
    expectations = request.receipt_expectations()
    started = execution_runtime.monotonic()
    acknowledged = _create_acknowledgement(
        provider_client=provider_client,
        request=request,
        acknowledgement_timeout_seconds=transport_budgets.acknowledgement_timeout_seconds,
        monotonic=execution_runtime.monotonic,
    )
    acknowledgement = acknowledged.response
    response_id = acknowledged.response_id
    acknowledgement_seconds = acknowledged.elapsed_seconds
    if execution_runtime.on_acknowledged is not None:
        try:
            execution_runtime.on_acknowledged(response_id)
        except Exception as exc:  # noqa: BLE001 - custody callback fails closed.
            raise ProviderExecutionError(
                "BACKGROUND_ACKNOWLEDGEMENT_CUSTODY",
                type(exc).__name__,
                diagnostics={"response_id": response_id},
            ) from exc
    _validate_acknowledgement(
        acknowledged,
        budgets=transport_budgets,
        expectations=expectations,
    )

    def retrieve(known_response_id: str) -> dict[str, object]:
        return _api_response_dict(
            provider_client.responses.retrieve(
                known_response_id,
                timeout=transport_budgets.acknowledgement_timeout_seconds,
            )
        )

    def validate_polled_snapshot(item: dict[str, object]) -> None:
        _validate_snapshot(
            item,
            expected_response_id=response_id,
            expectations=expectations,
        )

    polling = poll_background_response(
        initial_response=acknowledgement,
        response_id=response_id,
        budgets=transport_budgets,
        runtime=PollingRuntime(
            retrieve=retrieve,
            validate=validate_polled_snapshot,
            monotonic=execution_runtime.monotonic,
            sleep=execution_runtime.sleep,
        ),
    )
    confirmation_requests = 1
    try:
        confirmation = retrieve(response_id)
    except Exception as exc:  # noqa: BLE001 - confirmation GET is never retried.
        raise ProviderExecutionError(
            "BACKGROUND_CONFIRMATION_RETRIEVAL",
            type(exc).__name__,
            diagnostics={
                **_counts(
                    polling_retrieval_requests=polling.retrieval_requests,
                    confirmation_retrieval_requests=confirmation_requests,
                ),
                "response_id": response_id,
            },
        ) from exc
    _validate_confirmation(
        confirmation,
        response_id=response_id,
        expectations=expectations,
    )
    try:
        validate_retrieval_envelope(
            polling.terminal_response,
            confirmation,
            expectations,
        )
    except ReceiptBoundaryError as exc:
        raise _receipt_error(
            exc,
            response_id=response_id,
            polling_retrieval_requests=polling.retrieval_requests,
            confirmation_retrieval_requests=confirmation_requests,
        ) from exc

    input_item_retrieval_requests = 1
    try:
        page = provider_client.responses.input_items.list(
            response_id,
            limit=100,
            order="asc",
            timeout=transport_budgets.acknowledgement_timeout_seconds,
        )
        input_items = tuple(_api_response_dict(item) for item in page)
    except Exception as exc:  # noqa: BLE001 - input custody GET is never retried.
        raise ProviderExecutionError(
            "RECEIPT_INPUT_RETRIEVAL",
            type(exc).__name__,
            diagnostics={
                **_counts(
                    polling_retrieval_requests=polling.retrieval_requests,
                    confirmation_retrieval_requests=confirmation_requests,
                    input_item_retrieval_requests=input_item_retrieval_requests,
                ),
                "response_id": response_id,
            },
        ) from exc
    latency_seconds = execution_runtime.monotonic() - started
    try:
        validation = validate_provider_receipt(
            creation=polling.terminal_response,
            retrieval=confirmation,
            input_items=input_items,
            expectations=expectations,
            latency_seconds=latency_seconds,
        )
    except ReceiptBoundaryError as exc:
        raise _receipt_error(
            exc,
            response_id=response_id,
            polling_retrieval_requests=polling.retrieval_requests,
            confirmation_retrieval_requests=confirmation_requests,
            input_item_retrieval_requests=input_item_retrieval_requests,
        ) from exc

    try:
        canonical_payload = extract_canonical_payload(confirmation)
    except StructuredPayloadError as exc:
        raise ProviderExecutionError(
            "STRUCTURED_OUTPUT_PAYLOAD",
            str(exc),
            diagnostics={"response_id": response_id},
        ) from exc
    try:
        parsed = output_model.model_validate_json(
            json.dumps(canonical_payload.payload, separators=(",", ":"))
        )
    except Exception as exc:  # noqa: BLE001 - frozen schema fails closed.
        raise ProviderExecutionError(
            "STRUCTURED_OUTPUT_SCHEMA",
            type(exc).__name__,
            diagnostics={
                "response_id": response_id,
                "scientific_payload_sha256": canonical_payload.sha256,
            },
        ) from exc
    receipt = validation.as_json()
    receipt.update(
        {
            **_counts(
                polling_retrieval_requests=polling.retrieval_requests,
                confirmation_retrieval_requests=confirmation_requests,
                input_item_retrieval_requests=input_item_retrieval_requests,
            ),
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
            "polling_does_not_count_as_model_generation": True,
            "acknowledgement_seconds": acknowledgement_seconds,
            "polling_seconds": polling.polling_seconds,
            "status_history": list(polling.status_history),
            "acknowledgement_envelope_sha256": canonical_sha256(acknowledgement),
        }
    )
    return BackgroundProviderExecution(
        extraction=parsed,
        canonical_payload=canonical_payload.payload,
        acknowledgement_response=acknowledgement,
        terminal_response=polling.terminal_response,
        confirmation_response=confirmation,
        receipt=receipt,
    )


def _create_acknowledgement(
    *,
    provider_client: _Client,
    request: ProviderRequest,
    acknowledgement_timeout_seconds: float,
    monotonic: Callable[[], float],
) -> _Acknowledgement:
    started = monotonic()
    try:
        response = provider_client.responses.create(
            model=request.provider_model_id,
            input=request.provider_input,
            reasoning={"effort": request.reasoning_effort},
            max_output_tokens=request.max_output_tokens,
            text={"format": request.provider_format},
            metadata=request.metadata,
            background=True,
            store=True,
            timeout=acknowledgement_timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - creation is never repeated.
        stage = (
            "BACKGROUND_ACKNOWLEDGEMENT_TIMEOUT"
            if type(exc).__name__ in {"APITimeoutError", "TimeoutError"}
            else "BACKGROUND_CREATION_REJECTED"
        )
        raise ProviderExecutionError(
            stage,
            type(exc).__name__,
            diagnostics={
                **_counts(),
                "response_id_available": False,
                "duplicate_creation_may_exist": stage
                == "BACKGROUND_ACKNOWLEDGEMENT_TIMEOUT",
            },
        ) from exc
    elapsed_seconds = monotonic() - started
    acknowledgement = _api_response_dict(response)
    response_id = _require_response_id(acknowledgement)
    return _Acknowledgement(acknowledgement, response_id, elapsed_seconds)


def _validate_acknowledgement(
    acknowledgement: _Acknowledgement,
    *,
    budgets: BackgroundExecutionBudgets,
    expectations: ReceiptExpectations,
) -> None:
    try:
        _validate_snapshot(
            acknowledgement.response,
            expected_response_id=acknowledgement.response_id,
            expectations=expectations,
        )
    except ProviderExecutionError as exc:
        if "response_id" in exc.diagnostics:
            raise
        raise ProviderExecutionError(
            exc.stage,
            exc.root_cause,
            diagnostics={
                **exc.diagnostics,
                "response_id": acknowledgement.response_id,
            },
        ) from exc
    if acknowledgement.elapsed_seconds > budgets.acknowledgement_timeout_seconds:
        raise ProviderExecutionError(
            "BACKGROUND_ACKNOWLEDGEMENT_TIMEOUT",
            "response ID arrived after the acknowledgement budget",
            diagnostics={
                **_counts(),
                "response_id": acknowledgement.response_id,
                "acknowledgement_seconds": acknowledgement.elapsed_seconds,
                "duplicate_creation_may_exist": False,
            },
        )


def _require_response_id(response: dict[str, object]) -> str:
    response_id = response.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise ProviderExecutionError(
            "BACKGROUND_RESPONSE_ID",
            "provider response ID is absent or malformed",
        )
    return response_id


def _validate_confirmation(
    confirmation: dict[str, object],
    *,
    response_id: str,
    expectations: ReceiptExpectations,
) -> None:
    try:
        _validate_snapshot(
            confirmation,
            expected_response_id=response_id,
            expectations=expectations,
        )
        _require_confirmation_completed(confirmation)
    except ProviderExecutionError as exc:
        if "response_id" in exc.diagnostics:
            raise
        raise ProviderExecutionError(
            exc.stage,
            exc.root_cause,
            diagnostics={**exc.diagnostics, "response_id": response_id},
        ) from exc


def _require_confirmation_completed(confirmation: dict[str, object]) -> None:
    if classify_background_status(confirmation) != "COMPLETED":
        raise ProviderExecutionError(
            "BACKGROUND_CONFIRMATION_NOT_COMPLETED",
            "confirmation response regressed to a pending state",
        )


def _validate_snapshot(
    response: dict[str, object],
    *,
    expected_response_id: str | None,
    expectations: ReceiptExpectations,
) -> str:
    response_id = response.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise ProviderExecutionError(
            "BACKGROUND_RESPONSE_ID",
            "provider response ID is absent or malformed",
        )
    if expected_response_id is not None and response_id != expected_response_id:
        raise ProviderExecutionError(
            "BACKGROUND_RESPONSE_ID_CHANGED",
            "provider response ID changed while polling",
            diagnostics={
                "expected_response_id_sha256": canonical_sha256(expected_response_id),
                "actual_response_id_sha256": canonical_sha256(response_id),
            },
        )
    checks = {
        "$.object": ("response", response.get("object")),
        "$.model": (expectations.provider_model_id, response.get("model")),
        "$.metadata": (expectations.metadata, response.get("metadata")),
        "$.reasoning.effort": (
            expectations.reasoning_effort,
            _reasoning_effort(response),
        ),
        "$.text.format": (expectations.provider_format, _response_format(response)),
        "$.background": (True, response.get("background")),
    }
    for path, (expected, actual) in checks.items():
        if actual != expected:
            raise ProviderExecutionError(
                "BACKGROUND_ACKNOWLEDGEMENT_BINDING",
                f"provider response binding differs at {path}",
                diagnostics={
                    "path": path,
                    "expected_sha256": canonical_sha256(expected),
                    "actual_sha256": canonical_sha256(actual),
                },
            )
    created_at = response.get("created_at")
    if not isinstance(created_at, int | float) or created_at <= 0:
        raise ProviderExecutionError(
            "BACKGROUND_RESPONSE_ID",
            "provider creation timestamp is absent or malformed",
        )
    return response_id


def _reasoning_effort(response: dict[str, object]) -> object:
    reasoning = response.get("reasoning")
    return reasoning.get("effort") if isinstance(reasoning, dict) else None


def _response_format(response: dict[str, object]) -> object:
    text = response.get("text")
    return text.get("format") if isinstance(text, dict) else None


def _receipt_error(
    error: ReceiptBoundaryError,
    *,
    response_id: str,
    polling_retrieval_requests: int,
    confirmation_retrieval_requests: int,
    input_item_retrieval_requests: int = 0,
) -> ProviderExecutionError:
    return ProviderExecutionError(
        error.stage,
        error.root_cause,
        diagnostics={
            **_counts(
                polling_retrieval_requests=polling_retrieval_requests,
                confirmation_retrieval_requests=confirmation_retrieval_requests,
                input_item_retrieval_requests=input_item_retrieval_requests,
            ),
            "response_id": response_id,
            **error.diagnostics,
        },
    )


def _counts(
    *,
    polling_retrieval_requests: int = 0,
    confirmation_retrieval_requests: int = 0,
    input_item_retrieval_requests: int = 0,
) -> dict[str, object]:
    return {
        "provider_creation_calls": 1,
        "model_generation_calls": 1,
        "polling_retrieval_requests": polling_retrieval_requests,
        "confirmation_retrieval_requests": confirmation_retrieval_requests,
        "input_item_retrieval_requests": input_item_retrieval_requests,
        "provider_retries": 0,
        "duplicate_creation_calls": 0,
    }


def _api_response_dict(response: _Dumpable) -> dict[str, object]:
    return response.to_dict(
        mode="json",
        use_api_names=True,
        exclude_unset=True,
        exclude_none=False,
    )


__all__ = ["BackgroundExecutionRuntime", "execute_background_provider_call"]
