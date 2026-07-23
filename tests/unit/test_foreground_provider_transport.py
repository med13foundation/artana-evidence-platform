"""Direct foreground Responses transport regression tests."""

from __future__ import annotations

import copy
from collections.abc import Callable

import pytest
from pydantic import BaseModel, ConfigDict

from scripts.validation.provider_receipt_boundary.background import (
    TelemetryProviderRequestV2,
)
from scripts.validation.provider_receipt_boundary.foreground import (
    ForegroundExecutionRuntime,
    execute_foreground_provider_call_telemetry_v2,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)


class _Output(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    status: str


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
        return copy.deepcopy(self.payload)


class _InputItems:
    def __init__(self, prompt: str) -> None:
        self.prompt = prompt
        self.list_calls = 0

    def list(
        self,
        response_id: str,
        *,
        limit: int,
        order: str,
        timeout: float,
    ) -> tuple[_Dumpable, ...]:
        self.list_calls += 1
        assert response_id == "resp-foreground"
        assert limit == 100
        assert order == "asc"
        assert timeout == 30.0
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
        creation: dict[str, object] | Exception,
        confirmation: dict[str, object] | Exception,
        prompt: str,
    ) -> None:
        self.creation = creation
        self.confirmation = confirmation
        self.input_items = _InputItems(prompt)
        self.create_calls = 0
        self.retrieve_calls = 0
        self.create_kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> _Dumpable:
        self.create_calls += 1
        self.create_kwargs = kwargs
        if isinstance(self.creation, Exception):
            raise self.creation
        return _Dumpable(self.creation)

    def retrieve(self, response_id: str, *, timeout: float) -> _Dumpable:
        self.retrieve_calls += 1
        assert response_id == "resp-foreground"
        assert timeout == 30.0
        if isinstance(self.confirmation, Exception):
            raise self.confirmation
        return _Dumpable(self.confirmation)


class _Client:
    def __init__(
        self,
        creation: dict[str, object] | Exception,
        confirmation: dict[str, object] | Exception,
        prompt: str = "frozen input",
    ) -> None:
        self.responses = _Responses(creation, confirmation, prompt)


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        current = self.value
        self.value += 1.25
        return current


_FORMAT = {
    "type": "json_schema",
    "name": "foreground_smoke",
    "description": "A stable foreground transport response.",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
        "additionalProperties": False,
    },
}


def test_foreground_request_omits_background_and_generation_limits() -> None:
    completed = _response(output_tokens=100_000)
    client = _Client(completed, copy.deepcopy(completed))
    acknowledged: list[str] = []

    execution = _execute(
        client,
        on_completed=acknowledged.append,
    )

    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 1
    assert client.responses.input_items.list_calls == 1
    assert acknowledged == ["resp-foreground"]
    assert "background" not in client.responses.create_kwargs
    assert "max_output_tokens" not in client.responses.create_kwargs
    assert "max_total_tokens" not in client.responses.create_kwargs
    assert client.responses.create_kwargs["store"] is True
    assert execution.receipt["provider_creation_calls"] == 1
    assert execution.receipt["provider_retries"] == 0
    assert execution.receipt["duplicate_creation_calls"] == 0
    assert execution.receipt["usage"]["output_tokens"] == 100_000
    assert execution.receipt["token_and_cost_policy"] == (
        "RECORD_ONLY_NOT_SCIENTIFIC_VALIDITY"
    )


def test_foreground_creation_failure_never_retries() -> None:
    client = _Client(RuntimeError("provider unavailable"), RuntimeError())

    with pytest.raises(ProviderExecutionError) as error:
        _execute(client)

    assert error.value.stage == "FOREGROUND_CREATION"
    assert error.value.diagnostics["provider_creation_calls"] == 1
    assert error.value.diagnostics["provider_retries"] == 0
    assert error.value.diagnostics["duplicate_creation_calls"] == 0
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 0
    assert client.responses.input_items.list_calls == 0


def test_foreground_confirmation_usage_is_record_only_authority() -> None:
    creation = _response(output_tokens=25)
    confirmation = copy.deepcopy(creation)
    confirmation_usage = confirmation["usage"]
    assert isinstance(confirmation_usage, dict)
    details = confirmation_usage["input_tokens_details"]
    assert isinstance(details, dict)
    details["cache_write_tokens"] = 0
    client = _Client(creation, confirmation)

    execution = _execute(client)

    policy = execution.receipt["foreground_usage_policy"]
    assert isinstance(policy, dict)
    assert policy["authoritative_snapshot"] == "CONFIRMATION_RETRIEVAL"
    assert policy["scientific_validity_dependency"] is False
    assert policy["snapshots_differ"] is True
    assert execution.receipt["usage"]["output_tokens"] == 25
    differences = execution.receipt["differences"]
    assert isinstance(differences, list)
    assert any(
        item["path"] == "$.usage" and item["allowlisted"] is True
        for item in differences
    )
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 1


def _execute(
    client: _Client,
    *,
    on_completed: Callable[[str], None] | None = None,
) -> object:
    return execute_foreground_provider_call_telemetry_v2(
        api_key="redacted-test-key",
        request=TelemetryProviderRequestV2(
            provider_input="frozen input",
            provider_format=_FORMAT,
            provider_model_id="gpt-5.6-luna",
            reasoning_effort="high",
            pricing={
                "input": 0.000001,
                "cached_input": 0.0000001,
                "output": 0.000006,
            },
            metadata={"experiment": "foreground-test"},
        ),
        request_timeout_seconds=30.0,
        output_model=_Output,
        runtime=ForegroundExecutionRuntime(
            client=client,
            monotonic=_Clock().monotonic,
            on_completed=on_completed,
        ),
    )


def _response(*, output_tokens: int) -> dict[str, object]:
    return {
        "id": "resp-foreground",
        "object": "response",
        "created_at": 1000.0,
        "completed_at": 1001.0,
        "background": False,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "model": "gpt-5.6-luna",
        "reasoning": {"effort": "high"},
        "metadata": {"experiment": "foreground-test"},
        "text": {"format": _FORMAT},
        "output": [
            {
                "id": "msg-foreground",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": '{"status":"OK"}'}
                ],
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": output_tokens,
            "total_tokens": 20 + output_tokens,
            "input_tokens_details": {"cached_tokens": 5},
            "output_tokens_details": {"reasoning_tokens": 4},
        },
    }
