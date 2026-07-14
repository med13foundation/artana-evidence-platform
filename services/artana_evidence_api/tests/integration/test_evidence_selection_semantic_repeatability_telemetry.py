"""Postgres-backed runtime-ledger proof for semantic model comparisons."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana.events import EventType, ModelTerminalPayload
from artana_evidence_api.evidence_selection.repeatability.telemetry import (
    collect_semantic_run_telemetry,
)
from artana_evidence_api.runtime import create_artana_postgres_store


@pytest.mark.asyncio
async def test_runtime_telemetry_reads_real_artana_postgres_terminal_events() -> None:
    store = create_artana_postgres_store()
    execution_id = f"semantic-repeatability-test:{uuid4()}"
    try:
        await store.append_event(
            run_id=execution_id,
            tenant_id="semantic_repeatability_test",
            event_type=EventType.MODEL_TERMINAL,
            payload=ModelTerminalPayload(
                outcome="completed",
                model="openai:gpt-5.4-mini",
                model_cycle_id=f"cycle-{execution_id}",
                source_model_requested_event_id=f"request-{execution_id}",
                elapsed_ms=125,
                prompt_tokens=80,
                completion_tokens=20,
                cost_usd=0.001,
            ),
        )

        telemetry = await collect_semantic_run_telemetry(
            store=store,
            execution_ids=(execution_id,),
            expected_model_id="openai:gpt-5.4-mini",
            wall_elapsed_seconds=0.2,
        )
    finally:
        await store.close()

    assert telemetry.ledger.status == "available"
    assert telemetry.ledger.total_tokens == 100
    assert telemetry.ledger.cost_usd == pytest.approx(0.001)
    assert telemetry.ledger.model_latency_seconds == pytest.approx(0.125)
    assert telemetry.ledger.terminal_events[0].execution_id == execution_id
    assert telemetry.ledger.terminal_events[0].model_id == "openai:gpt-5.4-mini"
