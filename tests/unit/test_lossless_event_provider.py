from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ConfigDict

from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
    execute_single_provider_call,
)


class _Dumpable:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def to_dict(
        self,
        *,
        mode: str,
        use_api_names: bool,
        exclude_unset: bool,
        exclude_none: bool,
    ) -> dict[str, object]:
        assert mode == "json"
        assert use_api_names is True
        assert exclude_unset is True
        assert exclude_none is False
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
    def __init__(
        self,
        creation: dict[str, object],
        retrieval: dict[str, object],
        prompt: str,
    ) -> None:
        self.creation = creation
        self.retrieval = retrieval
        self.input_items = _InputItems(prompt)
        self.create_calls = 0

    def create(self, **kwargs: object) -> _Dumpable:
        self.create_calls += 1
        return _Dumpable(self.creation)

    def retrieve(self, response_id: str) -> _Dumpable:
        assert response_id == "resp-1"
        return _Dumpable(self.retrieval)


class _Client:
    def __init__(
        self,
        creation: dict[str, object],
        prompt: str,
        retrieval: dict[str, object] | None = None,
    ) -> None:
        self.responses = _Responses(creation, retrieval or creation, prompt)


class _SmokeOutput(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    status: str


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
        "status": "OK",
    }
    return {
        "id": "resp-1",
        "object": "response",
        "created_at": 1000.0,
        "completed_at": 1001.0,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "model": "gpt-5.6-sol",
        "reasoning": {"effort": "high"},
        "metadata": {"experiment": "test"},
        "text": {"format": response_format},
        "output": [
            {
                "id": "rs-1",
                "type": "reasoning",
                "summary": [],
                "content": None,
                "encrypted_content": None,
                "status": "completed",
            },
            {
                "id": "msg-1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(structured)}],
            },
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens_details": {"reasoning_tokens": 10},
        },
    }


def test_provider_transport_calls_model_once_and_verifies_receipt() -> None:
    prompt = "frozen input"
    response_format = {"type": "json_schema", "name": "test", "strict": True}
    client = _Client(_payload(response_format), prompt)

    execution = execute_single_provider_call(
        api_key="test",
        request=_request(prompt, response_format),
        output_model=_SmokeOutput,
        client=client,
    )

    assert client.responses.create_calls == 1
    assert execution.extraction.status == "OK"
    assert execution.receipt["status"] == "VERIFIED_LIVE"
    assert execution.receipt["provider_retries"] == 0
    assert execution.receipt["usage"]["total_tokens"] == 150


def test_provider_transport_fails_closed_on_retrieved_input_drift() -> None:
    prompt = "frozen input"
    response_format = {"type": "json_schema", "name": "test", "strict": True}
    client = _Client(_payload(response_format), "changed input")

    with pytest.raises(ProviderExecutionError, match="RECEIPT_INPUT"):
        execute_single_provider_call(
            api_key="test",
            request=_request(prompt, response_format),
            output_model=_SmokeOutput,
            client=client,
        )

    assert client.responses.create_calls == 1
