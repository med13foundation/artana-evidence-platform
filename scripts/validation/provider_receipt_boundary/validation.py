"""Compose strict identity, payload, envelope, input, schema, and usage checks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict

from scripts.validation.provider_receipt_boundary.canonical_payload import (
    StructuredPayloadError,
    canonical_sha256,
    extract_canonical_payload,
)
from scripts.validation.provider_receipt_boundary.contracts import (
    FieldDifference,
    ReceiptExpectations,
    ReceiptValidation,
    UsageAccounting,
)
from scripts.validation.provider_receipt_boundary.identity import (
    ReceiptIdentityError,
    extract_receipt_identity,
    require_same_identity,
)
from scripts.validation.provider_receipt_boundary.structural_diff import (
    RawDifference,
    structural_diff,
)

_OUTPUT_PATH_RE = re.compile(r"^\$\.output\[(?P<index>[0-9]+)]\.(?P<field>.+)$")


class ReceiptBoundaryError(ValueError):
    """A receipt cannot be qualified without weakening an immutable boundary."""

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


def validate_provider_receipt(
    *,
    creation: dict[str, object],
    retrieval: dict[str, object],
    input_items: tuple[dict[str, object], ...],
    expectations: ReceiptExpectations,
    latency_seconds: float,
) -> ReceiptValidation:
    """Validate immutable receipt evidence and explicitly classify every difference."""

    try:
        identity = require_same_identity(
            extract_receipt_identity(
                creation, expected_model=expectations.provider_model_id
            ),
            extract_receipt_identity(
                retrieval, expected_model=expectations.provider_model_id
            ),
        )
    except ReceiptIdentityError as exc:
        raise ReceiptBoundaryError("RECEIPT_IDENTITY", str(exc)) from exc
    _require_request_binding(creation, retrieval, expectations)
    _require_input(input_items, expectations.provider_input)
    _require_schema(creation, retrieval, expectations.provider_format)
    try:
        creation_payload = extract_canonical_payload(creation)
        retrieval_payload = extract_canonical_payload(retrieval)
    except StructuredPayloadError as exc:
        raise ReceiptBoundaryError("RECEIPT_PAYLOAD", str(exc)) from exc
    if creation_payload.sha256 != retrieval_payload.sha256:
        raise ReceiptBoundaryError(
            "RECEIPT_PAYLOAD",
            "canonical structured scientific payload changed on retrieval",
            diagnostics={
                "creation_payload_sha256": creation_payload.sha256,
                "retrieval_payload_sha256": retrieval_payload.sha256,
            },
        )
    usage = _usage_accounting(
        creation=creation,
        retrieval=retrieval,
        expectations=expectations,
        latency_seconds=latency_seconds,
    )
    differences = _classify_differences(
        creation=creation,
        retrieval=retrieval,
        same_payload=True,
        schema_verified=True,
    )
    unknown = tuple(item for item in differences if not item.allowlisted)
    if unknown:
        raise ReceiptBoundaryError(
            "RECEIPT_ENVELOPE",
            "unknown creation-versus-retrieval fields differ",
            diagnostics={
                "differences": [asdict(item) for item in unknown],
                "creation_envelope_sha256": canonical_sha256(creation),
                "retrieval_envelope_sha256": canonical_sha256(retrieval),
            },
        )
    return ReceiptValidation(
        identity=identity,
        scientific_payload_sha256=creation_payload.sha256,
        creation_envelope_sha256=canonical_sha256(creation),
        retrieval_envelope_sha256=canonical_sha256(retrieval),
        provider_input_sha256=hashlib.sha256(
            expectations.provider_input.encode()
        ).hexdigest(),
        provider_schema_sha256=canonical_sha256(expectations.provider_format),
        differences=differences,
        usage=usage,
    )


def _require_request_binding(
    creation: dict[str, object],
    retrieval: dict[str, object],
    expectations: ReceiptExpectations,
) -> None:
    for label, response in (("creation", creation), ("retrieval", retrieval)):
        if response.get("metadata") != expectations.metadata:
            raise ReceiptBoundaryError(
                "RECEIPT_METADATA", f"{label} custody metadata differs"
            )
        reasoning = response.get("reasoning")
        if (
            not isinstance(reasoning, dict)
            or reasoning.get("effort") != expectations.reasoning_effort
        ):
            raise ReceiptBoundaryError(
                "RECEIPT_REASONING", f"{label} reasoning effort differs"
            )


def _require_input(
    input_items: tuple[dict[str, object], ...], expected_input: str
) -> None:
    if len(input_items) != 1:
        raise ReceiptBoundaryError("RECEIPT_INPUT", "input topology is not singular")
    item = input_items[0]
    content = item.get("content")
    if item.get("type") != "message" or item.get("role") != "user":
        raise ReceiptBoundaryError("RECEIPT_INPUT", "input is not one user message")
    if not isinstance(content, list) or len(content) != 1:
        raise ReceiptBoundaryError("RECEIPT_INPUT", "input content is not singular")
    part = content[0]
    if not isinstance(part, dict) or part.get("type") != "input_text":
        raise ReceiptBoundaryError("RECEIPT_INPUT", "input part is not input_text")
    if part.get("text") != expected_input:
        raise ReceiptBoundaryError("RECEIPT_INPUT", "retrieved provider input differs")


def _require_schema(
    creation: dict[str, object],
    retrieval: dict[str, object],
    expected_format: dict[str, object],
) -> None:
    creation_format = _response_format(creation)
    if creation_format != expected_format:
        raise ReceiptBoundaryError(
            "RECEIPT_SCHEMA",
            "creation response schema differs",
            diagnostics=_schema_diagnostics(expected_format, creation_format),
        )
    retrieval_text = retrieval.get("text")
    if retrieval_text is None:
        return
    retrieval_format = _response_format(retrieval)
    if retrieval_format != expected_format:
        raise ReceiptBoundaryError(
            "RECEIPT_SCHEMA",
            "retrieval response schema differs",
            diagnostics=_schema_diagnostics(expected_format, retrieval_format),
        )


def _response_format(response: dict[str, object]) -> dict[str, object]:
    text = response.get("text")
    if not isinstance(text, dict):
        raise ReceiptBoundaryError("RECEIPT_SCHEMA", "response schema is absent")
    response_format = text.get("format")
    if not isinstance(response_format, dict):
        raise ReceiptBoundaryError("RECEIPT_SCHEMA", "response schema is absent")
    return response_format


def _schema_diagnostics(
    expected: dict[str, object], actual: dict[str, object]
) -> dict[str, object]:
    differences = tuple(
        item.redacted(allowlisted=False, rationale=None)
        for item in structural_diff(expected, actual)
    )
    return {
        "expected_schema_sha256": canonical_sha256(expected),
        "actual_schema_sha256": canonical_sha256(actual),
        "differences": [asdict(item) for item in differences],
    }


def _usage_accounting(
    *,
    creation: dict[str, object],
    retrieval: dict[str, object],
    expectations: ReceiptExpectations,
    latency_seconds: float,
) -> UsageAccounting:
    creation_usage = creation.get("usage")
    retrieval_usage = retrieval.get("usage")
    if not isinstance(creation_usage, dict) or not isinstance(retrieval_usage, dict):
        raise ReceiptBoundaryError(
            "RECEIPT_USAGE", "creation or retrieval usage is absent"
        )
    if creation_usage != retrieval_usage:
        raise ReceiptBoundaryError(
            "RECEIPT_USAGE", "creation and retrieval usage differ"
        )
    input_tokens = _nonnegative_int(retrieval_usage, "input_tokens")
    output_tokens = _nonnegative_int(retrieval_usage, "output_tokens")
    total_tokens = _nonnegative_int(retrieval_usage, "total_tokens")
    input_details = retrieval_usage.get("input_tokens_details")
    output_details = retrieval_usage.get("output_tokens_details")
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        raise ReceiptBoundaryError("RECEIPT_USAGE", "usage details are absent")
    cached_tokens = _nonnegative_int(input_details, "cached_tokens")
    reasoning_tokens = _nonnegative_int(output_details, "reasoning_tokens")
    if cached_tokens > input_tokens or total_tokens != input_tokens + output_tokens:
        raise ReceiptBoundaryError("RECEIPT_USAGE", "usage totals are inconsistent")
    cost_usd = (
        (input_tokens - cached_tokens) * expectations.pricing["input"]
        + cached_tokens * expectations.pricing["cached_input"]
        + output_tokens * expectations.pricing["output"]
    )
    if total_tokens > expectations.max_total_tokens:
        raise ReceiptBoundaryError("TOKEN_BUDGET", "total token ceiling exceeded")
    if latency_seconds > expectations.max_latency_seconds:
        raise ReceiptBoundaryError("LATENCY_BUDGET", "latency ceiling exceeded")
    if cost_usd > expectations.max_cost_usd:
        raise ReceiptBoundaryError("COST_BUDGET", "cost ceiling exceeded")
    return UsageAccounting(
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        latency_seconds=latency_seconds,
        cost_usd=cost_usd,
    )


def _classify_differences(
    *,
    creation: dict[str, object],
    retrieval: dict[str, object],
    same_payload: bool,
    schema_verified: bool,
) -> tuple[FieldDifference, ...]:
    classified: list[FieldDifference] = []
    for difference in structural_diff(creation, retrieval):
        rationale = _allowlist_rationale(
            difference,
            creation=creation,
            retrieval=retrieval,
            same_payload=same_payload,
            schema_verified=schema_verified,
        )
        classified.append(
            difference.redacted(
                allowlisted=rationale is not None,
                rationale=rationale,
            )
        )
    return tuple(classified)


def _allowlist_rationale(
    difference: RawDifference,
    *,
    creation: dict[str, object],
    retrieval: dict[str, object],
    same_payload: bool,
    schema_verified: bool,
) -> str | None:
    if (
        difference.path == "$.text"
        and schema_verified
        and retrieval.get("text") is None
    ):
        return (
            "Responses retrieval may omit optional text configuration; the request and "
            "creation-time strict schema were independently verified"
        )
    if difference.path == "$.completed_at" and _optional_completed_at(difference):
        return (
            "completed_at is optional transport timing metadata present only for a "
            "completed response"
        )
    match = _OUTPUT_PATH_RE.fullmatch(difference.path)
    if match is None:
        return None
    index = int(match.group("index"))
    field = match.group("field")
    item_type = _output_item_type(creation, retrieval, index)
    if field == "content[0].text" and item_type == "message" and same_payload:
        return (
            "JSON object key order and insignificant serialization differ while the "
            "canonical structured payload hash is exact"
        )
    if item_type == "reasoning" and field == "status" and _optional_status(difference):
        return (
            "reasoning item status is documented as optional and populated when an "
            "item is returned through the API"
        )
    if (
        item_type == "reasoning"
        and field == "content"
        and _none_empty_or_missing(difference)
    ):
        return "reasoning text content is optional and no content was disclosed"
    if (
        item_type == "reasoning"
        and field == "encrypted_content"
        and _none_or_missing(difference)
    ):
        return (
            "encrypted reasoning is optional include-only transport data and was not "
            "requested or disclosed"
        )
    if (
        item_type == "message"
        and field == "phase"
        and _optional_final_phase(difference)
    ):
        return "final-answer phase is optional message transport metadata"
    if (
        item_type == "message"
        and field
        in {
            "content[0].annotations",
            "content[0].logprobs",
        }
        and _none_empty_or_missing(difference)
    ):
        return "optional output_text metadata is empty in both representations"
    return None


def _output_item_type(
    creation: dict[str, object], retrieval: dict[str, object], index: int
) -> str | None:
    for response in (creation, retrieval):
        output = response.get("output")
        if isinstance(output, list) and index < len(output):
            item = output[index]
            if isinstance(item, dict):
                item_type = item.get("type")
                if isinstance(item_type, str):
                    return item_type
    return None


def _optional_completed_at(difference: RawDifference) -> bool:
    values = (difference.creation, difference.retrieval)
    present = [value for value in values if isinstance(value, int | float)]
    absent = sum(value is None for value in values)
    return len(present) == 1 and present[0] > 0 and absent == 1


def _optional_status(difference: RawDifference) -> bool:
    values = (difference.creation, difference.retrieval)
    return None in values and "completed" in values


def _optional_final_phase(difference: RawDifference) -> bool:
    values = (difference.creation, difference.retrieval)
    return None in values and "final_answer" in values


def _none_or_missing(difference: RawDifference) -> bool:
    return (difference.creation_missing or difference.creation is None) and (
        difference.retrieval_missing or difference.retrieval is None
    )


def _none_empty_or_missing(difference: RawDifference) -> bool:
    allowed: tuple[object, ...] = (None, [])
    return (difference.creation_missing or difference.creation in allowed) and (
        difference.retrieval_missing or difference.retrieval in allowed
    )


def _nonnegative_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        raise ReceiptBoundaryError("RECEIPT_USAGE", f"{key} is invalid")
    return value


__all__ = ["ReceiptBoundaryError", "validate_provider_receipt"]
