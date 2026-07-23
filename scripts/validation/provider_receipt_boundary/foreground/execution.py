"""One direct foreground creation followed by confirmation and input custody."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

from openai import OpenAI
from pydantic import BaseModel

from scripts.validation.provider_receipt_boundary import (
    ReceiptBoundaryError,
    UsageAccounting,
    validate_provider_receipt_telemetry_v2,
)
from scripts.validation.provider_receipt_boundary.canonical_payload import (
    StructuredPayloadError,
    extract_canonical_payload,
)
from scripts.validation.provider_receipt_boundary.foreground.contracts import (
    ForegroundExecutionRuntime,
    ForegroundProviderExecution,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)

if TYPE_CHECKING:
    from scripts.validation.provider_receipt_boundary.background.contracts import (
        TelemetryProviderRequestV2,
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


def execute_foreground_provider_call_telemetry_v2(
    *,
    api_key: str,
    request: TelemetryProviderRequestV2,
    request_timeout_seconds: float,
    output_model: type[_OutputT],
    runtime: ForegroundExecutionRuntime | None = None,
) -> ForegroundProviderExecution[_OutputT]:
    """Create exactly once without a generation ceiling or background queue."""

    if request_timeout_seconds <= 0:
        raise ValueError("foreground request timeout must be positive")
    active = runtime or ForegroundExecutionRuntime()
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
    try:
        created = client.responses.create(
            model=request.provider_model_id,
            input=request.provider_input,
            reasoning={"effort": request.reasoning_effort},
            text={"format": request.provider_format},
            metadata=request.metadata,
            store=True,
            timeout=request_timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - creation is never repeated.
        raise ProviderExecutionError(
            "FOREGROUND_CREATION",
            type(exc).__name__,
            diagnostics={
                **_counts(),
                "response_id_available": False,
                "duplicate_creation_may_exist": type(exc).__name__
                in {"APITimeoutError", "TimeoutError"},
            },
        ) from exc
    creation = _api_response_dict(created)
    response_id = _response_id(creation)
    if active.on_completed is not None:
        try:
            active.on_completed(response_id)
        except Exception as exc:  # noqa: BLE001 - custody callback fails closed.
            raise ProviderExecutionError(
                "FOREGROUND_COMPLETION_CUSTODY",
                type(exc).__name__,
                diagnostics={**_counts(), "response_id": response_id},
            ) from exc

    try:
        confirmed = client.responses.retrieve(
            response_id,
            timeout=request_timeout_seconds,
        )
        confirmation = _api_response_dict(confirmed)
    except Exception as exc:  # noqa: BLE001 - confirmation is never retried.
        raise ProviderExecutionError(
            "FOREGROUND_CONFIRMATION_RETRIEVAL",
            type(exc).__name__,
            diagnostics={
                **_counts(confirmation_retrieval_requests=1),
                "response_id": response_id,
                **_usage_diagnostics(
                    request=request,
                    creation=creation,
                    confirmation=None,
                    latency_seconds=active.monotonic() - started,
                ),
            },
        ) from exc

    try:
        page = client.responses.input_items.list(
            response_id,
            limit=100,
            order="asc",
            timeout=request_timeout_seconds,
        )
        input_items = tuple(_api_response_dict(item) for item in page)
    except Exception as exc:  # noqa: BLE001 - input custody is never retried.
        raise ProviderExecutionError(
            "FOREGROUND_INPUT_RETRIEVAL",
            type(exc).__name__,
            diagnostics={
                **_counts(
                    confirmation_retrieval_requests=1,
                    input_item_retrieval_requests=1,
                ),
                "response_id": response_id,
                **_usage_diagnostics(
                    request=request,
                    creation=creation,
                    confirmation=confirmation,
                    latency_seconds=active.monotonic() - started,
                ),
            },
        ) from exc

    latency_seconds = active.monotonic() - started
    try:
        validation = validate_provider_receipt_telemetry_v2(
            creation=creation,
            retrieval=confirmation,
            input_items=input_items,
            expectations=request.receipt_expectations(),
            latency_seconds=latency_seconds,
        )
    except ReceiptBoundaryError as exc:
        raise ProviderExecutionError(
            exc.stage,
            exc.root_cause,
            diagnostics={
                **_counts(
                    confirmation_retrieval_requests=1,
                    input_item_retrieval_requests=1,
                ),
                "response_id": response_id,
                **_usage_diagnostics(
                    request=request,
                    creation=creation,
                    confirmation=confirmation,
                    latency_seconds=latency_seconds,
                ),
                **exc.diagnostics,
            },
        ) from exc

    try:
        canonical_payload = extract_canonical_payload(confirmation)
    except StructuredPayloadError as exc:
        raise ProviderExecutionError(
            "STRUCTURED_OUTPUT_PAYLOAD",
            str(exc),
            diagnostics={
                **_counts(
                    confirmation_retrieval_requests=1,
                    input_item_retrieval_requests=1,
                ),
                "response_id": response_id,
                "observed_usage": asdict(validation.usage),
            },
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
                **_counts(
                    confirmation_retrieval_requests=1,
                    input_item_retrieval_requests=1,
                ),
                "response_id": response_id,
                "scientific_payload_sha256": canonical_payload.sha256,
                "observed_usage": asdict(validation.usage),
            },
        ) from exc
    receipt = validation.as_json()
    receipt.update(
        {
            **_counts(
                confirmation_retrieval_requests=1,
                input_item_retrieval_requests=1,
            ),
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
            "transport": "DIRECT_OPENAI_FOREGROUND_RESPONSES",
            "foreground_request_timeout_seconds": request_timeout_seconds,
        }
    )
    return ForegroundProviderExecution(
        extraction=parsed,
        canonical_payload=canonical_payload.payload,
        creation_response=creation,
        confirmation_response=confirmation,
        receipt=receipt,
    )


def _response_id(response: dict[str, object]) -> str:
    value = response.get("id")
    if not isinstance(value, str) or not value:
        raise ProviderExecutionError(
            "FOREGROUND_RESPONSE_ID",
            "provider response ID is absent or malformed",
            diagnostics=_counts(),
        )
    return value


def _usage_diagnostics(
    *,
    request: TelemetryProviderRequestV2,
    creation: dict[str, object],
    confirmation: dict[str, object] | None,
    latency_seconds: float,
) -> dict[str, object]:
    creation_usage = creation.get("usage")
    confirmation_usage = (
        confirmation.get("usage") if confirmation is not None else creation_usage
    )
    if not isinstance(creation_usage, dict) or creation_usage != confirmation_usage:
        return {}
    try:
        input_tokens = _usage_int(creation_usage, "input_tokens")
        output_tokens = _usage_int(creation_usage, "output_tokens")
        total_tokens = _usage_int(creation_usage, "total_tokens")
        input_details = creation_usage["input_tokens_details"]
        output_details = creation_usage["output_tokens_details"]
        if not isinstance(input_details, dict) or not isinstance(
            output_details,
            dict,
        ):
            return {}
        cached_tokens = _usage_int(input_details, "cached_tokens")
        reasoning_tokens = _usage_int(output_details, "reasoning_tokens")
    except (KeyError, ValueError):
        return {}
    if cached_tokens > input_tokens or total_tokens != input_tokens + output_tokens:
        return {}
    pricing = request.pricing
    usage = UsageAccounting(
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
    return {"observed_usage": asdict(usage)}


def _usage_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or item < 0:
        raise ValueError(f"usage {key} is absent")
    return item


def _counts(
    *,
    confirmation_retrieval_requests: int = 0,
    input_item_retrieval_requests: int = 0,
) -> dict[str, object]:
    return {
        "provider_creation_calls": 1,
        "model_generation_calls": 1,
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


__all__ = ["execute_foreground_provider_call_telemetry_v2"]
