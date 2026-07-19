from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
)

from scripts.validation.claim_frames.provider_receipts import (
    OPENAI_PROVIDER_RECEIPT_BASE_URL,
    OpenAIProviderReceiptVerifier,
    ProviderReceiptExpectation,
    canonical_provider_output_sha256,
)


def test_environment_verifier_pins_the_canonical_openai_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openai

    observed: dict[str, object] = {}

    def fake_openai(**kwargs: object) -> SimpleNamespace:
        observed.update(kwargs)
        return SimpleNamespace(responses=SimpleNamespace())

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr(openai, "OpenAI", fake_openai)

    verifier = OpenAIProviderReceiptVerifier.from_environment()

    assert verifier is not None
    assert observed == {
        "api_key": "test-key",
        "base_url": OPENAI_PROVIDER_RECEIPT_BASE_URL,
    }


def test_environment_verifier_rejects_noncanonical_endpoint_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://synthetic.invalid/v1")

    with pytest.raises(ValueError, match="canonical OpenAI endpoint"):
        OpenAIProviderReceiptVerifier.from_environment()


@dataclass(frozen=True, slots=True)
class _RetrievedResponse:
    response_id: str
    output: list[dict[str, object]]
    text: dict[str, object] | None = None

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {
            "id": self.response_id,
            "model": "gpt-5.6-luna",
            "status": "completed",
            "incomplete_details": None,
            "error": None,
            "instructions": None,
            "previous_response_id": None,
            "conversation": None,
            "prompt": None,
            "tools": [],
            "context_management": [],
            "metadata": {},
            "output": copy.deepcopy(self.output),
            "text": copy.deepcopy(self.text),
        }


def test_schema_custody_uses_provider_input_when_response_omits_format() -> None:
    expectation, response, input_items, _schema = _receipt_fixture()

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: response,
        lambda _response_id: input_items,
    ).verify(expectation)

    assert evidence.status == "verified_live"
    assert evidence.failure == "none"
    assert evidence.retrieved_output_schema_sha256 == (
        expectation.expected_output_schema_sha256
    )
    assert evidence.output_schema_verification_source == "provider_input_binding"
    assert evidence.provider_response_schema_supported is False
    assert evidence.provider_output_hash_matched is True
    assert evidence.provider_output_verification_source == "exact_provider_output"


def test_schema_custody_records_response_and_input_evidence_when_available() -> None:
    expectation, response, input_items, schema = _receipt_fixture(
        include_response_schema=True,
    )
    assert response.text == {"format": {"schema": schema}}

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: response,
        lambda _response_id: input_items,
    ).verify(expectation)

    assert evidence.status == "verified_live"
    assert evidence.output_schema_verification_source == (
        "provider_response_and_input_binding"
    )
    assert evidence.provider_response_schema_supported is True


def test_schema_custody_rejects_mismatched_provider_input_binding() -> None:
    expectation, response, _input_items, _schema = _receipt_fixture()
    mismatched_input = _input_items_for(
        expectation,
        output_schema_sha256="f" * 64,
    )

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: response,
        lambda _response_id: mismatched_input,
    ).verify(expectation)

    assert evidence.status == "mismatched"
    assert evidence.failure == "output_schema_mismatch"
    assert evidence.output_schema_verification_source == "unverified"


def test_adapter_output_shape_may_differ_when_payload_and_envelope_match() -> None:
    expectation, response, input_items, _schema = _receipt_fixture()
    retrieved_output: list[dict[str, object]] = [
        {
            "id": "reasoning_provider_receipt_schema",
            "type": "reasoning",
            "status": None,
            "summary": [],
            "content": [],
            "encrypted_content": "provider-native-reasoning",
        },
        *response.output,
    ]
    transformed_response = _RetrievedResponse(
        response_id=response.response_id,
        output=retrieved_output,
    )

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: transformed_response,
        lambda _response_id: input_items,
    ).verify(expectation)

    assert evidence.status == "verified_live"
    assert evidence.provider_output_hash_matched is False
    assert evidence.provider_output_verification_source == (
        "structured_payload_with_verified_envelope"
    )
    assert evidence.retrieved_payload_sha256 == evidence.expected_payload_sha256


def test_adapter_transformation_accepts_null_inert_reasoning_content() -> None:
    expectation, response, input_items, _schema = _receipt_fixture()
    transformed_response = _RetrievedResponse(
        response_id=response.response_id,
        output=[
            {
                "id": "reasoning_provider_receipt_schema",
                "type": "reasoning",
                "status": None,
                "summary": [],
                "content": None,
                "encrypted_content": None,
            },
            *response.output,
        ],
    )

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: transformed_response,
        lambda _response_id: input_items,
    ).verify(expectation)

    assert evidence.status == "verified_live"
    assert evidence.provider_output_verification_source == (
        "structured_payload_with_verified_envelope"
    )


def test_adapter_transformation_accepts_multiple_inert_reasoning_items() -> None:
    expectation, response, input_items, _schema = _receipt_fixture()
    reasoning_items = [
        {
            "id": f"reasoning_provider_receipt_{index}",
            "type": "reasoning",
            "status": None,
            "summary": [],
            "content": [],
            "encrypted_content": None,
        }
        for index in range(2)
    ]
    transformed_response = _RetrievedResponse(
        response_id=response.response_id,
        output=[*reasoning_items, *response.output],
    )

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: transformed_response,
        lambda _response_id: input_items,
    ).verify(expectation)

    assert evidence.status == "verified_live"
    assert evidence.provider_output_hash_matched is False
    assert evidence.provider_output_verification_source == (
        "structured_payload_with_verified_envelope"
    )


@pytest.mark.parametrize(
    "unexpected_output",
    [
        {
            "id": "msg_extra",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": '{"decision":"NO_EVENT"}'}],
        },
        {
            "id": "msg_refusal",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "refusal", "refusal": "Cannot comply."}],
        },
        {
            "id": "call_unexpected",
            "type": "function_call",
            "status": "completed",
            "name": "unexpected_tool",
            "arguments": "{}",
        },
        {
            "id": "item_unexpected",
            "type": "file_search_call",
            "status": "completed",
        },
        {
            "id": "reasoning_unrepresented",
            "type": "reasoning",
            "status": None,
            "summary": [],
            "content": [
                {"type": "reasoning_text", "text": "Unrepresented reasoning."}
            ],
            "encrypted_content": None,
        },
        {
            "id": "reasoning_summary",
            "type": "reasoning",
            "status": None,
            "summary": [{"type": "summary_text", "text": "Visible summary."}],
            "content": [],
            "encrypted_content": None,
        },
        {
            "id": "reasoning_unknown_field",
            "type": "reasoning",
            "status": None,
            "summary": [],
            "content": [],
            "encrypted_content": None,
            "unexpected": "not represented by the adapter",
        },
    ],
)
def test_adapter_transformation_rejects_unrepresented_provider_output(
    unexpected_output: dict[str, object],
) -> None:
    expectation, response, input_items, _schema = _receipt_fixture()
    transformed_response = _RetrievedResponse(
        response_id=response.response_id,
        output=[*response.output, unexpected_output],
    )

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: transformed_response,
        lambda _response_id: input_items,
    ).verify(expectation)

    assert evidence.status == "mismatched"
    assert evidence.failure == "payload_parse_failed"
    assert evidence.provider_output_verification_source == "unverified"


def test_adapter_transformation_rejects_unknown_message_fields() -> None:
    expectation, response, input_items, _schema = _receipt_fixture()
    output = copy.deepcopy(response.output)
    output[0]["unexpected"] = "not represented by the adapter"
    transformed_response = _RetrievedResponse(
        response_id=response.response_id,
        output=output,
    )

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: transformed_response,
        lambda _response_id: input_items,
    ).verify(expectation)

    assert evidence.status == "mismatched"
    assert evidence.failure == "payload_parse_failed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("annotations", [{"type": "url_citation"}]),
        ("logprobs", [{"token": "NO_EVENT"}]),
        ("unexpected", "not represented by the adapter"),
    ],
)
def test_adapter_transformation_rejects_unrepresented_output_text_fields(
    field: str,
    value: object,
) -> None:
    expectation, response, input_items, _schema = _receipt_fixture()
    output = copy.deepcopy(response.output)
    content = cast("list[dict[str, object]]", output[0]["content"])
    content[0][field] = value
    transformed_response = _RetrievedResponse(
        response_id=response.response_id,
        output=output,
    )

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: transformed_response,
        lambda _response_id: input_items,
    ).verify(expectation)

    assert evidence.status == "mismatched"
    assert evidence.failure == "payload_parse_failed"


def test_adapter_transformation_rejects_commentary_message_phase() -> None:
    expectation, response, input_items, _schema = _receipt_fixture()
    output = copy.deepcopy(response.output)
    output[0]["phase"] = "commentary"
    transformed_response = _RetrievedResponse(
        response_id=response.response_id,
        output=output,
    )

    evidence = OpenAIProviderReceiptVerifier(
        lambda _response_id: transformed_response,
        lambda _response_id: input_items,
    ).verify(expectation)

    assert evidence.status == "mismatched"
    assert evidence.failure == "payload_parse_failed"


def _receipt_fixture(
    *,
    include_response_schema: bool = False,
) -> tuple[
    ProviderReceiptExpectation,
    _RetrievedResponse,
    list[dict[str, object]],
    dict[str, object],
]:
    response_id = "resp_provider_receipt_schema"
    invocation_id = "provider-receipt-schema"
    source_sha256 = _sha256_text("IL-4 inhibited FOXP3 expression.")
    input_sha256 = _sha256_text("finite-source-unit-input")
    evidence_unit_sha256 = _sha256_text("finite-source-unit")
    schema = {
        "type": "object",
        "properties": {"decision": {"type": "string"}},
        "required": ["decision"],
        "additionalProperties": False,
    }
    schema_sha256 = canonical_provider_output_sha256(schema)
    payload = {"decision": "NO_EVENT"}
    output: list[dict[str, object]] = [
        {
            "id": "msg_provider_receipt_schema",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": json.dumps(
                        payload,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            ],
        },
    ]
    prompt = bind_prompt_to_invocation(
        prompt="Classify the frozen source unit.",
        invocation_id=invocation_id,
        source_sha256=source_sha256,
        input_sha256=input_sha256,
        evidence_unit_sha256=evidence_unit_sha256,
        output_schema_sha256=schema_sha256,
    )
    expectation = ProviderReceiptExpectation(
        response_id=response_id,
        expected_case_id="source-unit-1",
        expected_model_id="gpt-5.6-luna",
        expected_output_sha256=canonical_provider_output_sha256(output),
        expected_payload_sha256=canonical_provider_output_sha256(payload),
        expected_prompt_sha256=_sha256_text(prompt),
        expected_invocation_id=invocation_id,
        expected_kernel_run_id=f"research-init-extraction:{invocation_id}",
        expected_source_sha256=source_sha256,
        expected_input_sha256=input_sha256,
        expected_evidence_unit_sha256=evidence_unit_sha256,
        expected_output_schema_sha256=schema_sha256,
    )
    response = _RetrievedResponse(
        response_id=response_id,
        output=output,
        text={"format": {"schema": schema}} if include_response_schema else None,
    )
    return expectation, response, _input_items_for(expectation), schema


def _input_items_for(
    expectation: ProviderReceiptExpectation,
    *,
    output_schema_sha256: str | None = None,
) -> list[dict[str, object]]:
    prompt = bind_prompt_to_invocation(
        prompt="Classify the frozen source unit.",
        invocation_id=expectation.expected_invocation_id,
        source_sha256=expectation.expected_source_sha256,
        input_sha256=expectation.expected_input_sha256,
        evidence_unit_sha256=expectation.expected_evidence_unit_sha256,
        output_schema_sha256=(
            output_schema_sha256
            or expectation.expected_output_schema_sha256
            or "0" * 64
        ),
    )
    return [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        },
    ]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
