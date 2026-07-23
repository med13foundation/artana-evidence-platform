"""V13-only foreground execution with lossless rejected-call evidence."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Generic, NoReturn, Protocol, TypeVar, cast

from openai import OpenAI
from pydantic import BaseModel

from scripts.validation.provider_receipt_boundary import (
    ReceiptBoundaryError,
    UsageAccounting,
)
from scripts.validation.provider_receipt_boundary.canonical_payload import (
    StructuredPayloadError,
    extract_canonical_payload,
)
from scripts.validation.provider_receipt_boundary.foreground.validation import (
    validate_foreground_provider_receipt_telemetry_v3,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.request_contract import (
        V13ForegroundProviderRequest,
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
class V13ForegroundExecutionRuntime:
    """Injectable V13 transport boundary; never supplies a retry or fallback."""

    client: object | None = None
    monotonic: Callable[[], float] = time.monotonic
    on_completed: Callable[[str], None] | None = None


@dataclass(frozen=True, slots=True)
class V13TransportEvidence:
    """Every serializable fact recovered from one provider creation attempt."""

    response_ids: tuple[str, ...]
    creation_response: dict[str, object] | None
    confirmation_response: dict[str, object] | None
    input_items: tuple[dict[str, object], ...] | None
    canonical_payload: dict[str, object] | None
    usage: dict[str, object] | None
    latency_seconds: float
    provider_creation_calls: int
    completed_provider_calls: int
    confirmation_retrieval_requests: int
    input_item_retrieval_requests: int
    provider_retries: int = 0
    duplicate_creation_calls: int = 0

    @property
    def usage_accounting_status(self) -> str:
        return "ACCOUNTED" if self.usage is not None else "UNACCOUNTED_UNKNOWN"

    def counters_json(self) -> dict[str, object]:
        return {
            "provider_creation_calls": self.provider_creation_calls,
            "completed_provider_calls": self.completed_provider_calls,
            "confirmation_retrieval_requests": (self.confirmation_retrieval_requests),
            "input_item_retrieval_requests": self.input_item_retrieval_requests,
            "provider_retries": self.provider_retries,
            "duplicate_creation_calls": self.duplicate_creation_calls,
        }

    def as_json(self) -> dict[str, object]:
        return {
            "response_ids": list(self.response_ids),
            "creation_response": self.creation_response,
            "confirmation_response": self.confirmation_response,
            "input_items": (
                list(self.input_items) if self.input_items is not None else None
            ),
            "canonical_payload": self.canonical_payload,
            "usage": self.usage,
            "usage_accounting_status": self.usage_accounting_status,
            "latency_seconds": self.latency_seconds,
            **self.counters_json(),
        }


class V13ProviderExecutionError(RuntimeError):
    """One V13 attempt was rejected while retaining all available evidence."""

    def __init__(
        self,
        stage: str,
        root_cause: str,
        *,
        evidence: V13TransportEvidence,
        boundary_diagnostics: dict[str, object] | None = None,
    ) -> None:
        diagnostics: dict[str, object] = {
            **evidence.counters_json(),
            "response_ids": list(evidence.response_ids),
            "response_id": (
                evidence.response_ids[0] if evidence.response_ids else None
            ),
            "latency_seconds": evidence.latency_seconds,
            "usage_accounting_status": evidence.usage_accounting_status,
        }
        if evidence.usage is not None:
            diagnostics["observed_usage"] = evidence.usage
        if boundary_diagnostics:
            diagnostics["boundary_diagnostics"] = boundary_diagnostics
        super().__init__(f"{stage}: {root_cause}")
        self.stage = stage
        self.root_cause = root_cause
        self.diagnostics = diagnostics
        self.evidence = evidence


@dataclass(frozen=True, slots=True)
class V13ProviderExecution(Generic[_OutputT]):
    """A scientifically admitted V13 output plus complete transport custody."""

    extraction: _OutputT
    canonical_payload: dict[str, object]
    creation_response: dict[str, object]
    confirmation_response: dict[str, object]
    input_items: tuple[dict[str, object], ...]
    receipt: dict[str, object]

    def transport_evidence(self) -> V13TransportEvidence:
        usage = self.receipt.get("usage")
        return V13TransportEvidence(
            response_ids=_response_ids(
                self.creation_response,
                self.confirmation_response,
            ),
            creation_response=self.creation_response,
            confirmation_response=self.confirmation_response,
            input_items=self.input_items,
            canonical_payload=self.canonical_payload,
            usage=usage if isinstance(usage, dict) else None,
            latency_seconds=_receipt_latency(self.receipt),
            provider_creation_calls=_receipt_int(
                self.receipt,
                "provider_creation_calls",
            ),
            completed_provider_calls=_receipt_int(
                self.receipt,
                "completed_provider_calls",
            ),
            confirmation_retrieval_requests=_receipt_int(
                self.receipt,
                "confirmation_retrieval_requests",
            ),
            input_item_retrieval_requests=_receipt_int(
                self.receipt,
                "input_item_retrieval_requests",
            ),
            provider_retries=_receipt_int(self.receipt, "provider_retries"),
            duplicate_creation_calls=_receipt_int(
                self.receipt,
                "duplicate_creation_calls",
            ),
        )


@dataclass(frozen=True, slots=True)
class _PendingFailure:
    stage: str
    root_cause: str
    diagnostics: dict[str, object]


@dataclass(frozen=True, slots=True)
class _TransportSnapshot:
    creation: dict[str, object] | None
    confirmation: dict[str, object] | None
    input_items: tuple[dict[str, object], ...] | None
    canonical_payload: dict[str, object] | None
    completed_provider_calls: int
    confirmation_requests: int
    input_requests: int


@dataclass(frozen=True, slots=True)
class _ValidationContext:
    request: V13ForegroundProviderRequest
    snapshot: _TransportSnapshot
    canonical_error: str | None
    latency_seconds: float
    request_timeout_seconds: float


def execute_v13_foreground_call(
    *,
    api_key: str,
    request: V13ForegroundProviderRequest,
    request_timeout_seconds: float,
    output_model: type[_OutputT],
    runtime: V13ForegroundExecutionRuntime | None = None,
) -> V13ProviderExecution[_OutputT]:
    """Create once, retrieve once, and retain partial custody on every failure."""

    if request_timeout_seconds <= 0:
        raise ValueError("foreground request timeout must be positive")
    active = runtime or V13ForegroundExecutionRuntime()
    client = cast(
        "_Client",
        active.client
        or OpenAI(
            api_key=api_key,
            max_retries=0,
            timeout=request_timeout_seconds,
        ),
    )
    started = active.monotonic()
    creation = _create_once(
        client,
        request,
        request_timeout_seconds,
        started,
        active.monotonic,
    )
    response_id = _require_response_id(
        creation,
        request,
        started,
        active.monotonic,
    )
    confirmation, input_items, failures = _collect_custody(
        client,
        response_id,
        request_timeout_seconds,
        active.on_completed,
    )
    canonical, canonical_error = _canonical_payload(confirmation)
    snapshot = _TransportSnapshot(
        creation=creation,
        confirmation=confirmation,
        input_items=input_items,
        canonical_payload=canonical,
        completed_provider_calls=1,
        confirmation_requests=1,
        input_requests=1,
    )
    latency_seconds = active.monotonic() - started
    if failures:
        _raise_failure(
            failures[0],
            request,
            snapshot,
            latency_seconds,
            boundary_diagnostics={
                "all_failures": [
                    {
                        "stage": item.stage,
                        "root_cause": item.root_cause,
                        "diagnostics": item.diagnostics,
                    }
                    for item in failures
                ]
            },
        )
    if confirmation is None or input_items is None:
        raise AssertionError("successful retrievals are unexpectedly absent")
    validation_context = _ValidationContext(
        request=request,
        snapshot=snapshot,
        canonical_error=canonical_error,
        latency_seconds=latency_seconds,
        request_timeout_seconds=request_timeout_seconds,
    )
    return _validate_execution(validation_context, output_model)


def _validate_execution(
    context: _ValidationContext,
    output_model: type[_OutputT],
) -> V13ProviderExecution[_OutputT]:
    request = context.request
    snapshot = context.snapshot
    canonical_error = context.canonical_error
    latency_seconds = context.latency_seconds
    creation = _present(snapshot.creation, "creation")
    confirmation = _present(snapshot.confirmation, "confirmation")
    input_items = snapshot.input_items
    if input_items is None:
        raise AssertionError("input custody is unexpectedly absent")
    try:
        validation = validate_foreground_provider_receipt_telemetry_v3(
            creation=creation,
            confirmation=confirmation,
            input_items=input_items,
            expectations=request.receipt_expectations(),
            latency_seconds=latency_seconds,
        )
    except ReceiptBoundaryError as exc:
        _raise_failure(
            _PendingFailure(exc.stage, exc.root_cause, exc.diagnostics),
            request,
            snapshot,
            latency_seconds,
            boundary_diagnostics=exc.diagnostics,
        )

    canonical = snapshot.canonical_payload
    if canonical_error is not None or canonical is None:
        _raise_failure(
            _PendingFailure(
                "STRUCTURED_OUTPUT_PAYLOAD",
                canonical_error or "canonical payload is absent",
                {},
            ),
            request,
            snapshot,
            latency_seconds,
        )
    try:
        parsed = output_model.model_validate_json(
            json.dumps(canonical, separators=(",", ":"))
        )
    except Exception as exc:  # noqa: BLE001 - frozen schema fails closed.
        _raise_failure(
            _PendingFailure("STRUCTURED_OUTPUT_SCHEMA", type(exc).__name__, {}),
            request,
            snapshot,
            latency_seconds,
        )
    receipt = validation.receipt
    receipt.update(
        {
            "provider_creation_calls": 1,
            "completed_provider_calls": 1,
            "confirmation_retrieval_requests": 1,
            "input_item_retrieval_requests": 1,
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
            "transport": "DIRECT_OPENAI_FOREGROUND_RESPONSES",
            "foreground_request_timeout_seconds": (context.request_timeout_seconds),
            "v13_transport_custody": {
                "creation_response": creation,
                "confirmation_response": confirmation,
                "input_items": list(input_items),
            },
        }
    )
    return V13ProviderExecution(
        extraction=parsed,
        canonical_payload=canonical,
        creation_response=creation,
        confirmation_response=confirmation,
        input_items=input_items,
        receipt=receipt,
    )


def reject_verified_execution(
    execution: V13ProviderExecution[BaseModel],
    *,
    stage: str,
    root_cause: str,
    diagnostics: dict[str, object] | None = None,
) -> V13ProviderExecutionError:
    """Reclassify an unadmitted verified return without losing its custody."""

    return V13ProviderExecutionError(
        stage,
        root_cause,
        evidence=execution.transport_evidence(),
        boundary_diagnostics=diagnostics,
    )


def _create_once(
    client: _Client,
    request: V13ForegroundProviderRequest,
    timeout: float,
    started: float,
    monotonic: Callable[[], float],
) -> dict[str, object]:
    empty = _TransportSnapshot(None, None, None, None, 0, 0, 0)
    try:
        created = client.responses.create(
            model=request.provider_model_id,
            input=request.provider_input,
            reasoning={"effort": request.reasoning_effort},
            text={"format": request.provider_format},
            metadata=request.metadata,
            store=True,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 - exactly one creation, never retry.
        _raise_failure(
            _PendingFailure("FOREGROUND_CREATION", type(exc).__name__, {}),
            request,
            empty,
            monotonic() - started,
            boundary_diagnostics={
                "duplicate_creation_may_exist": type(exc).__name__
                in {"APITimeoutError", "TimeoutError"}
            },
        )
    try:
        return _api_response_dict(created)
    except Exception as exc:  # noqa: BLE001 - provider returned but no envelope.
        snapshot = _TransportSnapshot(None, None, None, None, 1, 0, 0)
        _raise_failure(
            _PendingFailure(
                "FOREGROUND_CREATION_ENVELOPE",
                type(exc).__name__,
                {},
            ),
            request,
            snapshot,
            monotonic() - started,
        )


def _require_response_id(
    creation: dict[str, object],
    request: V13ForegroundProviderRequest,
    started: float,
    monotonic: Callable[[], float],
) -> str:
    response_id = creation.get("id")
    if isinstance(response_id, str) and response_id:
        return response_id
    snapshot = _TransportSnapshot(creation, None, None, None, 1, 0, 0)
    return _raise_failure(
        _PendingFailure(
            "FOREGROUND_RESPONSE_ID",
            "provider response ID is absent or malformed",
            {},
        ),
        request,
        snapshot,
        monotonic() - started,
    )


def _collect_custody(
    client: _Client,
    response_id: str,
    timeout: float,
    on_completed: Callable[[str], None] | None,
) -> tuple[
    dict[str, object] | None,
    tuple[dict[str, object], ...] | None,
    tuple[_PendingFailure, ...],
]:
    failures: list[_PendingFailure] = []
    if on_completed is not None:
        try:
            on_completed(response_id)
        except Exception as exc:  # noqa: BLE001 - retrieval still preserves custody.
            failures.append(
                _PendingFailure(
                    "FOREGROUND_COMPLETION_CUSTODY",
                    type(exc).__name__,
                    {},
                )
            )
    confirmation: dict[str, object] | None = None
    try:
        confirmation = _api_response_dict(
            client.responses.retrieve(response_id, timeout=timeout)
        )
    except Exception as exc:  # noqa: BLE001 - exactly one confirmation request.
        failures.append(
            _PendingFailure(
                "FOREGROUND_CONFIRMATION_RETRIEVAL",
                type(exc).__name__,
                {},
            )
        )
    input_items: tuple[dict[str, object], ...] | None = None
    try:
        page = client.responses.input_items.list(
            response_id,
            limit=100,
            order="asc",
            timeout=timeout,
        )
        input_items = tuple(_api_response_dict(item) for item in page)
    except Exception as exc:  # noqa: BLE001 - exactly one input retrieval request.
        failures.append(
            _PendingFailure(
                "FOREGROUND_INPUT_RETRIEVAL",
                type(exc).__name__,
                {},
            )
        )
    return confirmation, input_items, tuple(failures)


def _raise_failure(
    failure: _PendingFailure,
    request: V13ForegroundProviderRequest,
    snapshot: _TransportSnapshot,
    latency_seconds: float,
    *,
    boundary_diagnostics: dict[str, object] | None = None,
) -> NoReturn:
    usage = _usage(
        request=request,
        creation=snapshot.creation,
        confirmation=snapshot.confirmation,
        latency_seconds=latency_seconds,
    )
    evidence = V13TransportEvidence(
        response_ids=_response_ids(snapshot.creation, snapshot.confirmation),
        creation_response=snapshot.creation,
        confirmation_response=snapshot.confirmation,
        input_items=snapshot.input_items,
        canonical_payload=snapshot.canonical_payload,
        usage=usage,
        latency_seconds=latency_seconds,
        provider_creation_calls=1,
        completed_provider_calls=snapshot.completed_provider_calls,
        confirmation_retrieval_requests=snapshot.confirmation_requests,
        input_item_retrieval_requests=snapshot.input_requests,
    )
    raise V13ProviderExecutionError(
        failure.stage,
        failure.root_cause,
        evidence=evidence,
        boundary_diagnostics=boundary_diagnostics,
    )


def _present(
    value: dict[str, object] | None,
    label: str,
) -> dict[str, object]:
    if value is None:
        raise AssertionError(f"{label} is unexpectedly absent")
    return value


def _canonical_payload(
    confirmation: dict[str, object] | None,
) -> tuple[dict[str, object] | None, str | None]:
    if confirmation is None:
        return None, None
    try:
        payload = extract_canonical_payload(confirmation)
    except StructuredPayloadError as exc:
        return None, str(exc)
    return payload.payload, None


def _usage(
    *,
    request: V13ForegroundProviderRequest,
    creation: dict[str, object] | None,
    confirmation: dict[str, object] | None,
    latency_seconds: float,
) -> dict[str, object] | None:
    for response in (confirmation, creation):
        if response is None:
            continue
        value = response.get("usage")
        if not isinstance(value, dict):
            continue
        try:
            input_tokens = _usage_int(value, "input_tokens")
            output_tokens = _usage_int(value, "output_tokens")
            total_tokens = _usage_int(value, "total_tokens")
            input_details = value.get("input_tokens_details")
            output_details = value.get("output_tokens_details")
            if not isinstance(input_details, dict) or not isinstance(
                output_details,
                dict,
            ):
                continue
            cached_tokens = _usage_int(input_details, "cached_tokens")
            reasoning_tokens = _usage_int(output_details, "reasoning_tokens")
        except ValueError:
            continue
        if (
            cached_tokens > input_tokens
            or reasoning_tokens > output_tokens
            or total_tokens != input_tokens + output_tokens
        ):
            continue
        pricing = request.pricing
        return asdict(
            UsageAccounting(
                input_tokens=input_tokens,
                cached_input_tokens=cached_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                total_tokens=total_tokens,
                latency_seconds=latency_seconds,
                cost_usd=(
                    (input_tokens - cached_tokens) * pricing["input"]
                    + cached_tokens * pricing["cached_input"]
                    + output_tokens * pricing["output"]
                ),
            )
        )
    return None


def _usage_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or item < 0:
        raise ValueError(f"usage {key} is absent")
    return item


def _response_ids(
    *responses: dict[str, object] | None,
) -> tuple[str, ...]:
    values: list[str] = []
    for response in responses:
        if response is None:
            continue
        response_id = response.get("id")
        if isinstance(response_id, str) and response_id and response_id not in values:
            values.append(response_id)
    return tuple(values)


def _receipt_latency(receipt: dict[str, object]) -> float:
    usage = receipt.get("usage")
    if not isinstance(usage, dict):
        raise TypeError("V13 receipt usage is absent")
    value = usage.get("latency_seconds")
    if not isinstance(value, int | float):
        raise TypeError("V13 receipt latency is absent")
    return float(value)


def _receipt_int(receipt: dict[str, object], key: str) -> int:
    value = receipt.get(key)
    if not isinstance(value, int):
        raise TypeError(f"V13 receipt {key} is absent")
    return value


def _api_response_dict(response: _Dumpable) -> dict[str, object]:
    return response.to_dict(
        mode="json",
        use_api_names=True,
        exclude_unset=True,
        exclude_none=False,
    )


__all__ = [
    "V13ForegroundExecutionRuntime",
    "V13ProviderExecution",
    "V13ProviderExecutionError",
    "V13TransportEvidence",
    "execute_v13_foreground_call",
    "reject_verified_execution",
]
