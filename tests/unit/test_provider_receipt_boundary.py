from __future__ import annotations

import copy
import json

import pytest

from scripts.validation.provider_receipt_boundary import (
    ReceiptBoundaryError,
    ReceiptExpectations,
    validate_provider_receipt,
)
from scripts.validation.provider_receipt_boundary.structural_diff import (
    structural_diff,
)

FORMAT = {
    "type": "json_schema",
    "name": "receipt_smoke",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["OK"]}},
        "required": ["status"],
        "additionalProperties": False,
    },
}
INPUT = "Return the categorical status OK."


def _response(*, payload_text: str = '{"status":"OK"}') -> dict[str, object]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1000.0,
        "completed_at": 1001.0,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "model": "gpt-5.6-sol",
        "metadata": {"experiment": "receipt-smoke"},
        "reasoning": {"effort": "low", "summary": None},
        "text": {"format": FORMAT},
        "service_tier": "default",
        "output": [
            {
                "id": "rs_1",
                "type": "reasoning",
                "summary": [],
                "content": None,
                "encrypted_content": None,
                "status": "completed",
            },
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "phase": None,
                "content": [
                    {
                        "type": "output_text",
                        "text": payload_text,
                        "annotations": [],
                        "logprobs": [],
                    }
                ],
            },
        ],
        "usage": {
            "input_tokens": 20,
            "input_tokens_details": {"cached_tokens": 5},
            "output_tokens": 10,
            "output_tokens_details": {"reasoning_tokens": 4},
            "total_tokens": 30,
        },
    }


def _input_items(text: str = INPUT) -> tuple[dict[str, object], ...]:
    return (
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    )


def _expectations(**overrides: object) -> ReceiptExpectations:
    values: dict[str, object] = {
        "provider_input": INPUT,
        "provider_format": FORMAT,
        "provider_model_id": "gpt-5.6-sol",
        "reasoning_effort": "low",
        "metadata": {"experiment": "receipt-smoke"},
        "max_total_tokens": 100,
        "max_cost_usd": 0.25,
        "max_latency_seconds": 60.0,
        "pricing": {
            "input": 0.000005,
            "cached_input": 0.0000005,
            "output": 0.00003,
        },
    }
    values.update(overrides)
    return ReceiptExpectations(**values)  # type: ignore[arg-type]


def _validate(
    creation: dict[str, object],
    retrieval: dict[str, object],
    *,
    input_items: tuple[dict[str, object], ...] | None = None,
    expectations: ReceiptExpectations | None = None,
):
    return validate_provider_receipt(
        creation=creation,
        retrieval=retrieval,
        input_items=input_items or _input_items(),
        expectations=expectations or _expectations(),
        latency_seconds=2.0,
    )


def test_identical_creation_and_retrieval_validate_with_truthful_cost() -> None:
    response = _response()

    receipt = _validate(response, copy.deepcopy(response))

    assert receipt.differences == ()
    assert receipt.usage.total_tokens == 30
    assert receipt.usage.cost_usd == pytest.approx(0.0003775)


def test_documented_transport_differences_and_json_key_order_are_allowlisted() -> None:
    creation = _response(payload_text='{"status":"OK","detail":"same"}')
    retrieval = copy.deepcopy(creation)
    creation["completed_at"] = None
    retrieval["text"] = None
    creation_output = creation["output"]
    retrieval_output = retrieval["output"]
    assert isinstance(creation_output, list)
    assert isinstance(retrieval_output, list)
    creation_output[0]["status"] = None
    retrieval_output[1]["phase"] = "final_answer"
    retrieval_output[1]["content"][0]["text"] = '{"detail":"same","status":"OK"}'

    receipt = _validate(creation, retrieval)

    assert receipt.scientific_payload_sha256
    assert receipt.creation_envelope_sha256 != receipt.retrieval_envelope_sha256
    assert receipt.differences
    assert all(item.allowlisted for item in receipt.differences)
    assert {item.path for item in receipt.differences} == {
        "$.completed_at",
        "$.output[0].status",
        "$.output[1].content[0].text",
        "$.output[1].phase",
        "$.text",
    }


def test_structural_diff_ignores_reordered_object_keys() -> None:
    assert structural_diff({"a": 1, "b": 2}, {"b": 2, "a": 1}) == ()


def test_scientific_payload_modification_fails() -> None:
    with pytest.raises(ReceiptBoundaryError, match="scientific payload changed"):
        _validate(_response(), _response(payload_text='{"status":"NOT_OK"}'))


def test_missing_output_fails() -> None:
    retrieval = _response()
    retrieval["output"] = []

    with pytest.raises(ReceiptBoundaryError, match="output identity"):
        _validate(_response(), retrieval)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "resp_2", "identities differ"),
        ("model", "different-model", "returned model differs"),
    ],
)
def test_changed_identity_fails(field: str, value: str, message: str) -> None:
    retrieval = _response()
    retrieval[field] = value

    with pytest.raises(ReceiptBoundaryError, match=message):
        _validate(_response(), retrieval)


def test_changed_output_item_identity_fails() -> None:
    retrieval = _response()
    output = retrieval["output"]
    assert isinstance(output, list)
    output[1]["id"] = "msg_2"

    with pytest.raises(ReceiptBoundaryError, match="identities differ"):
        _validate(_response(), retrieval)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "failed"),
        ("error", {"code": "provider_error"}),
        ("incomplete_details", {"reason": "max_output_tokens"}),
    ],
)
def test_incomplete_or_failed_response_fails(field: str, value: object) -> None:
    retrieval = _response()
    retrieval[field] = value

    with pytest.raises(ReceiptBoundaryError, match="not completed|incomplete"):
        _validate(_response(), retrieval)


def test_changed_input_or_schema_fails() -> None:
    with pytest.raises(ReceiptBoundaryError, match="input differs"):
        _validate(_response(), _response(), input_items=_input_items("changed"))

    retrieval = _response()
    retrieval["text"] = {"format": {**FORMAT, "name": "changed"}}
    with pytest.raises(ReceiptBoundaryError, match="schema differs") as error:
        _validate(_response(), retrieval)

    differences = error.value.diagnostics["differences"]
    assert differences[0]["path"] == "$.name"
    assert "changed" not in json.dumps(differences)


@pytest.mark.parametrize("usage", [None, {"input_tokens": -1}])
def test_missing_or_invalid_usage_fails(usage: object) -> None:
    creation = _response()
    retrieval = _response()
    creation["usage"] = usage
    retrieval["usage"] = usage

    with pytest.raises(ReceiptBoundaryError, match="RECEIPT_USAGE"):
        _validate(creation, retrieval)


def test_changed_usage_fails_instead_of_fabricating_cost() -> None:
    retrieval = _response()
    usage = retrieval["usage"]
    assert isinstance(usage, dict)
    usage["total_tokens"] = 31

    with pytest.raises(ReceiptBoundaryError, match="usage differ"):
        _validate(_response(), retrieval)


def test_unknown_envelope_difference_fails_with_redacted_path() -> None:
    retrieval = _response()
    retrieval["service_tier"] = "priority"

    with pytest.raises(ReceiptBoundaryError) as error:
        _validate(_response(), retrieval)

    assert error.value.stage == "RECEIPT_ENVELOPE"
    differences = error.value.diagnostics["differences"]
    assert differences[0]["path"] == "$.service_tier"
    assert "default" not in json.dumps(differences)
