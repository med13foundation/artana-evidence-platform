"""Exactly-once provider transport orchestrating the receipt boundary."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar, cast

from openai import OpenAI
from pydantic import BaseModel

from scripts.validation.provider_receipt_boundary import (
    ReceiptBoundaryError,
    ReceiptExpectations,
    validate_provider_receipt,
)
from scripts.validation.provider_receipt_boundary.canonical_payload import (
    extract_canonical_payload,
)

_OutputT = TypeVar("_OutputT", bound=BaseModel)


class ProviderExecutionError(RuntimeError):
    """The one provider attempt failed an execution-integrity boundary."""

    def __init__(
        self,
        stage: str,
        root_cause: str,
        *,
        diagnostics: dict[str, object] | None = None,
    ) -> None:
        super().__init__(f"{stage}: {root_cause}")
        self.stage = stage
        self.root_cause = root_cause
        self.diagnostics = diagnostics or {}


@dataclass(frozen=True, slots=True)
class ProviderExecution(Generic[_OutputT]):
    """Verified output and receipt from one provider model call."""

    extraction: _OutputT
    creation_response: dict[str, object]
    retrieval_response: dict[str, object]
    receipt: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Frozen provider request and all deterministic budget boundaries."""

    provider_input: str
    provider_format: dict[str, object]
    provider_model_id: str
    reasoning_effort: str
    max_output_tokens: int
    max_total_tokens: int
    max_cost_usd: float
    max_latency_seconds: float
    pricing: dict[str, float]
    metadata: dict[str, str]

    def receipt_expectations(self) -> ReceiptExpectations:
        return ReceiptExpectations(
            provider_input=self.provider_input,
            provider_format=self.provider_format,
            provider_model_id=self.provider_model_id,
            reasoning_effort=self.reasoning_effort,
            metadata=self.metadata,
            max_total_tokens=self.max_total_tokens,
            max_cost_usd=self.max_cost_usd,
            max_latency_seconds=self.max_latency_seconds,
            pricing=self.pricing,
        )


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
    def list(self, response_id: str, *, limit: int, order: str) -> _InputPage: ...


class _Responses(Protocol):
    def create(self, **kwargs: object) -> _Dumpable: ...

    def retrieve(self, response_id: str) -> _Dumpable: ...

    input_items: _InputItems


class _Client(Protocol):
    responses: _Responses


def execute_single_provider_call(
    *,
    api_key: str,
    request: ProviderRequest,
    output_model: type[_OutputT],
    client: _Client | None = None,
) -> ProviderExecution[_OutputT]:
    """Make one model call, retrieve once, and delegate all receipt decisions."""

    provider_client = client or cast(
        "_Client",
        OpenAI(api_key=api_key, max_retries=0, timeout=request.max_latency_seconds),
    )
    started = time.monotonic()
    try:
        response = provider_client.responses.create(
            model=request.provider_model_id,
            input=request.provider_input,
            reasoning={"effort": request.reasoning_effort},
            max_output_tokens=request.max_output_tokens,
            text={"format": request.provider_format},
            metadata=request.metadata,
            store=True,
        )
    except Exception as exc:  # noqa: BLE001 - exactly one attempt, never retry.
        raise ProviderExecutionError("PROVIDER_CALL", type(exc).__name__) from exc
    latency_seconds = time.monotonic() - started
    creation = _api_response_dict(response)
    response_id = creation.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise ProviderExecutionError("PROVIDER_ENVELOPE", "response ID is absent")
    try:
        retrieval = _api_response_dict(provider_client.responses.retrieve(response_id))
        page = provider_client.responses.input_items.list(
            response_id, limit=100, order="asc"
        )
        input_items = tuple(_api_response_dict(item) for item in page)
    except Exception as exc:  # noqa: BLE001 - receipt retrieval is not a model retry.
        raise ProviderExecutionError(
            "RECEIPT_RETRIEVAL",
            type(exc).__name__,
            diagnostics={"response_id": response_id},
        ) from exc
    try:
        validation = validate_provider_receipt(
            creation=creation,
            retrieval=retrieval,
            input_items=input_items,
            expectations=request.receipt_expectations(),
            latency_seconds=latency_seconds,
        )
    except ReceiptBoundaryError as exc:
        raise ProviderExecutionError(
            exc.stage,
            exc.root_cause,
            diagnostics={"response_id": response_id, **exc.diagnostics},
        ) from exc
    canonical_payload = extract_canonical_payload(retrieval)
    try:
        parsed = output_model.model_validate_json(
            json.dumps(canonical_payload.payload, separators=(",", ":"))
        )
    except Exception as exc:  # noqa: BLE001 - frozen output schema must fail closed.
        raise ProviderExecutionError(
            "STRUCTURED_OUTPUT_SCHEMA",
            type(exc).__name__,
            diagnostics={
                "response_id": response_id,
                "scientific_payload_sha256": canonical_payload.sha256,
            },
        ) from exc
    receipt = validation.as_json()
    receipt.update({"provider_calls": 1, "provider_retries": 0})
    return ProviderExecution(
        extraction=parsed,
        creation_response=creation,
        retrieval_response=retrieval,
        receipt=receipt,
    )


def _api_response_dict(response: _Dumpable) -> dict[str, object]:
    """Serialize provider models with wire aliases and only API-returned fields."""

    return response.to_dict(
        mode="json",
        use_api_names=True,
        exclude_unset=True,
        exclude_none=False,
    )


__all__ = [
    "ProviderExecution",
    "ProviderExecutionError",
    "ProviderRequest",
    "execute_single_provider_call",
]
