"""Live provider receipt verification for TG-03 model executions."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final, Literal, Protocol, cast

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    parse_provider_invocation_binding,
)

JsonObject = dict[str, object]

REPORT_MODEL_ID: Final = "openai:gpt-5.6-luna"
EXECUTION_MODEL_ID: Final = "openai/gpt-5.6-luna"
PROVIDER_MODEL_ID: Final = "gpt-5.6-luna"
_PROVIDER_MODEL_BY_ID: Final = {
    REPORT_MODEL_ID: PROVIDER_MODEL_ID,
    EXECUTION_MODEL_ID: PROVIDER_MODEL_ID,
    PROVIDER_MODEL_ID: PROVIDER_MODEL_ID,
    "openai:gpt-5.6-sol": "gpt-5.6-sol",
    "openai/gpt-5.6-sol": "gpt-5.6-sol",
    "gpt-5.6-sol": "gpt-5.6-sol",
}

ProviderReceiptStatus = Literal[
    "verified_live",
    "not_verified",
    "unavailable",
    "mismatched",
    "duplicate",
]
ProviderReceiptFailure = Literal[
    "none",
    "verifier_absent",
    "retrieve_failed",
    "response_id_mismatch",
    "model_mismatch",
    "response_status_mismatch",
    "response_error_present",
    "incomplete_details_present",
    "instructions_present",
    "previous_response_id_present",
    "unsupported_context_present",
    "invocation_topology_mismatch",
    "source_binding_mismatch",
    "input_binding_mismatch",
    "evidence_unit_binding_mismatch",
    "output_missing",
    "output_message_role_mismatch",
    "output_message_status_mismatch",
    "output_hash_mismatch",
    "payload_parse_failed",
    "payload_expectation_missing",
    "payload_hash_mismatch",
    "output_schema_missing",
    "output_schema_mismatch",
    "input_retrieve_failed",
    "input_topology_mismatch",
    "prompt_hash_mismatch",
    "duplicate_response_id",
]
OutputSchemaVerificationSource = Literal[
    "unverified",
    "not_required",
    "provider_response",
    "provider_input_binding",
    "provider_response_and_input_binding",
]
ProviderOutputVerificationSource = Literal[
    "unverified",
    "exact_provider_output",
    "structured_payload_with_verified_envelope",
]


def canonical_provider_model_id(model_id: str) -> str:
    """Map registered benchmark model identities to provider identities."""

    try:
        return _PROVIDER_MODEL_BY_ID[model_id]
    except KeyError as exc:
        raise ValueError(f"unrecognized benchmark model identity: {model_id}") from exc


def canonical_provider_output_sha256(output: object) -> str:
    """Hash the canonical JSON representation of a Responses output array."""

    encoded = json.dumps(
        output,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderReceiptExpectation:
    """Provider evidence required to bind one response to one scored attempt."""

    response_id: str
    expected_case_id: str
    expected_model_id: str
    expected_output_sha256: str
    expected_payload_sha256: str | None
    expected_prompt_sha256: str
    expected_invocation_id: str
    expected_kernel_run_id: str
    expected_source_sha256: str
    expected_input_sha256: str
    expected_evidence_unit_sha256: str
    expected_output_schema_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderReceiptEvidence:
    """Categorical result of retrieving and validating one provider response."""

    response_id: str
    expected_case_id: str
    status: ProviderReceiptStatus
    failure: ProviderReceiptFailure
    expected_model_id: str
    retrieved_model_id: str | None
    expected_output_sha256: str
    retrieved_output_sha256: str | None
    provider_output_hash_matched: bool
    provider_output_verification_source: ProviderOutputVerificationSource
    expected_payload_sha256: str | None
    retrieved_payload_sha256: str | None
    expected_prompt_sha256: str
    retrieved_prompt_sha256: str | None
    expected_invocation_id: str
    retrieved_invocation_id: str | None
    expected_kernel_run_id: str
    retrieved_kernel_run_id: str | None
    expected_source_sha256: str
    retrieved_source_sha256: str | None
    expected_input_sha256: str
    retrieved_input_sha256: str | None
    expected_evidence_unit_sha256: str
    retrieved_evidence_unit_sha256: str | None
    expected_output_schema_sha256: str | None
    retrieved_output_schema_sha256: str | None
    output_schema_verification_source: OutputSchemaVerificationSource
    provider_response_schema_supported: bool
    provider_status: str | None
    response_completed_verified: bool
    incomplete_details_absent: bool
    standalone_context_verified: bool
    input_topology_verified: bool
    invocation_topology_supported: bool
    invocation_topology_verified: bool
    error_type: str | None = None

    def as_json(self) -> JsonObject:
        return {
            "response_id": self.response_id,
            "expected_case_id": self.expected_case_id,
            "status": self.status,
            "failure": self.failure,
            "expected_model_id": self.expected_model_id,
            "retrieved_model_id": self.retrieved_model_id,
            "expected_output_sha256": self.expected_output_sha256,
            "retrieved_output_sha256": self.retrieved_output_sha256,
            "provider_output_hash_matched": self.provider_output_hash_matched,
            "provider_output_verification_source": (
                self.provider_output_verification_source
            ),
            "expected_payload_sha256": self.expected_payload_sha256,
            "retrieved_payload_sha256": self.retrieved_payload_sha256,
            "expected_prompt_sha256": self.expected_prompt_sha256,
            "retrieved_prompt_sha256": self.retrieved_prompt_sha256,
            "expected_invocation_id": self.expected_invocation_id,
            "retrieved_invocation_id": self.retrieved_invocation_id,
            "expected_kernel_run_id": self.expected_kernel_run_id,
            "retrieved_kernel_run_id": self.retrieved_kernel_run_id,
            "expected_source_sha256": self.expected_source_sha256,
            "retrieved_source_sha256": self.retrieved_source_sha256,
            "expected_input_sha256": self.expected_input_sha256,
            "retrieved_input_sha256": self.retrieved_input_sha256,
            "expected_evidence_unit_sha256": self.expected_evidence_unit_sha256,
            "retrieved_evidence_unit_sha256": self.retrieved_evidence_unit_sha256,
            "expected_output_schema_sha256": self.expected_output_schema_sha256,
            "retrieved_output_schema_sha256": self.retrieved_output_schema_sha256,
            "output_schema_verification_source": (
                self.output_schema_verification_source
            ),
            "provider_response_schema_supported": (
                self.provider_response_schema_supported
            ),
            "provider_status": self.provider_status,
            "response_completed_verified": self.response_completed_verified,
            "incomplete_details_absent": self.incomplete_details_absent,
            "standalone_context_verified": self.standalone_context_verified,
            "input_topology_verified": self.input_topology_verified,
            "invocation_topology_supported": self.invocation_topology_supported,
            "invocation_topology_verified": self.invocation_topology_verified,
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class ProviderReceiptVerification:
    """Aggregate provider-receipt result used by the deterministic merge gate."""

    status: ProviderReceiptStatus
    expected_count: int
    verified_count: int
    receipts: tuple[ProviderReceiptEvidence, ...]

    @property
    def gate_passed(self) -> bool:
        return (
            self.status == "verified_live"
            and self.expected_count > 0
            and self.verified_count == self.expected_count
        )

    def as_json(self) -> JsonObject:
        return {
            "status": self.status,
            "expected_count": self.expected_count,
            "verified_count": self.verified_count,
            "receipts": [receipt.as_json() for receipt in self.receipts],
        }


class ProviderReceiptVerifier(Protocol):
    """Deterministic verifier for one externally retrievable provider response."""

    def verify(
        self,
        expectation: ProviderReceiptExpectation,
    ) -> ProviderReceiptEvidence: ...


class _ProviderResponse(Protocol):
    def model_dump(self, *, mode: str) -> dict[str, object]: ...


ProviderResponseRetriever = Callable[[str], _ProviderResponse]
ProviderInputItemsRetriever = Callable[[str], Sequence[Mapping[str, object]]]


@dataclass(frozen=True, slots=True)
class _RetrievedReceiptFields:
    model_id: str | None = None
    output_sha256: str | None = None
    provider_output_hash_matched: bool = False
    provider_output_verification_source: ProviderOutputVerificationSource = (
        "unverified"
    )
    payload_sha256: str | None = None
    prompt_sha256: str | None = None
    invocation_id: str | None = None
    kernel_run_id: str | None = None
    source_sha256: str | None = None
    input_sha256: str | None = None
    evidence_unit_sha256: str | None = None
    output_schema_sha256: str | None = None
    output_schema_verification_source: OutputSchemaVerificationSource = "unverified"
    provider_response_schema_supported: bool = False
    provider_status: str | None = None
    response_completed_verified: bool = False
    incomplete_details_absent: bool = False
    standalone_context_verified: bool = False
    input_topology_verified: bool = False
    invocation_topology_supported: bool = False
    invocation_topology_verified: bool = False


class OpenAIProviderReceiptVerifier:
    """Verify receipts by retrieving stored responses from OpenAI."""

    def __init__(
        self,
        retrieve_response: ProviderResponseRetriever,
        retrieve_input_items: ProviderInputItemsRetriever | None = None,
    ) -> None:
        self._retrieve_response = retrieve_response
        self._retrieve_input_items = retrieve_input_items

    @classmethod
    def from_environment(cls) -> OpenAIProviderReceiptVerifier | None:
        """Build a verifier from configured OpenAI credentials, when available."""

        api_key = (
            os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY") or ""
        ).strip()
        if not api_key:
            return None

        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        def _retrieve(response_id: str) -> _ProviderResponse:
            return cast(
                "_ProviderResponse",
                client.responses.retrieve(response_id),
            )

        def _retrieve_input_items(
            response_id: str,
        ) -> tuple[Mapping[str, object], ...]:
            page = client.responses.input_items.list(
                response_id,
                limit=100,
                order="asc",
            )
            return tuple(item.model_dump(mode="json") for item in page)

        return cls(_retrieve, _retrieve_input_items)

    def verify(
        self,
        expectation: ProviderReceiptExpectation,
    ) -> ProviderReceiptEvidence:
        try:
            response = self._retrieve_response(expectation.response_id)
            payload = response.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 - categorical fail-closed evidence.
            return _receipt_evidence(
                expectation,
                status="unavailable",
                failure="retrieve_failed",
                error_type=type(exc).__name__,
            )
        output_result = _verify_response_output(expectation, payload)
        if isinstance(output_result, ProviderReceiptEvidence):
            return output_result
        return _verify_provider_input(
            expectation,
            output_result,
            self._retrieve_input_items,
        )


def _verify_response_output(
    expectation: ProviderReceiptExpectation,
    response: Mapping[str, object],
) -> _RetrievedReceiptFields | ProviderReceiptEvidence:
    envelope_result = _verify_response_envelope(expectation, response)
    if isinstance(envelope_result, ProviderReceiptEvidence):
        return envelope_result
    fields = envelope_result
    schema_result = _verify_response_schema(expectation, response, fields)
    if isinstance(schema_result, ProviderReceiptEvidence):
        return schema_result
    fields = schema_result
    output = response.get("output")
    if not isinstance(output, list):
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="output_missing",
            retrieved=fields,
        )
    message_failure = _output_message_failure(output)
    if message_failure is not None:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure=message_failure,
            retrieved=fields,
        )
    output_hash = canonical_provider_output_sha256(output)
    output_hash_matched = output_hash == expectation.expected_output_sha256
    fields = replace(
        fields,
        output_sha256=output_hash,
        provider_output_hash_matched=output_hash_matched,
    )
    if expectation.expected_payload_sha256 is None:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="payload_expectation_missing",
            retrieved=fields,
        )
    try:
        structured_payload = _structured_payload_from_output(output)
    except (TypeError, ValueError):
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="payload_parse_failed",
            retrieved=fields,
        )
    payload_hash = canonical_provider_output_sha256(structured_payload)
    fields = replace(fields, payload_sha256=payload_hash)
    if payload_hash != expectation.expected_payload_sha256:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure=(
                "payload_hash_mismatch"
                if output_hash_matched
                else "output_hash_mismatch"
            ),
            retrieved=fields,
        )
    return replace(
        fields,
        provider_output_verification_source=(
            "exact_provider_output"
            if output_hash_matched
            else "structured_payload_with_verified_envelope"
        ),
    )


def _verify_response_schema(
    expectation: ProviderReceiptExpectation,
    response: Mapping[str, object],
    retrieved: _RetrievedReceiptFields,
) -> _RetrievedReceiptFields | ProviderReceiptEvidence:
    expected = expectation.expected_output_schema_sha256
    if expected is None:
        return replace(
            retrieved,
            output_schema_verification_source="not_required",
        )
    text = response.get("text")
    if not isinstance(text, Mapping):
        return retrieved
    output_format = text.get("format")
    if not isinstance(output_format, Mapping):
        return retrieved
    schema = output_format.get("schema")
    if schema is None:
        return retrieved
    if not isinstance(schema, Mapping):
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="output_schema_mismatch",
            retrieved=retrieved,
        )
    schema_sha256 = canonical_provider_output_sha256(schema)
    fields = replace(
        retrieved,
        output_schema_sha256=schema_sha256,
        output_schema_verification_source="provider_response",
        provider_response_schema_supported=True,
    )
    if schema_sha256 != expected:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="output_schema_mismatch",
            retrieved=fields,
        )
    return fields


def _verify_response_envelope(
    expectation: ProviderReceiptExpectation,
    response: Mapping[str, object],
) -> _RetrievedReceiptFields | ProviderReceiptEvidence:
    if response.get("id") != expectation.response_id:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="response_id_mismatch",
        )
    retrieved_model = response.get("model")
    if not isinstance(retrieved_model, str):
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="model_mismatch",
        )
    provider_status = response.get("status")
    fields = _RetrievedReceiptFields(
        model_id=retrieved_model,
        provider_status=provider_status if isinstance(provider_status, str) else None,
    )
    try:
        provider_model = canonical_provider_model_id(retrieved_model)
    except ValueError:
        provider_model = None
    if provider_model != expectation.expected_model_id:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="model_mismatch",
            retrieved=fields,
        )
    if response.get("incomplete_details") is not None:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="incomplete_details_present",
            retrieved=fields,
        )
    fields = replace(fields, incomplete_details_absent=True)
    if provider_status != "completed":
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="response_status_mismatch",
            retrieved=fields,
        )
    fields = replace(fields, response_completed_verified=True)
    context_failure = _standalone_context_failure(response)
    if context_failure is not None:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure=context_failure,
            retrieved=fields,
        )
    fields = replace(fields, standalone_context_verified=True)
    topology_result = _verify_provider_invocation_topology(
        expectation,
        response,
        fields,
    )
    if isinstance(topology_result, ProviderReceiptEvidence):
        return topology_result
    return topology_result


def _standalone_context_failure(
    response: Mapping[str, object],
) -> ProviderReceiptFailure | None:
    if response.get("error") is not None:
        return "response_error_present"
    if response.get("instructions") is not None:
        return "instructions_present"
    if response.get("previous_response_id") is not None:
        return "previous_response_id_present"
    if response.get("conversation") is not None or response.get("prompt") is not None:
        return "unsupported_context_present"
    tools = response.get("tools")
    if not isinstance(tools, list) or tools:
        return "unsupported_context_present"
    context_management = response.get("context_management")
    if context_management is not None and context_management != []:
        return "unsupported_context_present"
    return None


def _verify_provider_invocation_topology(
    expectation: ProviderReceiptExpectation,
    response: Mapping[str, object],
    retrieved: _RetrievedReceiptFields,
) -> _RetrievedReceiptFields | ProviderReceiptEvidence:
    metadata = response.get("metadata")
    if metadata is None or metadata == {}:
        return retrieved
    if not isinstance(metadata, Mapping):
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="invocation_topology_mismatch",
            retrieved=retrieved,
        )
    invocation_id = metadata.get("artana_invocation_id")
    kernel_run_id = metadata.get("artana_kernel_run_id")
    if invocation_id is None and kernel_run_id is None:
        return retrieved
    bound_fields = replace(
        retrieved,
        invocation_id=invocation_id if isinstance(invocation_id, str) else None,
        kernel_run_id=kernel_run_id if isinstance(kernel_run_id, str) else None,
        invocation_topology_supported=True,
    )
    if (
        invocation_id != expectation.expected_invocation_id
        or kernel_run_id != expectation.expected_kernel_run_id
    ):
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="invocation_topology_mismatch",
            retrieved=bound_fields,
        )
    return replace(bound_fields, invocation_topology_verified=True)


def _verify_provider_input(
    expectation: ProviderReceiptExpectation,
    retrieved: _RetrievedReceiptFields,
    retrieve_input_items: ProviderInputItemsRetriever | None,
) -> ProviderReceiptEvidence:
    if retrieve_input_items is None:
        return _receipt_evidence(
            expectation,
            status="unavailable",
            failure="input_retrieve_failed",
            retrieved=retrieved,
            error_type="ProviderInputRetrieverUnavailable",
        )
    try:
        input_items = retrieve_input_items(expectation.response_id)
    except Exception as exc:  # noqa: BLE001 - categorical fail-closed evidence.
        return _receipt_evidence(
            expectation,
            status="unavailable",
            failure="input_retrieve_failed",
            retrieved=retrieved,
            error_type=type(exc).__name__,
        )
    try:
        retrieved_prompt = _single_user_prompt(input_items)
    except (TypeError, ValueError):
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="input_topology_mismatch",
            retrieved=retrieved,
        )
    try:
        invocation_binding = parse_provider_invocation_binding(retrieved_prompt)
    except ValueError:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="invocation_topology_mismatch",
            retrieved=retrieved,
        )
    schema_result = _bind_retrieved_output_schema(
        expectation,
        retrieved=retrieved,
        input_schema_sha256=invocation_binding.output_schema_sha256,
    )
    if isinstance(schema_result, ProviderReceiptEvidence):
        return schema_result
    retrieved = schema_result
    prompt_hash = _sha256_text(retrieved_prompt)
    bound_fields = replace(
        retrieved,
        prompt_sha256=prompt_hash,
        invocation_id=invocation_binding.invocation_id,
        kernel_run_id=invocation_binding.kernel_run_id,
        source_sha256=invocation_binding.source_sha256,
        input_sha256=invocation_binding.input_sha256,
        evidence_unit_sha256=invocation_binding.evidence_unit_sha256,
        input_topology_verified=True,
        invocation_topology_supported=True,
    )
    if (
        invocation_binding.invocation_id != expectation.expected_invocation_id
        or invocation_binding.kernel_run_id != expectation.expected_kernel_run_id
    ):
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="invocation_topology_mismatch",
            retrieved=bound_fields,
        )
    bound_fields = replace(bound_fields, invocation_topology_verified=True)
    if invocation_binding.source_sha256 != expectation.expected_source_sha256:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="source_binding_mismatch",
            retrieved=bound_fields,
        )
    if invocation_binding.input_sha256 != expectation.expected_input_sha256:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="input_binding_mismatch",
            retrieved=bound_fields,
        )
    if (
        invocation_binding.evidence_unit_sha256
        != expectation.expected_evidence_unit_sha256
    ):
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="evidence_unit_binding_mismatch",
            retrieved=bound_fields,
        )
    if prompt_hash != expectation.expected_prompt_sha256:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="prompt_hash_mismatch",
            retrieved=bound_fields,
        )
    return _receipt_evidence(
        expectation,
        status="verified_live",
        failure="none",
        retrieved=bound_fields,
    )


def _bind_retrieved_output_schema(
    expectation: ProviderReceiptExpectation,
    *,
    retrieved: _RetrievedReceiptFields,
    input_schema_sha256: str,
) -> _RetrievedReceiptFields | ProviderReceiptEvidence:
    """Bind schema custody to provider response metadata or retrieved input."""

    expected = expectation.expected_output_schema_sha256
    if expected is not None and input_schema_sha256 != expected:
        return _receipt_evidence(
            expectation,
            status="mismatched",
            failure="output_schema_mismatch",
            retrieved=retrieved,
        )
    if expected is None:
        return replace(
            retrieved,
            output_schema_verification_source="not_required",
        )
    source: OutputSchemaVerificationSource = (
        "provider_response_and_input_binding"
        if retrieved.provider_response_schema_supported
        else "provider_input_binding"
    )
    return replace(
        retrieved,
        output_schema_sha256=input_schema_sha256,
        output_schema_verification_source=source,
    )


def verify_provider_receipts(
    expectations: Sequence[ProviderReceiptExpectation],
    verifier: ProviderReceiptVerifier | None,
) -> ProviderReceiptVerification:
    """Verify all receipts independently and return one fail-closed result."""

    duplicate_ids = _duplicate_response_ids(expectations)
    if duplicate_ids:
        receipts = tuple(
            _receipt_evidence(
                expectation,
                status="duplicate",
                failure="duplicate_response_id",
            )
            for expectation in expectations
        )
        return ProviderReceiptVerification(
            status="duplicate",
            expected_count=len(expectations),
            verified_count=0,
            receipts=receipts,
        )
    if verifier is None:
        receipts = tuple(
            _receipt_evidence(
                expectation,
                status="not_verified",
                failure="verifier_absent",
            )
            for expectation in expectations
        )
        return ProviderReceiptVerification(
            status="not_verified",
            expected_count=len(expectations),
            verified_count=0,
            receipts=receipts,
        )

    receipts = tuple(verifier.verify(expectation) for expectation in expectations)
    verified_count = sum(receipt.status == "verified_live" for receipt in receipts)
    status = _aggregate_receipt_status(receipts)
    return ProviderReceiptVerification(
        status=status,
        expected_count=len(expectations),
        verified_count=verified_count,
        receipts=receipts,
    )


def _receipt_evidence(
    expectation: ProviderReceiptExpectation,
    *,
    status: ProviderReceiptStatus,
    failure: ProviderReceiptFailure,
    retrieved: _RetrievedReceiptFields | None = None,
    error_type: str | None = None,
) -> ProviderReceiptEvidence:
    fields = retrieved or _RetrievedReceiptFields()
    return ProviderReceiptEvidence(
        response_id=expectation.response_id,
        expected_case_id=expectation.expected_case_id,
        status=status,
        failure=failure,
        expected_model_id=expectation.expected_model_id,
        retrieved_model_id=fields.model_id,
        expected_output_sha256=expectation.expected_output_sha256,
        retrieved_output_sha256=fields.output_sha256,
        provider_output_hash_matched=fields.provider_output_hash_matched,
        provider_output_verification_source=(
            fields.provider_output_verification_source
        ),
        expected_payload_sha256=expectation.expected_payload_sha256,
        retrieved_payload_sha256=fields.payload_sha256,
        expected_prompt_sha256=expectation.expected_prompt_sha256,
        retrieved_prompt_sha256=fields.prompt_sha256,
        expected_invocation_id=expectation.expected_invocation_id,
        retrieved_invocation_id=fields.invocation_id,
        expected_kernel_run_id=expectation.expected_kernel_run_id,
        retrieved_kernel_run_id=fields.kernel_run_id,
        expected_source_sha256=expectation.expected_source_sha256,
        retrieved_source_sha256=fields.source_sha256,
        expected_input_sha256=expectation.expected_input_sha256,
        retrieved_input_sha256=fields.input_sha256,
        expected_evidence_unit_sha256=(expectation.expected_evidence_unit_sha256),
        retrieved_evidence_unit_sha256=fields.evidence_unit_sha256,
        expected_output_schema_sha256=expectation.expected_output_schema_sha256,
        retrieved_output_schema_sha256=fields.output_schema_sha256,
        output_schema_verification_source=(
            fields.output_schema_verification_source
        ),
        provider_response_schema_supported=(
            fields.provider_response_schema_supported
        ),
        provider_status=fields.provider_status,
        response_completed_verified=fields.response_completed_verified,
        incomplete_details_absent=fields.incomplete_details_absent,
        standalone_context_verified=fields.standalone_context_verified,
        input_topology_verified=fields.input_topology_verified,
        invocation_topology_supported=fields.invocation_topology_supported,
        invocation_topology_verified=fields.invocation_topology_verified,
        error_type=error_type,
    )


def _structured_payload_from_output(output: Sequence[object]) -> JsonObject:
    output_texts: list[str] = []
    message_count = 0
    for raw_item in output:
        if not isinstance(raw_item, Mapping):
            raise TypeError("provider output items must be objects")
        item_type = raw_item.get("type")
        if item_type == "reasoning":
            _validate_inert_reasoning_item(raw_item)
            continue
        if item_type != "message":
            raise ValueError("provider output contains an unsupported item type")
        message_count += 1
        _validate_output_message_item(raw_item)
        content = raw_item.get("content")
        if not isinstance(content, Sequence) or isinstance(content, str | bytes):
            raise TypeError("provider message content must be a list")
        for raw_part in content:
            if not isinstance(raw_part, Mapping):
                raise TypeError("provider message content parts must be objects")
            if raw_part.get("type") != "output_text":
                raise ValueError("provider message contains non-output text content")
            _validate_output_text_part(raw_part)
            output_texts.append(_output_text(raw_part))
    if message_count != 1 or len(output_texts) != 1:
        raise ValueError(
            "provider response must contain one message and one structured output text",
        )
    parsed = json.loads(output_texts[0])
    if not isinstance(parsed, dict):
        raise TypeError("provider structured output must parse to an object")
    return cast("JsonObject", parsed)


def _validate_inert_reasoning_item(item: Mapping[str, object]) -> None:
    """Accept only the provider reasoning envelope omitted by the adapter."""

    _reject_unknown_keys(
        item,
        allowed={
            "content",
            "encrypted_content",
            "id",
            "status",
            "summary",
            "type",
        },
        label="provider reasoning item",
    )
    if not isinstance(item.get("id"), str):
        raise TypeError("provider reasoning item ID must be text")
    if item.get("status") not in (None, "completed"):
        raise ValueError("provider reasoning item status is unsupported")
    summary = item.get("summary")
    if summary != []:
        raise ValueError("provider reasoning summary must be empty")
    content = item.get("content")
    if content not in (None, []):
        raise ValueError("provider reasoning content must be opaque")
    encrypted_content = item.get("encrypted_content")
    if encrypted_content is not None and not isinstance(encrypted_content, str):
        raise TypeError("provider encrypted reasoning must be text or null")


def _validate_output_message_item(item: Mapping[str, object]) -> None:
    _reject_unknown_keys(
        item,
        allowed={"content", "id", "phase", "role", "status", "type"},
        label="provider output message",
    )
    if not isinstance(item.get("id"), str):
        raise TypeError("provider output message ID must be text")
    if item.get("phase") not in (None, "final_answer"):
        raise ValueError("provider output message phase is unsupported")


def _validate_output_text_part(part: Mapping[str, object]) -> None:
    _reject_unknown_keys(
        part,
        allowed={"annotations", "logprobs", "text", "type"},
        label="provider output text",
    )
    if part.get("annotations") not in (None, []):
        raise ValueError("provider output text annotations must be empty")
    if part.get("logprobs") not in (None, []):
        raise ValueError("provider output text logprobs must be empty")


def _reject_unknown_keys(
    value: Mapping[str, object],
    *,
    allowed: set[str],
    label: str,
) -> None:
    if unknown := set(value) - allowed:
        raise ValueError(f"{label} contains unsupported fields: {sorted(unknown)}")


def _output_message_failure(
    output: Sequence[object],
) -> ProviderReceiptFailure | None:
    for raw_item in output:
        if not isinstance(raw_item, Mapping) or raw_item.get("type") != "message":
            continue
        if raw_item.get("role") != "assistant":
            return "output_message_role_mismatch"
        if raw_item.get("status") != "completed":
            return "output_message_status_mismatch"
    return None


def _output_text(payload: Mapping[str, object]) -> str:
    for key in ("text", "value"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    raise ValueError("provider output text part lacks text")


def _single_user_prompt(input_items: Sequence[Mapping[str, object]]) -> str:
    if len(input_items) != 1:
        raise ValueError("provider input topology must contain one item")
    item = input_items[0]
    if item.get("type") != "message" or item.get("role") != "user":
        raise ValueError("provider input topology must be one user message")
    content = item.get("content")
    if not isinstance(content, Sequence) or isinstance(content, str | bytes):
        raise TypeError("provider user message content must be a list")
    if len(content) != 1 or not isinstance(content[0], Mapping):
        raise ValueError("provider user message must contain one input_text part")
    part = content[0]
    if part.get("type") != "input_text":
        raise ValueError("provider user message part must be input_text")
    text = part.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError("provider input_text part lacks text")
    return text


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _duplicate_response_ids(
    expectations: Sequence[ProviderReceiptExpectation],
) -> frozenset[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for expectation in expectations:
        if expectation.response_id in seen:
            duplicates.add(expectation.response_id)
        seen.add(expectation.response_id)
    return frozenset(duplicates)


def _aggregate_receipt_status(
    receipts: Sequence[ProviderReceiptEvidence],
) -> ProviderReceiptStatus:
    statuses = {receipt.status for receipt in receipts}
    if statuses == {"verified_live"} and receipts:
        return "verified_live"
    for status in ("duplicate", "mismatched", "unavailable", "not_verified"):
        if status in statuses:
            return cast("ProviderReceiptStatus", status)
    return "not_verified"


__all__ = [
    "EXECUTION_MODEL_ID",
    "OpenAIProviderReceiptVerifier",
    "OutputSchemaVerificationSource",
    "ProviderOutputVerificationSource",
    "PROVIDER_MODEL_ID",
    "ProviderReceiptEvidence",
    "ProviderReceiptExpectation",
    "ProviderReceiptVerification",
    "ProviderReceiptVerifier",
    "REPORT_MODEL_ID",
    "canonical_provider_model_id",
    "canonical_provider_output_sha256",
    "verify_provider_receipts",
]
