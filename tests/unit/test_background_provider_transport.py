from __future__ import annotations

import copy
from collections.abc import Callable

import pytest
from pydantic import BaseModel, ConfigDict

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundExecutionBudgets,
    BackgroundExecutionRuntime,
    BackgroundProviderExecution,
    execute_background_provider_call,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
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
        assert response_id == "resp-1"
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
        retrievals: list[dict[str, object] | Exception],
        prompt: str,
    ) -> None:
        self.creation = creation
        self.retrievals = list(retrievals)
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
        assert response_id == "resp-1"
        assert timeout == 30.0
        if not self.retrievals:
            raise AssertionError("unexpected retrieval")
        response = self.retrievals.pop(0)
        if isinstance(response, Exception):
            raise response
        return _Dumpable(response)


class _Client:
    def __init__(
        self,
        creation: dict[str, object] | Exception,
        retrievals: list[dict[str, object] | Exception],
        prompt: str = "frozen input",
    ) -> None:
        self.responses = _Responses(creation, retrievals, prompt)


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


FORMAT = {
    "type": "json_schema",
    "name": "background_smoke",
    "description": "A stable background transport response.",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
        "additionalProperties": False,
    },
}


def _request() -> ProviderRequest:
    return ProviderRequest(
        provider_input="frozen input",
        provider_format=FORMAT,
        provider_model_id="gpt-5.6-sol",
        reasoning_effort="low",
        max_output_tokens=100,
        max_total_tokens=200,
        max_cost_usd=0.25,
        max_latency_seconds=20.0,
        pricing={"input": 0.000005, "cached_input": 0.0000005, "output": 0.00003},
        metadata={"experiment": "background-test"},
    )


def _budgets(*, polling: float = 10.0) -> BackgroundExecutionBudgets:
    return BackgroundExecutionBudgets(
        acknowledgement_timeout_seconds=30.0,
        polling_interval_seconds=1.0,
        max_polling_seconds=polling,
    )


def _response(
    status: str,
    *,
    response_id: str = "resp-1",
    payload: str = '{"status":"OK"}',
) -> dict[str, object]:
    completed = status == "completed"
    return {
        "id": response_id,
        "object": "response",
        "created_at": 1000.0,
        "completed_at": 1001.0 if completed else None,
        "background": True,
        "status": status,
        "error": {"code": "provider_failed"} if status == "failed" else None,
        "incomplete_details": (
            {"reason": "max_output_tokens"} if status == "incomplete" else None
        ),
        "model": "gpt-5.6-sol",
        "reasoning": {"effort": "low"},
        "metadata": {"experiment": "background-test"},
        "text": {"format": FORMAT},
        "output": (
            [
                {
                    "id": "msg-1",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": payload}],
                }
            ]
            if completed
            else []
        ),
        "usage": (
            {
                "input_tokens": 20,
                "output_tokens": 10,
                "total_tokens": 30,
                "input_tokens_details": {"cached_tokens": 5},
                "output_tokens_details": {"reasoning_tokens": 4},
            }
            if completed
            else None
        ),
    }


def _execute(
    client: _Client,
    clock: _Clock,
    *,
    polling: float = 10.0,
    on_acknowledged: Callable[[str], None] | None = None,
) -> BackgroundProviderExecution[_Output]:
    return execute_background_provider_call(
        api_key="test",
        request=_request(),
        transport_budgets=_budgets(polling=polling),
        output_model=_Output,
        runtime=BackgroundExecutionRuntime(
            client=client,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
            on_acknowledged=on_acknowledged,
        ),
    )


def test_immediate_completion_uses_one_creation_and_one_confirmation() -> None:
    completed = _response("completed")
    client = _Client(completed, [completed])
    clock = _Clock()

    execution = _execute(client, clock)

    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 1
    assert client.responses.input_items.list_calls == 1
    assert client.responses.create_kwargs["background"] is True
    assert execution.extraction.status == "OK"
    assert execution.receipt["status_history"] == ["completed"]
    assert execution.receipt["model_generation_calls"] == 1
    assert execution.receipt["polling_retrieval_requests"] == 0


def test_acknowledgement_callback_receives_identity_before_polling() -> None:
    completed = _response("completed")
    client = _Client(_response("queued"), [completed, completed])
    acknowledged: list[str] = []

    _execute(client, _Clock(), on_acknowledged=acknowledged.append)

    assert acknowledged == ["resp-1"]


def test_acknowledgement_identity_is_preserved_before_binding_failure() -> None:
    malformed = _response("queued")
    malformed["model"] = "unexpected-model"
    acknowledged: list[str] = []

    with pytest.raises(ProviderExecutionError) as error:
        _execute(
            _Client(malformed, []),
            _Clock(),
            on_acknowledged=acknowledged.append,
        )

    assert acknowledged == ["resp-1"]
    assert error.value.diagnostics["response_id"] == "resp-1"


def test_queued_to_in_progress_to_completed_polls_only_one_response_id() -> None:
    completed = _response("completed")
    client = _Client(
        _response("queued"),
        [_response("in_progress"), completed, completed],
    )
    clock = _Clock()

    execution = _execute(client, clock)

    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 3
    assert execution.receipt["status_history"] == [
        "queued",
        "in_progress",
        "completed",
    ]
    assert execution.receipt["polling_retrieval_requests"] == 2
    assert execution.receipt["confirmation_retrieval_requests"] == 1
    assert execution.receipt["polling_does_not_count_as_model_generation"] is True
    usage = execution.receipt["usage"]
    assert isinstance(usage, dict)
    assert usage["latency_seconds"] == 2.0
    assert usage["cost_usd"] == pytest.approx(0.0003775)


def test_completed_background_response_accepts_multiple_reasoning_items() -> None:
    completed = _response("completed")
    output = completed["output"]
    assert isinstance(output, list)
    output[0:0] = [
        {
            "id": "rs-1",
            "type": "reasoning",
            "summary": [],
            "status": "completed",
        },
        {
            "id": "rs-2",
            "type": "reasoning",
            "summary": [],
            "status": "completed",
        },
    ]
    client = _Client(_response("queued"), [completed, completed])

    execution = _execute(client, _Clock())

    identity = execution.receipt["identity"]
    assert isinstance(identity, dict)
    assert identity["output_items"] == (
        ("reasoning", "rs-1"),
        ("reasoning", "rs-2"),
        ("message", "msg-1"),
    )
    assert execution.extraction.status == "OK"
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 2


@pytest.mark.parametrize("status", ["failed", "cancelled", "incomplete"])
def test_terminal_provider_failure_stops_before_confirmation(status: str) -> None:
    client = _Client(_response("queued"), [_response(status)])

    with pytest.raises(ProviderExecutionError) as error:
        _execute(client, _Clock())

    assert error.value.stage == "BACKGROUND_TERMINAL_FAILURE"
    assert error.value.diagnostics["response_id"] == "resp-1"
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 1
    assert client.responses.input_items.list_calls == 0


def test_unknown_status_fails_closed() -> None:
    client = _Client(_response("mystery"), [])

    with pytest.raises(ProviderExecutionError) as error:
        _execute(client, _Clock())

    assert error.value.stage == "BACKGROUND_UNKNOWN_STATUS"
    assert error.value.diagnostics["response_id"] == "resp-1"
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 0


def test_acknowledgement_timeout_never_repeats_creation() -> None:
    client = _Client(TimeoutError("ack timeout"), [])

    with pytest.raises(ProviderExecutionError) as error:
        _execute(client, _Clock())

    assert error.value.stage == "BACKGROUND_ACKNOWLEDGEMENT_TIMEOUT"
    assert error.value.diagnostics["duplicate_creation_may_exist"] is True
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 0


def test_polling_timeout_never_repeats_creation() -> None:
    client = _Client(_response("queued"), [_response("queued")])

    with pytest.raises(ProviderExecutionError) as error:
        _execute(client, _Clock(), polling=2.0)

    assert error.value.stage == "BACKGROUND_POLLING_TIMEOUT"
    assert error.value.diagnostics["creation_repeated"] is False
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 1


def test_response_id_change_fails_before_further_polling() -> None:
    client = _Client(
        _response("queued"),
        [_response("in_progress", response_id="resp-other")],
    )

    with pytest.raises(ProviderExecutionError) as error:
        _execute(client, _Clock())

    assert error.value.stage == "BACKGROUND_RESPONSE_ID_CHANGED"
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 1


@pytest.mark.parametrize(
    "retrieval",
    [RuntimeError("malformed retrieval"), {"status": "in_progress"}],
)
def test_malformed_retrieval_fails_closed(retrieval: object) -> None:
    client = _Client(_response("queued"), [retrieval])  # type: ignore[list-item]

    with pytest.raises(ProviderExecutionError) as error:
        _execute(client, _Clock())

    assert error.value.stage in {
        "BACKGROUND_POLL_RETRIEVAL",
        "BACKGROUND_RESPONSE_ID",
    }
    assert client.responses.create_calls == 1


def test_missing_usage_after_completion_fails_accounting() -> None:
    completed = _response("completed")
    completed["usage"] = None
    client = _Client(completed, [completed])

    with pytest.raises(ProviderExecutionError) as error:
        _execute(client, _Clock())

    assert error.value.stage == "RECEIPT_USAGE"
    assert client.responses.create_calls == 1


def test_receipt_payload_mismatch_after_completion_fails() -> None:
    terminal = _response("completed")
    confirmation = _response("completed", payload='{"status":"CHANGED"}')
    client = _Client(terminal, [confirmation])

    with pytest.raises(ProviderExecutionError) as error:
        _execute(client, _Clock())

    assert error.value.stage == "RECEIPT_PAYLOAD"
    assert client.responses.input_items.list_calls == 1


def test_background_budgets_must_be_positive() -> None:
    with pytest.raises(ValueError, match="polling_interval_seconds"):
        BackgroundExecutionBudgets(30.0, 0.0, 900.0)
