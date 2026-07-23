"""V13 rejected-call transport, accounting, and custody regressions."""

from __future__ import annotations

import copy
import hashlib
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.accounting import (
    V13OperationalLedger,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
    V13ForegroundExecutionRuntime,
    V13ProviderExecution,
    V13ProviderExecutionError,
    execute_v13_foreground_call,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.rejected_custody import (
    persist_rejected_custody,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.request_contract import (
    V13ForegroundProviderRequest,
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
        assert (mode, use_api_names, exclude_unset, exclude_none) == (
            "json",
            True,
            True,
            False,
        )
        return copy.deepcopy(self.payload)


class _InputItems:
    def __init__(self, prompt: str, failure: Exception | None = None) -> None:
        self.prompt = prompt
        self.failure = failure
        self.calls = 0

    def list(
        self,
        response_id: str,
        *,
        limit: int,
        order: str,
        timeout: float,
    ) -> tuple[_Dumpable, ...]:
        self.calls += 1
        assert (response_id, limit, order, timeout) == (
            "resp-v13",
            100,
            "asc",
            30.0,
        )
        if self.failure is not None:
            raise self.failure
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
        *,
        input_failure: Exception | None = None,
    ) -> None:
        self.creation = creation
        self.confirmation = confirmation
        self.input_items = _InputItems("frozen input", input_failure)
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
        assert (response_id, timeout) == ("resp-v13", 30.0)
        if isinstance(self.confirmation, Exception):
            raise self.confirmation
        return _Dumpable(self.confirmation)


class _Client:
    def __init__(
        self,
        creation: dict[str, object] | Exception,
        confirmation: dict[str, object] | Exception,
        *,
        input_failure: Exception | None = None,
    ) -> None:
        self.responses = _Responses(
            creation,
            confirmation,
            input_failure=input_failure,
        )


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        value = self.value
        self.value += 1.25
        return value


_FORMAT = {
    "type": "json_schema",
    "name": "v13_custody_test",
    "description": "V13 custody test.",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
        "additionalProperties": False,
    },
}


def test_building_v13_request_does_not_import_background_transport() -> None:
    module_prefix = "scripts.validation.provider_receipt_boundary.background"
    source = f"""
import sys
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider import build_request

request = build_request(
    case_id="test-case",
    provider_input="frozen input",
    preregistration_sha256="a" * 64,
)
assert request.provider_input == "frozen input"
loaded = sorted(
    name for name in sys.modules
    if name == {module_prefix!r} or name.startswith({module_prefix!r} + ".")
)
if loaded:
    raise AssertionError(loaded)
"""
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_successful_transport_is_exactly_once_with_complete_custody() -> None:
    completed = _response('{"status":"OK"}')
    client = _Client(completed, copy.deepcopy(completed))
    acknowledged: list[str] = []

    execution = _execute(client, on_completed=acknowledged.append)

    assert isinstance(execution, V13ProviderExecution)
    assert execution.extraction.status == "OK"
    assert acknowledged == ["resp-v13"]
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 1
    assert client.responses.input_items.calls == 1
    assert execution.receipt["provider_creation_calls"] == 1
    assert execution.receipt["completed_provider_calls"] == 1
    assert execution.receipt["confirmation_retrieval_requests"] == 1
    assert execution.receipt["input_item_retrieval_requests"] == 1
    assert execution.receipt["provider_retries"] == 0
    assert execution.receipt["duplicate_creation_calls"] == 0
    transport = execution.receipt["v13_transport_custody"]
    assert isinstance(transport, dict)
    assert transport["creation_response"] == completed
    assert transport["confirmation_response"] == completed
    assert transport["input_items"]


def test_callback_failure_keeps_confirmation_input_payload_and_usage() -> None:
    completed = _response('{"status":"OK"}')
    client = _Client(completed, copy.deepcopy(completed))

    with pytest.raises(V13ProviderExecutionError) as raised:
        _execute(client, on_completed=_raise_callback)

    error = raised.value
    assert error.stage == "FOREGROUND_COMPLETION_CUSTODY"
    assert error.evidence.response_ids == ("resp-v13",)
    assert error.evidence.creation_response is not None
    assert error.evidence.confirmation_response is not None
    assert error.evidence.input_items is not None
    assert error.evidence.canonical_payload == {"status": "OK"}
    assert error.evidence.usage is not None
    assert error.evidence.usage["cost_usd"] == pytest.approx(0.0001655)
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 1
    assert client.responses.input_items.calls == 1
    assert "max_output_tokens" not in client.responses.create_kwargs
    assert "background" not in client.responses.create_kwargs


def test_confirmation_failure_still_retrieves_input_and_accounts_creation() -> None:
    completed = _response('{"status":"OK"}')
    client = _Client(completed, RuntimeError("confirmation unavailable"))

    with pytest.raises(V13ProviderExecutionError) as raised:
        _execute(client)

    error = raised.value
    assert error.stage == "FOREGROUND_CONFIRMATION_RETRIEVAL"
    assert error.evidence.confirmation_response is None
    assert error.evidence.input_items is not None
    assert error.evidence.usage is not None
    assert error.evidence.usage_accounting_status == "ACCOUNTED"
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 1
    assert client.responses.input_items.calls == 1


def test_input_retrieval_failure_keeps_confirmation_and_known_usage() -> None:
    completed = _response('{"status":"OK"}')
    client = _Client(
        completed,
        copy.deepcopy(completed),
        input_failure=RuntimeError("input unavailable"),
    )

    with pytest.raises(V13ProviderExecutionError) as raised:
        _execute(client)

    error = raised.value
    assert error.stage == "FOREGROUND_INPUT_RETRIEVAL"
    assert error.evidence.confirmation_response is not None
    assert error.evidence.input_items is None
    assert error.evidence.usage is not None
    assert error.evidence.confirmation_retrieval_requests == 1
    assert error.evidence.input_item_retrieval_requests == 1
    assert error.evidence.provider_retries == 0
    assert error.evidence.duplicate_creation_calls == 0


def test_schema_rejection_keeps_canonical_payload_and_usage() -> None:
    completed = _response('{"status":7}')
    client = _Client(completed, copy.deepcopy(completed))

    with pytest.raises(V13ProviderExecutionError) as raised:
        _execute(client)

    error = raised.value
    assert error.stage == "STRUCTURED_OUTPUT_SCHEMA"
    assert error.evidence.canonical_payload == {"status": 7}
    assert error.evidence.usage is not None
    assert error.evidence.completed_provider_calls == 1


def test_invalid_receipt_keeps_all_available_transport_evidence() -> None:
    creation = _response('{"status":"OK"}')
    confirmation = copy.deepcopy(creation)
    confirmation["metadata"] = {"experiment": "changed-after-create"}
    client = _Client(creation, confirmation)

    with pytest.raises(V13ProviderExecutionError) as raised:
        _execute(client)

    error = raised.value
    assert error.stage != "STRUCTURED_OUTPUT_SCHEMA"
    assert error.evidence.creation_response == creation
    assert error.evidence.confirmation_response == confirmation
    assert error.evidence.input_items is not None
    assert error.evidence.canonical_payload == {"status": "OK"}
    assert error.evidence.usage is not None


def test_creation_exception_is_explicitly_unaccounted_and_never_retried() -> None:
    client = _Client(RuntimeError("provider unavailable"), RuntimeError())

    with pytest.raises(V13ProviderExecutionError) as raised:
        _execute(client)

    error = raised.value
    assert error.stage == "FOREGROUND_CREATION"
    assert error.evidence.completed_provider_calls == 0
    assert error.evidence.usage is None
    assert error.evidence.usage_accounting_status == "UNACCOUNTED_UNKNOWN"
    assert client.responses.create_calls == 1
    assert client.responses.retrieve_calls == 0
    assert client.responses.input_items.calls == 0
    ledger = V13OperationalLedger().record_rejected(
        case_id="case-unknown",
        error=error,
        custody=None,
    )
    value = ledger.as_json(global_max_cost_usd=5.0)
    assert value["attempted_provider_calls"] == 1
    assert value["completed_provider_calls"] == 0
    assert value["rejected_provider_calls"] == 1
    assert value["unaccounted_provider_calls"] == 1
    assert value["cost_usd"] is None
    assert value["remaining_cost_usd"] is None
    assert value["budget_accounting_status"] == ("UNACCOUNTED_PROVIDER_SPEND_POSSIBLE")


def test_rejected_custody_binds_normal_paths_and_readback_hashes(
    tmp_path: Path,
) -> None:
    completed = _response('{"status":7}')
    client = _Client(completed, copy.deepcopy(completed))
    with pytest.raises(V13ProviderExecutionError) as raised:
        _execute(client)
    paths = _paths(tmp_path)

    custody = persist_rejected_custody(
        paths=paths,
        stage="GENERALIZATION_V13_EXPOSED:test-case",
        provider_input="frozen input",
        schema_sha256="a" * 64,
        error=raised.value,
    )

    assert custody.bundle_sha256 == _file_sha256(paths.bundle)
    assert custody.receipt_sha256 == _file_sha256(paths.receipt)
    assert custody.raw_output_sha256 == _file_sha256(paths.raw_output)
    ledger = V13OperationalLedger().record_rejected(
        case_id="test-case",
        error=raised.value,
        custody=custody,
    )
    value = ledger.as_json(global_max_cost_usd=5.0)
    assert value["attempted_provider_calls"] == 1
    assert value["completed_provider_calls"] == 1
    assert value["admitted_provider_calls"] == 0
    assert value["rejected_provider_calls"] == 1
    assert value["unaccounted_provider_calls"] == 0
    per_call = value["per_call"]
    assert isinstance(per_call, list)
    assert isinstance(per_call[0], dict)
    assert per_call[0]["rejected_custody"] == custody.as_json()


def _execute(
    client: _Client,
    *,
    on_completed: Callable[[str], None] | None = None,
) -> object:
    return execute_v13_foreground_call(
        api_key="redacted-test-key",
        request=V13ForegroundProviderRequest(
            provider_input="frozen input",
            provider_format=_FORMAT,
            provider_model_id="gpt-5.6-luna",
            reasoning_effort="high",
            pricing={
                "input": 0.000001,
                "cached_input": 0.0000001,
                "output": 0.000006,
            },
            metadata={"experiment": "v13-custody-test"},
        ),
        request_timeout_seconds=30.0,
        output_model=_Output,
        runtime=V13ForegroundExecutionRuntime(
            client=client,
            monotonic=_Clock().monotonic,
            on_completed=on_completed,
        ),
    )


def _response(payload: str) -> dict[str, object]:
    return {
        "id": "resp-v13",
        "object": "response",
        "created_at": 1000.0,
        "completed_at": 1001.0,
        "background": False,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "model": "gpt-5.6-luna",
        "reasoning": {"effort": "high"},
        "metadata": {"experiment": "v13-custody-test"},
        "text": {"format": _FORMAT},
        "output": [
            {
                "id": "msg-v13",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": payload}],
            }
        ],
        "usage": {
            "input_tokens": 20,
            "output_tokens": 25,
            "total_tokens": 45,
            "input_tokens_details": {"cached_tokens": 5},
            "output_tokens_details": {"reasoning_tokens": 4},
        },
    }


def _raise_callback(_response_id: str) -> None:
    raise RuntimeError("attempt acknowledgement failed")


def _paths(root: Path) -> CaseExecutionPaths:
    return CaseExecutionPaths(
        attempt=root / "attempt.json",
        bundle=root / "custody.json",
        receipt=root / "receipt.json",
        raw_output=root / "raw.json",
        evaluation=root / "evaluation.json",
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
