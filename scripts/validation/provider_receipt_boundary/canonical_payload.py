"""Canonicalize the sole structured output without trusting transport shape."""

from __future__ import annotations

import hashlib
import json

from scripts.validation.provider_receipt_boundary.contracts import CanonicalPayload


class StructuredPayloadError(ValueError):
    """The response does not contain one safe structured final answer."""


def extract_canonical_payload(response: dict[str, object]) -> CanonicalPayload:
    """Extract exactly one JSON object from one completed final assistant message."""

    message = _select_final_message(response)
    text = _extract_structured_text(message)
    return _parse_payload(text)


def discover_canonical_payload(response: dict[str, object]) -> CanonicalPayload:
    """Find one output_text payload before enforcing complete output topology."""

    output = response.get("output")
    if not isinstance(output, list) or not output:
        raise StructuredPayloadError("provider output array is missing or empty")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = part.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)
    if len(texts) != 1:
        raise StructuredPayloadError("expected exactly one discoverable output_text")
    return _parse_payload(texts[0])


def _select_final_message(response: dict[str, object]) -> dict[str, object]:
    output = response.get("output")
    if not isinstance(output, list) or not output:
        raise StructuredPayloadError("provider output array is missing or empty")
    messages: list[dict[str, object]] = []
    reasoning_items = 0
    for item in output:
        if not isinstance(item, dict):
            raise StructuredPayloadError("provider output item is not an object")
        item_type = item.get("type")
        if item_type == "reasoning":
            reasoning_items += 1
            if reasoning_items > 1:
                raise StructuredPayloadError("multiple reasoning items are unsupported")
            continue
        if item_type != "message":
            raise StructuredPayloadError(
                f"unsupported provider output item: {item_type}"
            )
        messages.append(item)
    if len(messages) != 1:
        raise StructuredPayloadError("expected exactly one output message")
    message = messages[0]
    if message.get("role") != "assistant" or message.get("status") != "completed":
        raise StructuredPayloadError(
            "output message is not a completed assistant message"
        )
    phase = message.get("phase")
    if phase not in (None, "final_answer"):
        raise StructuredPayloadError("commentary output cannot be scientific payload")
    return message


def _extract_structured_text(message: dict[str, object]) -> str:
    content = message.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise StructuredPayloadError("expected exactly one output content part")
    part = content[0]
    if not isinstance(part, dict) or part.get("type") != "output_text":
        raise StructuredPayloadError("output content is not structured output_text")
    annotations = part.get("annotations")
    if annotations not in (None, []):
        raise StructuredPayloadError(
            "structured output unexpectedly contains annotations"
        )
    logprobs = part.get("logprobs")
    if logprobs not in (None, []):
        raise StructuredPayloadError("structured output unexpectedly contains logprobs")
    text = part.get("text")
    if not isinstance(text, str) or not text:
        raise StructuredPayloadError("structured output text is missing")
    return text


def _parse_payload(text: str) -> CanonicalPayload:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StructuredPayloadError("structured output is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise StructuredPayloadError("structured output must be a JSON object")
    return CanonicalPayload(payload=payload, sha256=canonical_sha256(payload))


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "StructuredPayloadError",
    "canonical_sha256",
    "discover_canonical_payload",
    "extract_canonical_payload",
]
