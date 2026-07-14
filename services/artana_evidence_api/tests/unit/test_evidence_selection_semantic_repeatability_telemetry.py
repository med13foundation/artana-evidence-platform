"""Runtime-ledger telemetry regressions for semantic model comparison."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from artana.events import EventType, ModelRequestedPayload, ModelTerminalPayload
from artana_evidence_api.evidence_selection.repeatability.contracts import (
    SemanticRuntimeLedgerObservation,
)
from artana_evidence_api.evidence_selection.repeatability.runtime.ledger import (
    semantic_model_attempts_sha256,
)
from artana_evidence_api.evidence_selection.repeatability.telemetry import (
    collect_semantic_run_telemetry,
)
from artana_evidence_api.evidence_selection.semantic.attempts import (
    SemanticLocalValidationFailure,
    SemanticModelAttemptContext,
    semantic_batch_id,
    semantic_governed_context_sha256,
)
from pydantic import ValidationError

_MODEL_ID = "openai:gpt-5.4-mini"
_STEP_KEY = "evidence_selection.semantic_selector.v2"
_CONTEXT_SHA256 = "c" * 64


class _EventStore:
    def __init__(self, events: dict[str, list[object]]) -> None:
        self._events = events

    async def get_events_for_run(self, execution_id: str) -> list[object]:
        return self._events.get(execution_id, [])


def _attempt(
    execution_id: str,
    *,
    sequence: int = 1,
    local_failure: SemanticLocalValidationFailure | None = None,
) -> SemanticModelAttemptContext:
    references = ("sr_0123456789abcdef0123456789abcdef",)
    return SemanticModelAttemptContext(
        execution_id=execution_id,
        batch_id=semantic_batch_id(
            source_key="pubmed",
            search_id="search-1",
            record_references=references,
            governed_context_sha256=_CONTEXT_SHA256,
        ),
        governed_context_sha256=_CONTEXT_SHA256,
        attempt_sequence=sequence,
        batch_attempt_number=sequence,
        step_key=_STEP_KEY,
        source_key="pubmed",
        search_id="search-1",
        record_references=references,
        local_failure=local_failure,
    )


def _requested_event(execution_id: str, *, model_id: str = _MODEL_ID) -> object:
    payload = ModelRequestedPayload(
        model=model_id,
        prompt="governed prompt",
        messages=(),
        step_key=_STEP_KEY,
        model_cycle_id=f"cycle-{execution_id}",
    )
    return SimpleNamespace(
        event_type=EventType.MODEL_REQUESTED,
        event_id=f"request-{execution_id}",
        run_id=execution_id,
        seq=1,
        event_hash=hashlib.sha256(f"request-{execution_id}".encode()).hexdigest(),
        payload=payload,
    )


def _run_events(execution_id: str, terminal: object | None = None) -> list[object]:
    return [_requested_event(execution_id), terminal or _terminal_event(execution_id)]


def _terminal_event(
    execution_id: str,
    *,
    outcome: str = "completed",
    model_id: str = _MODEL_ID,
    prompt_tokens: int | None = 100,
    completion_tokens: int | None = 20,
    cost_usd: float | None = 0.001,
    error_category: str | None = None,
    error_class: str | None = None,
    diagnostics_json: str | None = None,
) -> object:
    payload = ModelTerminalPayload.model_validate(
        {
            "outcome": outcome,
            "model": model_id,
            "model_cycle_id": f"cycle-{execution_id}",
            "source_model_requested_event_id": f"request-{execution_id}",
            "step_key": _STEP_KEY,
            "elapsed_ms": 250,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost_usd,
            "error_category": error_category,
            "error_class": error_class,
            "diagnostics_json": diagnostics_json,
        },
    )
    return SimpleNamespace(
        event_type=EventType.MODEL_TERMINAL,
        event_id=f"terminal-{execution_id}",
        run_id=execution_id,
        seq=2,
        event_hash=hashlib.sha256(f"terminal-{execution_id}".encode()).hexdigest(),
        payload=payload,
    )


@pytest.mark.asyncio
async def test_runtime_telemetry_binds_complete_attempt_observations() -> None:
    attempts = (_attempt("run-1", sequence=1), _attempt("run-2", sequence=2))
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore(
            {
                "run-1": _run_events("run-1"),
                "run-2": _run_events("run-2"),
            },
        ),
        attempts=attempts,
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.8,
    )

    assert telemetry.ledger.status == "available"
    assert telemetry.ledger.execution_ids == ("run-1", "run-2")
    assert telemetry.ledger.total_tokens == 240
    assert telemetry.ledger.cost_usd == pytest.approx(0.002)
    assert telemetry.ledger.model_latency_seconds == pytest.approx(0.5)
    assert telemetry.ledger.token_usage_provenance == "artana_model_terminal"
    assert telemetry.ledger.cost_usage_provenance == "artana_model_terminal"
    assert telemetry.ledger.unavailable_reasons == ()
    assert telemetry.ledger.model_attempts[0].batch_id == attempts[0].batch_id


@pytest.mark.asyncio
async def test_schema_failure_is_typed_and_usage_is_explicitly_unavailable() -> None:
    attempt = _attempt("run-schema")
    event = _terminal_event(
        "run-schema",
        outcome="failed",
        prompt_tokens=None,
        completion_tokens=None,
        cost_usd=None,
        error_category="internal",
        error_class="ValidationError",
        diagnostics_json=json.dumps(
            {
                "message": "schema mismatch",
                "exception_module": "pydantic_core._pydantic_core",
            },
        ),
    )

    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore({"run-schema": _run_events("run-schema", event)}),
        attempts=(attempt,),
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.3,
    )

    observed = telemetry.ledger.model_attempts[0]
    assert observed.status == "failed"
    assert observed.failure_stage == "output_schema_validation"
    assert observed.failure_cause == "schema_contract_rejected"
    assert observed.execution_id == attempt.execution_id
    assert observed.batch_id == attempt.batch_id
    assert observed.prompt_tokens is None
    assert observed.completion_tokens is None
    assert observed.cost_usd is None
    assert observed.token_usage_provenance == "unavailable"
    assert observed.cost_usage_provenance == "unavailable"
    assert (
        observed.token_usage_unavailable_reason
        == "artana_exception_did_not_preserve_provider_usage"
    )
    assert telemetry.ledger.status == "partial"


@pytest.mark.asyncio
async def test_completed_terminal_retains_local_validation_rejection() -> None:
    failure = SemanticLocalValidationFailure(
        stage="semantic_batch_validation",
        cause="record_coverage_mismatch",
    )
    attempt = _attempt("run-local", local_failure=failure)

    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore({"run-local": _run_events("run-local")}),
        attempts=(attempt,),
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.3,
    )

    observed = telemetry.ledger.model_attempts[0]
    assert observed.terminal_outcome == "completed"
    assert observed.status == "rejected"
    assert observed.failure_stage == "semantic_batch_validation"
    assert observed.failure_cause == "record_coverage_mismatch"
    assert telemetry.ledger.status == "available"


@pytest.mark.asyncio
async def test_missing_terminal_preserves_attempt_and_typed_unavailable_reason() -> None:
    attempt = _attempt("run-missing")
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore({}),
        attempts=(attempt,),
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.1,
    )

    assert telemetry.ledger.status == "unavailable"
    assert telemetry.ledger.model_attempt_count == 1
    assert telemetry.ledger.model_terminal_count == 0
    observed = telemetry.ledger.model_attempts[0]
    assert observed.status == "telemetry_unavailable"
    assert observed.failure_cause == "model_terminal_event_missing"
    assert telemetry.ledger.unavailable_reasons == ("model_terminal_event_missing",)


@pytest.mark.asyncio
async def test_runtime_telemetry_is_explicitly_unavailable_without_attempts() -> None:
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore({}),
        attempts=(),
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.1,
    )

    assert telemetry.ledger.status == "unavailable"
    assert telemetry.ledger.model_attempt_count == 0
    assert telemetry.ledger.unavailable_reasons == ("no_model_attempts",)


@pytest.mark.asyncio
async def test_runtime_telemetry_rejects_wrong_model_terminal_event() -> None:
    with pytest.raises(ValueError, match="does not match the frozen model"):
        await collect_semantic_run_telemetry(
            store=_EventStore(
                {
                    "run-1": _run_events(
                        "run-1",
                        _terminal_event("run-1", model_id="openai:gpt-5"),
                    ),
                },
            ),
            attempts=(_attempt("run-1"),),
            expected_model_id=_MODEL_ID,
            wall_elapsed_seconds=0.1,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("batch_id", "semantic_batch_ffffffffffffffffffffffffffffffff"),
        ("failure_stage", "provider_call"),
        ("failure_cause", "network_error"),
        ("model_requested_event_hash", "f" * 64),
        (
            "token_usage_unavailable_reason",
            "artana_exception_did_not_preserve_provider_usage",
        ),
    ],
)
async def test_model_attempt_digest_detects_failure_telemetry_tampering(
    field: str,
    forged_value: object,
) -> None:
    event = _terminal_event(
        "run-1",
        outcome="failed",
        prompt_tokens=None,
        completion_tokens=None,
        cost_usd=None,
        error_category="internal",
    )
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore({"run-1": _run_events("run-1", event)}),
        attempts=(_attempt("run-1"),),
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.1,
    )
    payload = telemetry.ledger.model_dump(mode="json")
    payload["model_attempts"][0][field] = forged_value

    with pytest.raises(ValidationError, match="snapshot digest does not match"):
        SemanticRuntimeLedgerObservation.model_validate_json(json.dumps(payload))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("prompt_tokens", 1),
        ("completion_tokens", 1),
        ("total_tokens", 2),
        ("cost_usd", 0.0),
        ("model_latency_seconds", 0.0),
        ("token_usage_provenance", "unavailable"),
        ("cost_usage_provenance", "unavailable"),
        ("unavailable_reasons", ["artana_terminal_missing_cost_usage"]),
    ],
)
async def test_runtime_telemetry_rejects_forged_aggregates(
    field: str,
    forged_value: object,
) -> None:
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore({"run-1": _run_events("run-1")}),
        attempts=(_attempt("run-1"),),
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.1,
    )
    payload = telemetry.ledger.model_dump(mode="json")
    payload[field] = forged_value

    with pytest.raises(ValidationError, match="aggregate does not match"):
        SemanticRuntimeLedgerObservation.model_validate_json(json.dumps(payload))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "category", "status", "cause"),
    [
        ("completed", None, "completed", None),
        ("failed", "internal", "failed", "internal_error"),
        ("timeout", "timeout", "failed", "timeout"),
        ("cancelled", "cancelled", "failed", "cancelled"),
        ("abandoned", "abandoned", "abandoned", "abandoned"),
    ],
)
async def test_production_terminal_outcomes_map_categorically(
    outcome: str,
    category: str | None,
    status: str,
    cause: str | None,
) -> None:
    execution_id = f"run-{outcome}"
    terminal = _terminal_event(
        execution_id,
        outcome=outcome,
        error_category=category,
        error_class=None if outcome == "completed" else "RuntimeError",
    )
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore({execution_id: _run_events(execution_id, terminal)}),
        attempts=(_attempt(execution_id),),
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.1,
    )

    observed = telemetry.ledger.model_attempts[0]
    assert observed.status == status
    assert observed.failure_cause == cause


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "category"),
    [
        ("completed", "internal"),
        ("timeout", "internal"),
        ("cancelled", "timeout"),
        ("failed", "timeout"),
    ],
)
async def test_terminal_outcome_category_contradictions_are_rejected(
    outcome: str,
    category: str,
) -> None:
    execution_id = f"run-inconsistent-{outcome}"
    terminal = _terminal_event(
        execution_id,
        outcome=outcome,
        error_category=category,
        error_class="RuntimeError",
    )
    with pytest.raises(ValueError, match="error|contradicts|consistent"):
        await collect_semantic_run_telemetry(
            store=_EventStore({execution_id: _run_events(execution_id, terminal)}),
            attempts=(_attempt(execution_id),),
            expected_model_id=_MODEL_ID,
            wall_elapsed_seconds=0.1,
        )


@pytest.mark.asyncio
async def test_timeout_missing_usage_does_not_claim_schema_usage_loss() -> None:
    execution_id = "run-timeout-usage"
    terminal = _terminal_event(
        execution_id,
        outcome="timeout",
        error_category="timeout",
        error_class="ModelTimeoutError",
        prompt_tokens=None,
        completion_tokens=None,
        cost_usd=None,
    )
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore({execution_id: _run_events(execution_id, terminal)}),
        attempts=(_attempt(execution_id),),
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.1,
    )

    observed = telemetry.ledger.model_attempts[0]
    assert observed.token_usage_unavailable_reason == "artana_terminal_missing_token_usage"
    assert observed.cost_usage_unavailable_reason == "artana_terminal_missing_cost_usage"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    ["request_id", "request_hash", "run", "model", "step", "cycle"],
)
async def test_terminal_request_join_validates_the_exact_request(mutation: str) -> None:
    execution_id = f"run-request-{mutation}"
    request = _requested_event(execution_id)
    terminal = _terminal_event(execution_id)
    if mutation == "request_id":
        request = SimpleNamespace(**{**vars(request), "event_id": "wrong-request"})
    elif mutation == "request_hash":
        request = SimpleNamespace(**{**vars(request), "event_hash": "invalid"})
    elif mutation == "run":
        request = SimpleNamespace(**{**vars(request), "run_id": "wrong-run"})
    else:
        payload = request.payload
        updates = {
            "model": "openai:wrong-model",
            "step": "wrong-step",
            "cycle": "wrong-cycle",
        }
        field_names = {"model": "model", "step": "step_key", "cycle": "model_cycle_id"}
        request = SimpleNamespace(
            **{
                **vars(request),
                "payload": payload.model_copy(
                    update={field_names[mutation]: updates[mutation]},
                ),
            },
        )
    with pytest.raises(ValueError, match="request|terminal"):
        await collect_semantic_run_telemetry(
            store=_EventStore({execution_id: [request, terminal]}),
            attempts=(_attempt(execution_id),),
            expected_model_id=_MODEL_ID,
            wall_elapsed_seconds=0.1,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("attempt_sequence", 3, "sequence must be contiguous"),
        ("batch_attempt_number", 3, "per-batch attempt numbers must be contiguous"),
    ],
)
async def test_runtime_ledger_rejects_sequence_gaps_after_digest_recomputation(
    field: str,
    value: int,
    message: str,
) -> None:
    attempts = (_attempt("run-order-1", sequence=1), _attempt("run-order-2", sequence=2))
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore(
            {
                "run-order-1": _run_events("run-order-1"),
                "run-order-2": _run_events("run-order-2"),
            },
        ),
        attempts=attempts,
        expected_model_id=_MODEL_ID,
        wall_elapsed_seconds=0.1,
    )
    payload = telemetry.ledger.model_dump(mode="python")
    payload["model_attempts"][1][field] = value
    normalized = tuple(
        type(telemetry.ledger.model_attempts[0]).model_validate(item)
        for item in payload["model_attempts"]
    )
    payload["model_attempts_sha256"] = semantic_model_attempts_sha256(normalized)

    with pytest.raises(ValidationError, match=message):
        SemanticRuntimeLedgerObservation.model_validate(payload)


def test_batch_identity_changes_with_governed_objective_and_criteria() -> None:
    common = {
        "instructions": None,
        "exclusion_criteria": ("Exclude animals",),
        "population_context": "Adults",
        "evidence_types": ("clinical trial",),
        "priority_outcomes": ("survival",),
        "source_key": "pubmed",
        "search_id": "search-1",
        "records": ({"title": "Same record"},),
        "record_indices": (0,),
    }
    first = semantic_governed_context_sha256(
        goal="Assess treatment A",
        inclusion_criteria=("Treatment A",),
        **common,
    )
    second = semantic_governed_context_sha256(
        goal="Assess treatment B",
        inclusion_criteria=("Treatment B",),
        **common,
    )
    references = ("sr_0123456789abcdef0123456789abcdef",)

    assert first != second
    assert semantic_batch_id(
        source_key="pubmed",
        search_id="search-1",
        record_references=references,
        governed_context_sha256=first,
    ) != semantic_batch_id(
        source_key="pubmed",
        search_id="search-1",
        record_references=references,
        governed_context_sha256=second,
    )
