"""Collect semantic attempt telemetry from the Artana runtime ledger."""

from __future__ import annotations

from typing import Protocol

from artana_evidence_api.evidence_selection.semantic.attempts import (
    SemanticModelAttemptContext,
)

from .contracts import (
    SemanticRunTelemetry,
    SemanticRuntimeLedgerObservation,
    SemanticRuntimeModelAttempt,
    SemanticWallClockObservation,
    aggregate_semantic_model_attempts,
    semantic_ledger_status,
    semantic_model_attempts_sha256,
)
from .telemetry_normalization import (
    missing_semantic_terminal_attempt,
    normalize_semantic_model_id,
    normalize_semantic_terminal_attempt,
)


class SemanticTelemetryReader(Protocol):
    """Minimal event-ledger boundary required for telemetry collection."""

    async def get_events_for_run(self, run_id: str) -> list[object]: ...


class SemanticTelemetryStore(SemanticTelemetryReader, Protocol):
    """Request-local telemetry store with an explicit async lifecycle."""

    async def close(self) -> None: ...


async def collect_semantic_run_telemetry(
    *,
    store: SemanticTelemetryReader,
    attempts: tuple[SemanticModelAttemptContext, ...],
    expected_model_id: str,
    wall_elapsed_seconds: float,
) -> SemanticRunTelemetry:
    """Join every semantic attempt to Artana facts without estimating usage."""

    normalized_expected_model_id = normalize_semantic_model_id(expected_model_id)
    model_attempts = await _collect_model_attempts(
        store=store,
        attempts=attempts,
        expected_model_id=normalized_expected_model_id,
    )
    aggregate = aggregate_semantic_model_attempts(model_attempts)
    execution_ids = tuple(attempt.execution_id for attempt in attempts)
    ledger = SemanticRuntimeLedgerObservation(
        status=semantic_ledger_status(model_attempts),
        expected_model_id=normalized_expected_model_id,
        execution_ids=execution_ids,
        model_attempt_count=len(model_attempts),
        model_terminal_count=sum(
            attempt.terminal_outcome is not None for attempt in model_attempts
        ),
        model_attempts=model_attempts,
        model_attempts_sha256=semantic_model_attempts_sha256(model_attempts),
        prompt_tokens=aggregate.prompt_tokens,
        completion_tokens=aggregate.completion_tokens,
        total_tokens=aggregate.total_tokens,
        cost_usd=aggregate.cost_usd,
        model_latency_seconds=aggregate.model_latency_seconds,
        token_usage_provenance=aggregate.token_usage_provenance,
        cost_usage_provenance=aggregate.cost_usage_provenance,
        unavailable_reasons=aggregate.unavailable_reasons,
    )
    return SemanticRunTelemetry(
        ledger=ledger,
        wall_clock=SemanticWallClockObservation(
            execution_ids=execution_ids,
            elapsed_seconds=wall_elapsed_seconds,
        ),
    )


async def _collect_model_attempts(
    *,
    store: SemanticTelemetryReader,
    attempts: tuple[SemanticModelAttemptContext, ...],
    expected_model_id: str,
) -> tuple[SemanticRuntimeModelAttempt, ...]:
    from artana.events import EventType, ModelTerminalPayload

    normalized: list[SemanticRuntimeModelAttempt] = []
    for attempt in attempts:
        events = await store.get_events_for_run(attempt.execution_id)
        terminals = [
            event
            for event in events
            if getattr(event, "event_type", None)
            in {EventType.MODEL_TERMINAL, EventType.MODEL_TERMINAL.value}
            and isinstance(getattr(event, "payload", None), ModelTerminalPayload)
        ]
        if len(terminals) > 1:
            raise ValueError("semantic execution contains multiple terminal events")
        if not terminals:
            normalized.append(
                missing_semantic_terminal_attempt(
                    attempt=attempt,
                    expected_model_id=expected_model_id,
                ),
            )
            continue
        normalized.append(
            normalize_semantic_terminal_attempt(
                attempt=attempt,
                event=terminals[0],
                expected_model_id=expected_model_id,
            ),
        )
    return tuple(normalized)


__all__ = [
    "SemanticTelemetryReader",
    "SemanticTelemetryStore",
    "collect_semantic_run_telemetry",
]
