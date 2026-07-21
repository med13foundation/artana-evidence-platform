from __future__ import annotations

import json

import pytest

from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
    execute_single_provider_call,
)


class _Dumpable:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return self.payload


class _InputItems:
    def __init__(self, prompt: str) -> None:
        self.prompt = prompt

    def list(self, response_id: str, *, limit: int, order: str):
        assert response_id == "resp-1"
        assert limit == 100
        assert order == "asc"
        return (
            _Dumpable(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": self.prompt}],
                }
            ),
        )


class _Responses:
    def __init__(self, payload: dict[str, object], prompt: str) -> None:
        self.payload = payload
        self.input_items = _InputItems(prompt)
        self.create_calls = 0

    def create(self, **kwargs: object) -> _Dumpable:
        self.create_calls += 1
        return _Dumpable(self.payload)

    def retrieve(self, response_id: str) -> _Dumpable:
        assert response_id == "resp-1"
        return _Dumpable(self.payload)


class _Client:
    def __init__(self, payload: dict[str, object], prompt: str) -> None:
        self.responses = _Responses(payload, prompt)


def _request(prompt: str, response_format: dict[str, object]) -> ProviderRequest:
    return ProviderRequest(
        provider_input=prompt,
        provider_format=response_format,
        provider_model_id="gpt-5.6-sol",
        reasoning_effort="high",
        max_output_tokens=20000,
        max_total_tokens=40000,
        max_cost_usd=5.0,
        max_latency_seconds=900.0,
        pricing={"input": 0.000005, "cached_input": 0.0000005, "output": 0.00003},
        metadata={"experiment": "test"},
    )


def _payload(response_format: dict[str, object]) -> dict[str, object]:
    structured = {
        "status": "ABSTAIN",
        "mentions": [],
        "events": [],
        "abstention_reason": "source is ambiguous",
    }
    return {
        "id": "resp-1",
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "model": "gpt-5.6-sol",
        "reasoning": {"effort": "high"},
        "metadata": {"experiment": "test"},
        "text": {"format": response_format},
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": json.dumps(structured)}
                ],
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "input_tokens_details": {"cached_tokens": 20},
        },
    }


def test_provider_transport_calls_model_once_and_verifies_receipt() -> None:
    prompt = "frozen input"
    response_format = {"type": "json_schema", "name": "test", "strict": True}
    client = _Client(_payload(response_format), prompt)

    execution = execute_single_provider_call(
        api_key="test",
        request=_request(prompt, response_format),
        client=client,
    )

    assert client.responses.create_calls == 1
    assert execution.extraction.status == "ABSTAIN"
    assert execution.receipt["status"] == "VERIFIED_LIVE"
    assert execution.receipt["provider_retries"] == 0
    assert execution.receipt["total_tokens"] == 150


def test_provider_transport_fails_closed_on_retrieved_input_drift() -> None:
    prompt = "frozen input"
    response_format = {"type": "json_schema", "name": "test", "strict": True}
    client = _Client(_payload(response_format), "changed input")

    with pytest.raises(ProviderExecutionError, match="RECEIPT_INPUT"):
        execute_single_provider_call(
            api_key="test",
            request=_request(prompt, response_format),
            client=client,
        )

    assert client.responses.create_calls == 1
