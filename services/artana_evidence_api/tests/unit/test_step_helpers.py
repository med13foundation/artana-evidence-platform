"""Unit tests for service-local Artana step helpers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import pytest
from artana_evidence_api.step_helpers import (
    get_step_execution_health,
    reset_step_execution_health,
    run_single_step_with_policy,
)


@dataclass(frozen=True)
class _FakeStepResult:
    output: object


class _ReplayFailureStepClient:
    async def step(
        self,
        *,
        run_id: str,
        tenant: object,
        model: str,
        prompt: str,
        output_schema: type[object],
        step_key: str,
        replay_policy: str,
        context_version: object | None = None,
    ) -> _FakeStepResult:
        del run_id, tenant, model, prompt, output_schema, step_key, replay_policy
        del context_version
        raise RuntimeError(
            "Replayed model terminal outcome='failed' "
            "category='internal' class='ValidationError' reason='internal'.",
        )


class _GenericFailureStepClient:
    async def step(
        self,
        *,
        run_id: str,
        tenant: object,
        model: str,
        prompt: str,
        output_schema: type[object],
        step_key: str,
        replay_policy: str,
        context_version: object | None = None,
    ) -> _FakeStepResult:
        del run_id, tenant, model, prompt, output_schema, step_key, replay_policy
        del context_version
        raise RuntimeError("synthetic failure")


def test_run_single_step_with_policy_logs_replayed_terminal_without_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reset_step_execution_health()

    with (
        caplog.at_level(logging.INFO, logger="artana_evidence_api.step_helpers"),
        pytest.raises(RuntimeError, match="Replayed model terminal outcome="),
    ):
        asyncio.run(
            run_single_step_with_policy(
                _ReplayFailureStepClient(),
                run_id="run-replay",
                tenant=object(),
                model="openai/gpt-5.4-mini",
                prompt="return ok",
                output_schema=dict,
                step_key="document_extraction.proposal_review.v1",
                replay_policy="fork_on_drift",
            ),
        )

    replay_records = [
        record
        for record in caplog.records
        if record.message
        == "Artana model step replay surfaced historical terminal failure"
    ]
    assert replay_records
    replay_record = replay_records[-1]
    assert replay_record.exc_info is None
    assert getattr(replay_record, "artana_replayed_terminal", None) is True
    health = get_step_execution_health()
    assert health.consecutive_failures == 0
    assert health.last_error is None
    assert health.status == "healthy"
    reset_step_execution_health()


def test_run_single_step_with_policy_logs_generic_failures_with_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reset_step_execution_health()

    with (
        caplog.at_level(logging.WARNING, logger="artana_evidence_api.step_helpers"),
        pytest.raises(RuntimeError, match="synthetic failure"),
    ):
        asyncio.run(
            run_single_step_with_policy(
                _GenericFailureStepClient(),
                run_id="run-generic",
                tenant=object(),
                model="openai/gpt-5.4-mini",
                prompt="return ok",
                output_schema=dict,
                step_key="document_extraction.proposal_review.v1",
                replay_policy="fork_on_drift",
            ),
        )

    failure_records = [
        record
        for record in caplog.records
        if record.message == "Artana model step failed"
    ]
    assert failure_records
    failure_record = failure_records[-1]
    assert failure_record.exc_info is not None
    assert getattr(failure_record, "artana_replayed_terminal", None) is None
    health = get_step_execution_health()
    assert health.consecutive_failures == 1
    assert health.last_error == "synthetic failure"
    reset_step_execution_health()
