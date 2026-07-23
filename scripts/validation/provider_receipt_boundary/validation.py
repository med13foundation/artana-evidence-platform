"""Compose strict identity, payload, envelope, input, schema, and usage checks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict

from scripts.validation.provider_receipt_boundary.canonical_payload import (
    StructuredPayloadError,
    canonical_sha256,
    discover_canonical_payload,
    extract_canonical_payload,
)
from scripts.validation.provider_receipt_boundary.contracts import (
    BudgetAccounting,
    CanonicalPayload,
    FieldDifference,
    ReceiptExpectations,
    ReceiptExpectationsLike,
    ReceiptIdentity,
    ReceiptValidation,
    TelemetryReceiptExpectationsV2,
    TelemetryReceiptValidationV2,
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
VALIDATION_ORDER = (
    "RESPONSE_STATUS",
    "RECEIPT_IDENTITY",
    "RECEIPT_MODEL",
    "RECEIPT_BINDING",
    "CREATION_DESCRIPTION",
    "CREATION_SCHEMA",
    "RECEIPT_INPUT",
    "RETRIEVAL_SCHEMA",
    "RECEIPT_PAYLOAD",
    "RECEIPT_OUTPUT_TOPOLOGY",
    "RECEIPT_USAGE",
    "RECEIPT_BUDGET",
    "RECEIPT_ENVELOPE",
)
TELEMETRY_VALIDATION_ORDER_V2 = tuple(
    stage for stage in VALIDATION_ORDER if stage != "RECEIPT_BUDGET"
)


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
    """Validate a receipt in the preregistered cheapest-first stage order."""

    _require_completed(creation, label="creation")
    _require_completed(retrieval, label="retrieval")
    _require_response_identity(creation, retrieval)
    _require_model_identity(creation, retrieval, expectations.provider_model_id)
    _require_request_binding(creation, retrieval, expectations)
    _require_creation_description(creation, expectations.provider_format)
    _require_creation_schema(creation, expectations.provider_format)
    _require_input(input_items, expectations.provider_input)
    _require_retrieval_schema(retrieval, expectations.provider_format)
    creation_payload, retrieval_payload = _require_payload_match(
        creation,
        retrieval,
    )
    identity = _require_output_topology(
        creation,
        retrieval,
        expected_model=expectations.provider_model_id,
        expected_payload_sha256=creation_payload.sha256,
    )
    usage = _require_usage(
        creation=creation,
        retrieval=retrieval,
        expectations=expectations,
        latency_seconds=latency_seconds,
    )
    budgets = _require_budgets(usage, expectations)
    differences = _require_known_envelope_differences(
        creation,
        retrieval,
    )
    return ReceiptValidation(
        identity=identity,
        scientific_payload_sha256=retrieval_payload.sha256,
        creation_envelope_sha256=canonical_sha256(creation),
        retrieval_envelope_sha256=canonical_sha256(retrieval),
        provider_input_sha256=hashlib.sha256(
            expectations.provider_input.encode()
        ).hexdigest(),
        provider_schema_sha256=canonical_sha256(expectations.provider_format),
        differences=differences,
        usage=usage,
        budgets=budgets,
    )


def validate_provider_receipt_telemetry_v2(
    *,
    creation: dict[str, object],
    retrieval: dict[str, object],
    input_items: tuple[dict[str, object], ...],
    expectations: TelemetryReceiptExpectationsV2,
    latency_seconds: float,
) -> TelemetryReceiptValidationV2:
    """Validate scientific custody while treating usage as record-only telemetry."""

    _require_completed(creation, label="creation")
    _require_completed(retrieval, label="retrieval")
    _require_response_identity(creation, retrieval)
    _require_model_identity(creation, retrieval, expectations.provider_model_id)
    _require_request_binding(creation, retrieval, expectations)
    _require_creation_description(creation, expectations.provider_format)
    _require_creation_schema(creation, expectations.provider_format)
    _require_input(input_items, expectations.provider_input)
    _require_retrieval_schema(retrieval, expectations.provider_format)
    creation_payload, retrieval_payload = _require_payload_match(
        creation,
        retrieval,
    )
    identity = _require_output_topology(
        creation,
        retrieval,
        expected_model=expectations.provider_model_id,
        expected_payload_sha256=creation_payload.sha256,
    )
    usage = _require_usage(
        creation=creation,
        retrieval=retrieval,
        expectations=expectations,
        latency_seconds=latency_seconds,
    )
    differences = _require_known_envelope_differences(
        creation,
        retrieval,
    )
    return TelemetryReceiptValidationV2(
        identity=identity,
        scientific_payload_sha256=retrieval_payload.sha256,
        creation_envelope_sha256=canonical_sha256(creation),
        retrieval_envelope_sha256=canonical_sha256(retrieval),
        provider_input_sha256=hashlib.sha256(
            expectations.provider_input.encode()
        ).hexdigest(),
        provider_schema_sha256=canonical_sha256(expectations.provider_format),
        differences=differences,
        usage=usage,
    )


def validate_creation_response(
    creation: dict[str, object],
    expectations: ReceiptExpectationsLike,
) -> None:
    """Stop before retrieval when a creation response fails stages 1 through 5."""

    _require_completed(creation, label="creation")
    _require_single_response_identity(creation, label="creation")
    _require_single_model(creation, expectations.provider_model_id, label="creation")
    _require_single_binding(creation, expectations, label="creation")
    _require_creation_description(creation, expectations.provider_format)
    _require_creation_schema(creation, expectations.provider_format)


def validate_retrieval_envelope(
    creation: dict[str, object],
    retrieval: dict[str, object],
    expectations: ReceiptExpectationsLike,
) -> None:
    """Stop before input-item retrieval when response envelope stages fail."""

    _require_completed(retrieval, label="retrieval")
    _require_response_identity(creation, retrieval)
    _require_model_identity(creation, retrieval, expectations.provider_model_id)
    _require_request_binding(creation, retrieval, expectations)


def _require_payload_match(
    creation: dict[str, object], retrieval: dict[str, object]
) -> tuple[CanonicalPayload, CanonicalPayload]:
    try:
        creation_payload = discover_canonical_payload(creation)
        retrieval_payload = discover_canonical_payload(retrieval)
    except StructuredPayloadError as exc:
        raise ReceiptBoundaryError(
            "RECEIPT_PAYLOAD",
            str(exc),
            diagnostics=_path_diagnostics(
                "$.output[*].content[*].text",
                creation.get("output"),
                retrieval.get("output"),
            ),
        ) from exc
    if creation_payload.sha256 != retrieval_payload.sha256:
        raise ReceiptBoundaryError(
            "RECEIPT_PAYLOAD",
            "canonical structured scientific payload changed on retrieval",
            diagnostics={
                "creation_payload_sha256": creation_payload.sha256,
                "retrieval_payload_sha256": retrieval_payload.sha256,
                "differences": [
                    _redacted_difference(
                        "$.output[*].content[*].text",
                        creation_payload.payload,
                        retrieval_payload.payload,
                    )
                ],
            },
        )
    return creation_payload, retrieval_payload


def _require_output_topology(
    creation: dict[str, object],
    retrieval: dict[str, object],
    *,
    expected_model: str,
    expected_payload_sha256: str,
) -> ReceiptIdentity:
    try:
        creation_payload = extract_canonical_payload(creation)
        retrieval_payload = extract_canonical_payload(retrieval)
        identity = require_same_identity(
            extract_receipt_identity(creation, expected_model=expected_model),
            extract_receipt_identity(retrieval, expected_model=expected_model),
        )
    except (ReceiptIdentityError, StructuredPayloadError) as exc:
        raise ReceiptBoundaryError(
            "RECEIPT_OUTPUT_TOPOLOGY",
            str(exc),
            diagnostics=_path_diagnostics(
                "$.output",
                creation.get("output"),
                retrieval.get("output"),
            ),
        ) from exc
    if (
        creation_payload.sha256 != expected_payload_sha256
        or retrieval_payload.sha256 != expected_payload_sha256
    ):
        raise ReceiptBoundaryError(
            "RECEIPT_OUTPUT_TOPOLOGY",
            "strict output topology changed the discovered payload",
        )
    return identity


def _require_known_envelope_differences(
    creation: dict[str, object], retrieval: dict[str, object]
) -> tuple[FieldDifference, ...]:
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
    return differences


def _require_request_binding(
    creation: dict[str, object],
    retrieval: dict[str, object],
    expectations: ReceiptExpectationsLike,
) -> None:
    for label, response in (("creation", creation), ("retrieval", retrieval)):
        _require_single_binding(response, expectations, label=label)


def _require_completed(response: dict[str, object], *, label: str) -> None:
    if response.get("status") != "completed":
        raise ReceiptBoundaryError(
            "RESPONSE_STATUS",
            f"{label} response is not completed",
            diagnostics=_path_diagnostics(
                "$.status",
                "completed",
                response.get("status"),
            ),
        )
    if response.get("error") is not None:
        raise ReceiptBoundaryError(
            "RESPONSE_STATUS",
            f"{label} response contains a provider error",
            diagnostics=_path_diagnostics("$.error", None, response.get("error")),
        )
    if response.get("incomplete_details") is not None:
        raise ReceiptBoundaryError(
            "RESPONSE_STATUS",
            f"{label} response contains incomplete details",
            diagnostics=_path_diagnostics(
                "$.incomplete_details",
                None,
                response.get("incomplete_details"),
            ),
        )


def _require_response_identity(
    creation: dict[str, object], retrieval: dict[str, object]
) -> None:
    creation_identity = _require_single_response_identity(
        creation,
        label="creation",
    )
    retrieval_identity = _require_single_response_identity(
        retrieval,
        label="retrieval",
    )
    if creation_identity != retrieval_identity:
        raise ReceiptBoundaryError(
            "RECEIPT_IDENTITY",
            "creation and retrieval response identity differs",
            diagnostics=_path_diagnostics(
                "$.id|$.object|$.created_at",
                creation_identity,
                retrieval_identity,
            ),
        )


def _require_single_response_identity(
    response: dict[str, object], *, label: str
) -> tuple[str, str, float]:
    response_id = response.get("id")
    object_type = response.get("object")
    created_at = response.get("created_at")
    if not isinstance(response_id, str) or not response_id:
        raise ReceiptBoundaryError(
            "RECEIPT_IDENTITY",
            f"{label} response ID is absent",
            diagnostics=_path_diagnostics("$.id", "NON_EMPTY_STRING", response_id),
        )
    if object_type != "response":
        raise ReceiptBoundaryError(
            "RECEIPT_IDENTITY",
            f"{label} object type is not response",
            diagnostics=_path_diagnostics("$.object", "response", object_type),
        )
    if not isinstance(created_at, int | float) or created_at <= 0:
        raise ReceiptBoundaryError(
            "RECEIPT_IDENTITY",
            f"{label} creation timestamp is invalid",
            diagnostics=_path_diagnostics(
                "$.created_at",
                "POSITIVE_NUMBER",
                created_at,
            ),
        )
    return response_id, object_type, float(created_at)


def _require_model_identity(
    creation: dict[str, object],
    retrieval: dict[str, object],
    expected_model: str,
) -> None:
    _require_single_model(creation, expected_model, label="creation")
    _require_single_model(retrieval, expected_model, label="retrieval")


def _require_single_model(
    response: dict[str, object], expected_model: str, *, label: str
) -> None:
    if response.get("model") != expected_model:
        raise ReceiptBoundaryError(
            "RECEIPT_MODEL",
            f"{label} model differs from requested model",
            diagnostics=_path_diagnostics(
                "$.model",
                expected_model,
                response.get("model"),
            ),
        )


def _require_single_binding(
    response: dict[str, object],
    expectations: ReceiptExpectationsLike,
    *,
    label: str,
) -> None:
    if response.get("metadata") != expectations.metadata:
        raise ReceiptBoundaryError(
            "RECEIPT_BINDING",
            f"{label} custody metadata differs",
            diagnostics=_path_diagnostics(
                "$.metadata",
                expectations.metadata,
                response.get("metadata"),
            ),
        )
    reasoning = response.get("reasoning")
    actual_effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
    if actual_effort != expectations.reasoning_effort:
        raise ReceiptBoundaryError(
            "RECEIPT_BINDING",
            f"{label} reasoning effort differs",
            diagnostics=_path_diagnostics(
                "$.reasoning.effort",
                expectations.reasoning_effort,
                actual_effort,
            ),
        )


def _require_input(
    input_items: tuple[dict[str, object], ...], expected_input: str
) -> None:
    if len(input_items) != 1:
        raise ReceiptBoundaryError(
            "RECEIPT_INPUT",
            "input topology is not singular",
            diagnostics=_path_diagnostics("$.input_items.length", 1, len(input_items)),
        )
    item = input_items[0]
    content = item.get("content")
    if item.get("type") != "message" or item.get("role") != "user":
        raise ReceiptBoundaryError(
            "RECEIPT_INPUT",
            "input is not one user message",
            diagnostics=_path_diagnostics(
                "$.input_items[0].type|$.input_items[0].role",
                ("message", "user"),
                (item.get("type"), item.get("role")),
            ),
        )
    if not isinstance(content, list) or len(content) != 1:
        raise ReceiptBoundaryError(
            "RECEIPT_INPUT",
            "input content is not singular",
            diagnostics=_path_diagnostics(
                "$.input_items[0].content",
                "ONE_ITEM_ARRAY",
                content,
            ),
        )
    part = content[0]
    if not isinstance(part, dict) or part.get("type") != "input_text":
        raise ReceiptBoundaryError(
            "RECEIPT_INPUT",
            "input part is not input_text",
            diagnostics=_path_diagnostics(
                "$.input_items[0].content[0].type",
                "input_text",
                part.get("type") if isinstance(part, dict) else part,
            ),
        )
    if part.get("text") != expected_input:
        raise ReceiptBoundaryError(
            "RECEIPT_INPUT",
            "retrieved provider input differs",
            diagnostics=_path_diagnostics(
                "$.input_items[0].content[0].text",
                expected_input,
                part.get("text"),
            ),
        )


def _require_creation_schema(
    creation: dict[str, object], expected_format: dict[str, object]
) -> None:
    creation_format = _response_format(creation, stage="CREATION_SCHEMA")
    if creation_format != expected_format:
        raise ReceiptBoundaryError(
            "CREATION_SCHEMA",
            "creation response schema differs",
            diagnostics=_schema_diagnostics(expected_format, creation_format),
        )


def _require_creation_description(
    creation: dict[str, object], expected_format: dict[str, object]
) -> None:
    creation_format = _response_format(creation, stage="CREATION_DESCRIPTION")
    _require_description(
        actual_format=creation_format,
        expected_format=expected_format,
        stage="CREATION_DESCRIPTION",
    )


def _require_retrieval_schema(
    retrieval: dict[str, object], expected_format: dict[str, object]
) -> None:
    retrieval_format = _response_format(retrieval, stage="RETRIEVAL_SCHEMA")
    _require_description(
        actual_format=retrieval_format,
        expected_format=expected_format,
        stage="RETRIEVAL_SCHEMA",
    )
    if retrieval_format != expected_format:
        raise ReceiptBoundaryError(
            "RETRIEVAL_SCHEMA",
            "retrieval response schema differs",
            diagnostics=_schema_diagnostics(expected_format, retrieval_format),
        )


def _require_description(
    *,
    actual_format: dict[str, object],
    expected_format: dict[str, object],
    stage: str,
) -> None:
    expected = expected_format.get("description")
    actual = actual_format.get("description")
    if not isinstance(expected, str) or not expected:
        raise ReceiptBoundaryError(
            stage,
            "frozen response-format description is absent",
            diagnostics=_path_diagnostics(
                "$.description", "NON_EMPTY_STRING", expected
            ),
        )
    if actual != expected:
        raise ReceiptBoundaryError(
            stage,
            "response-format description differs",
            diagnostics=_path_diagnostics("$.description", expected, actual),
        )


def _response_format(response: dict[str, object], *, stage: str) -> dict[str, object]:
    text = response.get("text")
    if not isinstance(text, dict):
        raise ReceiptBoundaryError(
            stage,
            "response schema is absent",
            diagnostics=_path_diagnostics("$.text", "OBJECT", text),
        )
    response_format = text.get("format")
    if not isinstance(response_format, dict):
        raise ReceiptBoundaryError(
            stage,
            "response schema is absent",
            diagnostics=_path_diagnostics(
                "$.text.format",
                "OBJECT",
                response_format,
            ),
        )
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


def _path_diagnostics(path: str, expected: object, actual: object) -> dict[str, object]:
    return {
        "differences": [_redacted_difference(path, expected, actual)],
        "expected_sha256": canonical_sha256(expected),
        "actual_sha256": canonical_sha256(actual),
    }


def _redacted_difference(
    path: str, expected: object, actual: object
) -> dict[str, object]:
    return {
        "path": path,
        "difference": "VALUE_CHANGED",
        "expected_sha256": canonical_sha256(expected),
        "actual_sha256": canonical_sha256(actual),
    }


def _require_usage(
    *,
    creation: dict[str, object],
    retrieval: dict[str, object],
    expectations: ReceiptExpectationsLike,
    latency_seconds: float,
) -> UsageAccounting:
    creation_usage = creation.get("usage")
    retrieval_usage = retrieval.get("usage")
    if not isinstance(creation_usage, dict) or not isinstance(retrieval_usage, dict):
        raise ReceiptBoundaryError(
            "RECEIPT_USAGE",
            "creation or retrieval usage is absent",
            diagnostics=_path_diagnostics(
                "$.usage",
                creation_usage,
                retrieval_usage,
            ),
        )
    if creation_usage != retrieval_usage:
        raise ReceiptBoundaryError(
            "RECEIPT_USAGE",
            "creation and retrieval usage differ",
            diagnostics=_path_diagnostics(
                "$.usage",
                creation_usage,
                retrieval_usage,
            ),
        )
    input_tokens = _nonnegative_int(retrieval_usage, "input_tokens")
    output_tokens = _nonnegative_int(retrieval_usage, "output_tokens")
    total_tokens = _nonnegative_int(retrieval_usage, "total_tokens")
    input_details = retrieval_usage.get("input_tokens_details")
    output_details = retrieval_usage.get("output_tokens_details")
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        raise ReceiptBoundaryError(
            "RECEIPT_USAGE",
            "usage details are absent",
            diagnostics=_path_diagnostics(
                "$.usage.*_tokens_details",
                "OBJECTS",
                (input_details, output_details),
            ),
        )
    cached_tokens = _nonnegative_int(input_details, "cached_tokens")
    reasoning_tokens = _nonnegative_int(output_details, "reasoning_tokens")
    if cached_tokens > input_tokens or total_tokens != input_tokens + output_tokens:
        raise ReceiptBoundaryError(
            "RECEIPT_USAGE",
            "usage totals are inconsistent",
            diagnostics=_path_diagnostics(
                "$.usage",
                "CONSISTENT_TOTALS",
                retrieval_usage,
            ),
        )
    cost_usd = (
        (input_tokens - cached_tokens) * expectations.pricing["input"]
        + cached_tokens * expectations.pricing["cached_input"]
        + output_tokens * expectations.pricing["output"]
    )
    return UsageAccounting(
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
        latency_seconds=latency_seconds,
        cost_usd=cost_usd,
    )


def _require_budgets(
    usage: UsageAccounting, expectations: ReceiptExpectations
) -> BudgetAccounting:
    requested = (
        expectations.max_output_tokens,
        expectations.max_total_tokens,
        expectations.max_latency_seconds,
        expectations.max_cost_usd,
    )
    if any(not isinstance(value, int | float) or value <= 0 for value in requested):
        raise ReceiptBoundaryError(
            "RECEIPT_BUDGET",
            "requested budget provenance is absent or invalid",
            diagnostics={"receipt_status": "REJECTED_BUDGET_PROVENANCE"},
        )
    accounting = BudgetAccounting(
        requested_max_output_tokens=expectations.max_output_tokens,
        requested_max_total_tokens=expectations.max_total_tokens,
        requested_max_latency_seconds=expectations.max_latency_seconds,
        requested_max_cost_usd=expectations.max_cost_usd,
        observed_output_tokens=usage.output_tokens,
        observed_total_tokens=usage.total_tokens,
        observed_latency_seconds=usage.latency_seconds,
        observed_cost_usd=usage.cost_usd,
        output_tokens=_budget_status(
            usage.output_tokens, expectations.max_output_tokens
        ),
        total_tokens=_budget_status(usage.total_tokens, expectations.max_total_tokens),
        latency=_budget_status(usage.latency_seconds, expectations.max_latency_seconds),
        cost=_budget_status(usage.cost_usd, expectations.max_cost_usd),
    )
    checks = (
        (
            "$.usage.output_tokens",
            expectations.max_output_tokens,
            usage.output_tokens,
            "output token ceiling exceeded",
        ),
        (
            "$.usage.total_tokens",
            expectations.max_total_tokens,
            usage.total_tokens,
            "total token ceiling exceeded",
        ),
        (
            "$.latency_seconds",
            expectations.max_latency_seconds,
            usage.latency_seconds,
            "latency ceiling exceeded",
        ),
        (
            "$.cost_usd",
            expectations.max_cost_usd,
            usage.cost_usd,
            "cost ceiling exceeded",
        ),
    )
    for path, maximum, actual, message in checks:
        if actual > maximum:
            raise ReceiptBoundaryError(
                "RECEIPT_BUDGET",
                message,
                diagnostics={
                    **_path_diagnostics(path, maximum, actual),
                    "observed_usage": asdict(usage),
                    "budget_accounting": asdict(accounting),
                    "receipt_status": "REJECTED_BUDGET",
                },
            )
    return accounting


def _budget_status(actual: float, maximum: float) -> str:
    return "PASS" if actual <= maximum else "FAIL"


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
        raise ReceiptBoundaryError(
            "RECEIPT_USAGE",
            f"{key} is invalid",
            diagnostics=_path_diagnostics(
                f"$.usage.{key}",
                "NON_NEGATIVE_INTEGER",
                value,
            ),
        )
    return value


__all__ = [
    "VALIDATION_ORDER",
    "ReceiptBoundaryError",
    "validate_creation_response",
    "validate_provider_receipt",
    "validate_retrieval_envelope",
]
