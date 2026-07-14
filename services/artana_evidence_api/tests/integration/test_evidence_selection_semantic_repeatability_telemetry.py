"""Postgres-backed failed-attempt telemetry proof for semantic comparisons."""

from __future__ import annotations

from typing import Protocol, cast
from uuid import uuid4

import pytest
from artana.agent import SingleStepModelClient
from artana.events import EventType, ModelRequestedPayload, ModelTerminalPayload
from artana.kernel import ArtanaKernel
from artana.models import TenantContext
from artana.ports.model import ModelPort
from artana_evidence_api.evidence_selection.repeatability.telemetry import (
    collect_semantic_run_telemetry,
)
from artana_evidence_api.evidence_selection.semantic.attempts import (
    SemanticAttemptRecorder,
)
from artana_evidence_api.evidence_selection.semantic.contracts import (
    EvidenceSelectionSemanticBatchContract,
)
from artana_evidence_api.runtime import create_artana_postgres_store
from artana_evidence_api.step_helpers import run_single_step_with_policy
from pydantic import BaseModel, ValidationError

_MODEL_ID = "openai:gpt-5.4-mini"
_STEP_KEY = "evidence_selection.semantic_selector.v2"
_RECORD_REFERENCE = "sr_0123456789abcdef0123456789abcdef"


class _ModelRequestLike(Protocol):
    output_schema: type[BaseModel]


class _SchemaInvalidModelPort:
    async def complete(self, request: object) -> object:
        output_schema = cast("_ModelRequestLike", request).output_schema
        output_schema.model_validate(
            {
                "schema_version": "evidence_selection_semantic_agent.v2",
                "reasoning_summary": "Missing required assessments.",
                "assessments": [],
            },
        )
        raise AssertionError("invalid schema unexpectedly passed validation")


@pytest.mark.asyncio
async def test_postgres_failure_path_retains_schema_stage_and_association() -> None:
    store = create_artana_postgres_store()
    execution_id = f"semantic-failure-telemetry-test:{uuid4()}"
    recorder = _attempt_recorder(execution_id)
    kernel = ArtanaKernel(
        store=store,
        model_port=cast("ModelPort", _SchemaInvalidModelPort()),
    )
    try:
        client = SingleStepModelClient(kernel=kernel)
        with pytest.raises(ValidationError):
            await run_single_step_with_policy(
                client,
                run_id=execution_id,
                tenant=TenantContext(
                    tenant_id="semantic_failure_telemetry_test",
                    capabilities=frozenset(),
                    budget_usd_limit=1.0,
                ),
                model=_MODEL_ID,
                prompt="Return an invalid semantic batch for telemetry testing.",
                output_schema=EvidenceSelectionSemanticBatchContract,
                schema_id="evidence_selection.semantic.v2",
                step_key=_STEP_KEY,
                replay_policy="strict",
            )

        telemetry = await collect_semantic_run_telemetry(
            store=store,
            attempts=recorder.attempts(),
            expected_model_id=_MODEL_ID,
            wall_elapsed_seconds=0.2,
        )
    finally:
        await kernel.close()
        await store.close()

    attempt = telemetry.ledger.model_attempts[0]
    assert attempt.status == "failed"
    assert attempt.failure_stage == "output_schema_validation"
    assert attempt.failure_cause == "schema_contract_rejected"
    assert attempt.execution_id == execution_id
    assert attempt.batch_id == recorder.attempts()[0].batch_id
    assert attempt.source_model_requested_event_id is not None
    assert attempt.model_requested_event_seq is not None
    assert attempt.model_requested_event_hash is not None
    assert attempt.prompt_tokens is None
    assert attempt.completion_tokens is None
    assert attempt.cost_usd is None
    assert (
        attempt.token_usage_unavailable_reason
        == "artana_exception_did_not_preserve_provider_usage"
    )


@pytest.mark.asyncio
async def test_postgres_terminal_usage_is_copied_without_estimation() -> None:
    store = create_artana_postgres_store()
    execution_id = f"semantic-complete-telemetry-test:{uuid4()}"
    recorder = _attempt_recorder(execution_id)
    try:
        request = await store.append_event(
            run_id=execution_id,
            tenant_id="semantic_complete_telemetry_test",
            event_type=EventType.MODEL_REQUESTED,
            payload=ModelRequestedPayload(
                model=_MODEL_ID,
                prompt="Return a complete semantic batch.",
                messages=(),
                step_key=_STEP_KEY,
                model_cycle_id=f"cycle-{execution_id}",
            ),
        )
        await store.append_event(
            run_id=execution_id,
            tenant_id="semantic_complete_telemetry_test",
            event_type=EventType.MODEL_TERMINAL,
            payload=ModelTerminalPayload(
                outcome="completed",
                model=_MODEL_ID,
                model_cycle_id=f"cycle-{execution_id}",
                source_model_requested_event_id=request.event_id,
                step_key=_STEP_KEY,
                elapsed_ms=125,
                prompt_tokens=80,
                completion_tokens=20,
                cost_usd=0.001,
            ),
        )
        telemetry = await collect_semantic_run_telemetry(
            store=store,
            attempts=recorder.attempts(),
            expected_model_id=_MODEL_ID,
            wall_elapsed_seconds=0.2,
        )
    finally:
        await store.close()

    assert telemetry.ledger.status == "available"
    assert telemetry.ledger.total_tokens == 100
    assert telemetry.ledger.cost_usd == pytest.approx(0.001)
    assert telemetry.ledger.token_usage_provenance == "artana_model_terminal"
    assert telemetry.ledger.cost_usage_provenance == "artana_model_terminal"


def _attempt_recorder(execution_id: str) -> SemanticAttemptRecorder:
    recorder = SemanticAttemptRecorder(step_key=_STEP_KEY)
    recorder.start_attempt(
        execution_id=execution_id,
        source_key="pubmed",
        search_id="search-1",
        record_references=(_RECORD_REFERENCE,),
        governed_context_sha256="c" * 64,
    )
    return recorder
