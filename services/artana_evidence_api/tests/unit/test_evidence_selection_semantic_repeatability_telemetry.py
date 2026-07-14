"""Runtime-ledger telemetry regressions for semantic model comparison."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from artana.events import EventType, ModelTerminalPayload
from artana_evidence_api.evidence_selection.repeatability.contracts import (
    SemanticRuntimeLedgerObservation,
)
from artana_evidence_api.evidence_selection.repeatability.telemetry import (
    collect_semantic_run_telemetry,
)
from pydantic import ValidationError


class _EventStore:
    def __init__(
        self,
        *,
        missing_execution_id: str | None = None,
        model_id: str = "openai:gpt-5.4-mini",
    ) -> None:
        self._missing_execution_id = missing_execution_id
        self._model_id = model_id

    async def get_events_for_run(self, execution_id: str) -> list[object]:
        if execution_id == self._missing_execution_id:
            return []
        payload = ModelTerminalPayload(
            outcome="completed",
            model=self._model_id,
            model_cycle_id=f"cycle-{execution_id}",
            source_model_requested_event_id=f"request-{execution_id}",
            elapsed_ms=250,
            prompt_tokens=100,
            completion_tokens=20,
            cost_usd=0.001,
        )
        return [
            SimpleNamespace(
                event_type=EventType.MODEL_TERMINAL,
                payload=payload,
            ),
        ]


@pytest.mark.asyncio
async def test_runtime_telemetry_binds_complete_ledger_observations() -> None:
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore(),
        execution_ids=("run-1", "run-2"),
        expected_model_id="openai:gpt-5.4-mini",
        wall_elapsed_seconds=0.8,
    )

    assert telemetry.ledger.status == "available"
    assert telemetry.ledger.execution_ids == ("run-1", "run-2")
    assert telemetry.ledger.prompt_tokens == 200
    assert telemetry.ledger.completion_tokens == 40
    assert telemetry.ledger.total_tokens == 240
    assert telemetry.ledger.cost_usd == pytest.approx(0.002)
    assert telemetry.ledger.model_latency_seconds == pytest.approx(0.5)
    assert telemetry.ledger.cost_derivation == "provider_reported"
    assert len(telemetry.ledger.terminal_events) == 2
    assert telemetry.ledger.terminal_events[0].execution_id == "run-1"
    assert telemetry.ledger.terminal_events[0].cost_derivation == "provider_reported"
    assert telemetry.wall_clock.elapsed_seconds == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_runtime_telemetry_is_partial_when_one_execution_is_missing() -> None:
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore(missing_execution_id="run-2"),
        execution_ids=("run-1", "run-2"),
        expected_model_id="openai:gpt-5.4-mini",
        wall_elapsed_seconds=0.8,
    )

    assert telemetry.ledger.status == "partial"
    assert telemetry.ledger.model_terminal_count == 1
    assert telemetry.ledger.execution_ids == ("run-1", "run-2")


@pytest.mark.asyncio
async def test_runtime_telemetry_is_explicitly_unavailable_without_run_ids() -> None:
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore(),
        execution_ids=(),
        expected_model_id="openai:gpt-5.4-mini",
        wall_elapsed_seconds=0.1,
    )

    assert telemetry.ledger.status == "unavailable"
    assert telemetry.ledger.total_tokens is None
    assert telemetry.ledger.cost_usd is None


@pytest.mark.asyncio
async def test_runtime_telemetry_rejects_wrong_model_terminal_event() -> None:
    with pytest.raises(ValueError, match="does not match the frozen model"):
        await collect_semantic_run_telemetry(
            store=_EventStore(model_id="openai:gpt-5"),
            execution_ids=("run-1",),
            expected_model_id="openai:gpt-5.4-mini",
            wall_elapsed_seconds=0.1,
        )


@pytest.mark.asyncio
async def test_runtime_telemetry_snapshot_digest_detects_tampering() -> None:
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore(),
        execution_ids=("run-1",),
        expected_model_id="openai:gpt-5.4-mini",
        wall_elapsed_seconds=0.1,
    )
    payload = telemetry.ledger.model_dump(mode="json")
    payload["terminal_events"][0]["prompt_tokens"] = 999

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
        ("cost_derivation", "token_pricing"),
    ],
)
async def test_runtime_telemetry_rejects_forged_aggregates(
    field: str,
    forged_value: object,
) -> None:
    telemetry = await collect_semantic_run_telemetry(
        store=_EventStore(),
        execution_ids=("run-1",),
        expected_model_id="openai:gpt-5.4-mini",
        wall_elapsed_seconds=0.1,
    )
    payload = telemetry.ledger.model_dump(mode="json")
    payload[field] = forged_value

    with pytest.raises(ValidationError, match="aggregate does not match"):
        SemanticRuntimeLedgerObservation.model_validate_json(json.dumps(payload))
