"""Exactly-once provider transport and live receipt verification."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Protocol, cast

from openai import OpenAI

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    ScientificEventExtraction,
)


class ProviderExecutionError(RuntimeError):
    """The one provider attempt failed an execution-integrity boundary."""

    def __init__(self, stage: str, root_cause: str) -> None:
        super().__init__(f"{stage}: {root_cause}")
        self.stage = stage
        self.root_cause = root_cause


@dataclass(frozen=True, slots=True)
class ProviderExecution:
    """Verified output and receipt from one provider model call."""

    extraction: ScientificEventExtraction
    raw_response: dict[str, object]
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


@dataclass(frozen=True, slots=True)
class _ReceiptContext:
    request: ProviderRequest
    latency_seconds: float


class _Dumpable(Protocol):
    def model_dump(self, *, mode: str) -> dict[str, object]: ...


class _Responses(Protocol):
    def create(self, **kwargs: object) -> _Dumpable: ...

    def retrieve(self, response_id: str) -> _Dumpable: ...

    @property
    def input_items(self) -> object: ...


class _Client(Protocol):
    responses: _Responses


def execute_single_provider_call(
    *,
    api_key: str,
    request: ProviderRequest,
    client: _Client | None = None,
) -> ProviderExecution:
    """Make one model call, then retrieve and verify its immutable receipt."""

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
    except Exception as exc:  # noqa: BLE001 - no retry; preserve exact failure.
        raise ProviderExecutionError("PROVIDER_CALL", type(exc).__name__) from exc
    latency_seconds = time.monotonic() - started
    raw_response = response.model_dump(mode="json")
    response_id = _required_string(raw_response, "id")
    try:
        retrieved = provider_client.responses.retrieve(response_id).model_dump(
            mode="json"
        )
        input_items_api = cast(
            "object",
            provider_client.responses.input_items,
        )
        page = input_items_api.list(response_id, limit=100, order="asc")  # type: ignore[attr-defined]
        input_items = tuple(item.model_dump(mode="json") for item in page)
    except Exception as exc:  # noqa: BLE001 - receipt failure is terminal.
        raise ProviderExecutionError("RECEIPT_RETRIEVAL", type(exc).__name__) from exc
    receipt = _verify_receipt(
        initial=raw_response,
        retrieved=retrieved,
        input_items=input_items,
        context=_ReceiptContext(request=request, latency_seconds=latency_seconds),
    )
    try:
        extraction = ScientificEventExtraction.model_validate_json(
            _structured_output_text(retrieved)
        )
    except Exception as exc:  # noqa: BLE001 - frozen schema failure is terminal.
        raise ProviderExecutionError("STRUCTURED_OUTPUT_SCHEMA", type(exc).__name__) from exc
    return ProviderExecution(
        extraction=extraction,
        raw_response=raw_response,
        receipt=receipt,
    )


def _verify_receipt(
    *,
    initial: dict[str, object],
    retrieved: dict[str, object],
    input_items: tuple[dict[str, object], ...],
    context: _ReceiptContext,
) -> dict[str, object]:
    _verify_response_envelope(initial, retrieved, context.request)
    retrieved_output_hash = _verify_output_binding(initial, retrieved)
    _verify_input_and_schema(input_items, retrieved, context.request)
    return _usage_receipt(
        response_id=_required_string(initial, "id"),
        retrieved=retrieved,
        output_hash=retrieved_output_hash,
        context=context,
    )


def _verify_response_envelope(
    initial: dict[str, object],
    retrieved: dict[str, object],
    request: ProviderRequest,
) -> None:
    response_id = _required_string(initial, "id")
    if retrieved.get("id") != response_id:
        raise ProviderExecutionError("RECEIPT_ID", "retrieved response ID differs")
    if retrieved.get("status") != "completed" or retrieved.get("error") is not None:
        raise ProviderExecutionError("RECEIPT_STATUS", "response is not completed")
    if retrieved.get("incomplete_details") is not None:
        raise ProviderExecutionError("RECEIPT_STATUS", "response is incomplete")
    if retrieved.get("model") != request.provider_model_id:
        raise ProviderExecutionError("RECEIPT_MODEL", "provider model differs")
    reasoning = retrieved.get("reasoning")
    if not isinstance(reasoning, dict) or reasoning.get("effort") != request.reasoning_effort:
        raise ProviderExecutionError("RECEIPT_REASONING", "reasoning effort differs")
    if retrieved.get("metadata") != request.metadata:
        raise ProviderExecutionError("RECEIPT_METADATA", "custody metadata differs")


def _verify_output_binding(
    initial: dict[str, object], retrieved: dict[str, object]
) -> str:
    initial_output_hash = _canonical_sha256(initial.get("output"))
    retrieved_output_hash = _canonical_sha256(retrieved.get("output"))
    if initial_output_hash != retrieved_output_hash:
        raise ProviderExecutionError(
            "RECEIPT_OUTPUT", "created and retrieved provider outputs differ"
        )
    return retrieved_output_hash


def _verify_input_and_schema(
    input_items: tuple[dict[str, object], ...],
    retrieved: dict[str, object],
    request: ProviderRequest,
) -> None:
    actual_input = _single_user_input(input_items)
    if actual_input != request.provider_input:
        raise ProviderExecutionError("RECEIPT_INPUT", "retrieved model input differs")
    text = retrieved.get("text")
    if not isinstance(text, dict) or not isinstance(text.get("format"), dict):
        raise ProviderExecutionError("RECEIPT_SCHEMA", "response schema is absent")
    retrieved_format = text["format"]
    if retrieved_format != request.provider_format:
        raise ProviderExecutionError("RECEIPT_SCHEMA", "response schema differs")


def _usage_receipt(
    *,
    response_id: str,
    retrieved: dict[str, object],
    output_hash: str,
    context: _ReceiptContext,
) -> dict[str, object]:
    request = context.request
    usage = retrieved.get("usage")
    if not isinstance(usage, dict):
        raise ProviderExecutionError("RECEIPT_USAGE", "provider usage is absent")
    input_tokens = _required_int(usage, "input_tokens")
    output_tokens = _required_int(usage, "output_tokens")
    total_tokens = _required_int(usage, "total_tokens")
    details = usage.get("input_tokens_details")
    cached_tokens = (
        details.get("cached_tokens", 0) if isinstance(details, dict) else 0
    )
    if not isinstance(cached_tokens, int) or cached_tokens < 0:
        raise ProviderExecutionError("RECEIPT_USAGE", "cached token count is invalid")
    cost_usd = (
        (input_tokens - cached_tokens) * request.pricing["input"]
        + cached_tokens * request.pricing["cached_input"]
        + output_tokens * request.pricing["output"]
    )
    if total_tokens > request.max_total_tokens:
        raise ProviderExecutionError("TOKEN_BUDGET", "total token ceiling exceeded")
    if context.latency_seconds > request.max_latency_seconds:
        raise ProviderExecutionError("LATENCY_BUDGET", "latency ceiling exceeded")
    if cost_usd > request.max_cost_usd:
        raise ProviderExecutionError("COST_BUDGET", "cost ceiling exceeded")
    return {
        "status": "VERIFIED_LIVE",
        "provider_calls": 1,
        "provider_retries": 0,
        "response_id": response_id,
        "model": request.provider_model_id,
        "reasoning_effort": request.reasoning_effort,
        "provider_output_sha256": output_hash,
        "structured_payload_sha256": _canonical_sha256(
            json.loads(_structured_output_text(retrieved))
        ),
        "provider_input_sha256": hashlib.sha256(
            request.provider_input.encode()
        ).hexdigest(),
        "provider_response_format_sha256": _canonical_sha256(
            request.provider_format
        ),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "latency_seconds": context.latency_seconds,
        "cost_usd": cost_usd,
        "cost_basis": "frozen per-token rates applied deterministically to provider usage",
    }


def _single_user_input(input_items: tuple[dict[str, object], ...]) -> str:
    if len(input_items) != 1:
        raise ProviderExecutionError("RECEIPT_INPUT", "input topology is not singular")
    item = input_items[0]
    content = item.get("content")
    if item.get("type") != "message" or item.get("role") != "user":
        raise ProviderExecutionError("RECEIPT_INPUT", "input is not one user message")
    if not isinstance(content, list) or len(content) != 1:
        raise ProviderExecutionError("RECEIPT_INPUT", "input content is not singular")
    part = content[0]
    if not isinstance(part, dict) or part.get("type") != "input_text":
        raise ProviderExecutionError("RECEIPT_INPUT", "input part is not input_text")
    return _required_string(part, "text")


def _structured_output_text(response: dict[str, object]) -> str:
    output = response.get("output")
    if not isinstance(output, list):
        raise ProviderExecutionError("STRUCTURED_OUTPUT", "output array is absent")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                texts.append(_required_string(part, "text"))
    if len(texts) != 1:
        raise ProviderExecutionError(
            "STRUCTURED_OUTPUT", "expected exactly one output_text payload"
        )
    return texts[0]


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ProviderExecutionError("PROVIDER_ENVELOPE", f"{key} is absent")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        raise ProviderExecutionError("RECEIPT_USAGE", f"{key} is invalid")
    return value


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ProviderExecution",
    "ProviderExecutionError",
    "ProviderRequest",
    "execute_single_provider_call",
]
