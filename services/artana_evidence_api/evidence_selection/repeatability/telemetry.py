"""Runtime-ledger telemetry collection for semantic selector evaluations."""

from __future__ import annotations

from contextlib import suppress
from typing import Protocol

from artana_evidence_api.evidence_selection.repeatability.contracts import (
    SemanticRunTelemetry,
    SemanticRuntimeLedgerObservation,
    SemanticRuntimeTerminalEvent,
    SemanticTerminalCostDerivation,
    SemanticWallClockObservation,
    aggregate_semantic_terminal_events,
    semantic_terminal_events_sha256,
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
    execution_ids: tuple[str, ...],
    expected_model_id: str,
    wall_elapsed_seconds: float,
) -> SemanticRunTelemetry:
    """Collect provider usage without allowing it to influence semantic decisions."""

    ledger = await _collect_ledger_observation(
        store=store,
        execution_ids=execution_ids,
        expected_model_id=expected_model_id,
    )
    return SemanticRunTelemetry(
        ledger=ledger,
        wall_clock=SemanticWallClockObservation(
            execution_ids=execution_ids,
            elapsed_seconds=wall_elapsed_seconds,
        ),
    )


async def _collect_ledger_observation(
    *,
    store: SemanticTelemetryReader,
    execution_ids: tuple[str, ...],
    expected_model_id: str,
) -> SemanticRuntimeLedgerObservation:
    if not execution_ids:
        return _unavailable_observation(
            execution_ids=execution_ids,
            expected_model_id=expected_model_id,
        )

    from artana.events import EventType, ModelTerminalPayload

    terminal_events: list[SemanticRuntimeTerminalEvent] = []
    execution_coverage = 0
    normalized_expected_model_id = _normalize_cost_model_id(expected_model_id)
    for execution_id in execution_ids:
        events = await store.get_events_for_run(execution_id)
        matching_event_count = 0
        for event in events:
            event_type = getattr(event, "event_type", None)
            payload = getattr(event, "payload", None)
            if event_type not in {EventType.MODEL_TERMINAL, EventType.MODEL_TERMINAL.value}:
                continue
            if isinstance(payload, ModelTerminalPayload):
                normalized_model_id = _normalize_cost_model_id(payload.model)
                if normalized_model_id != normalized_expected_model_id:
                    raise ValueError(
                        "runtime ledger terminal event does not match the frozen model",
                    )
                matching_event_count += 1
                cost_usd, cost_derivation = _payload_cost(payload)
                terminal_events.append(
                    SemanticRuntimeTerminalEvent(
                        execution_id=execution_id,
                        outcome=_string_value(payload.outcome),
                        model_id=normalized_model_id,
                        model_cycle_id=payload.model_cycle_id,
                        source_model_requested_event_id=(
                            payload.source_model_requested_event_id
                        ),
                        elapsed_ms=payload.elapsed_ms,
                        prompt_tokens=payload.prompt_tokens,
                        completion_tokens=payload.completion_tokens,
                        cost_usd=cost_usd,
                        cost_derivation=cost_derivation,
                    ),
                )
        if matching_event_count:
            execution_coverage += 1
    if not terminal_events:
        return _unavailable_observation(
            execution_ids=execution_ids,
            expected_model_id=expected_model_id,
        )

    normalized_events = tuple(terminal_events)
    aggregate = aggregate_semantic_terminal_events(normalized_events)
    execution_complete = execution_coverage == len(execution_ids)
    complete = execution_complete and all(
        value is not None
        for value in (
            aggregate.prompt_tokens,
            aggregate.completion_tokens,
            aggregate.total_tokens,
            aggregate.cost_usd,
            aggregate.model_latency_seconds,
        )
    )
    return SemanticRuntimeLedgerObservation(
        status="available" if complete else "partial",
        expected_model_id=normalized_expected_model_id,
        execution_ids=execution_ids,
        model_terminal_count=len(normalized_events),
        terminal_events=normalized_events,
        terminal_events_sha256=semantic_terminal_events_sha256(normalized_events),
        prompt_tokens=aggregate.prompt_tokens,
        completion_tokens=aggregate.completion_tokens,
        total_tokens=aggregate.total_tokens,
        cost_usd=aggregate.cost_usd,
        model_latency_seconds=aggregate.model_latency_seconds,
        cost_derivation=aggregate.cost_derivation,
    )


def _payload_cost(
    payload: object,
) -> tuple[float | None, SemanticTerminalCostDerivation]:
    reported = getattr(payload, "cost_usd", None)
    if isinstance(reported, int | float) and not isinstance(reported, bool):
        normalized = round(float(reported), 8)
        if normalized > 0.0:
            return normalized, "provider_reported"
        derived = _derived_cost(payload)
        if derived is not None:
            return derived, "token_pricing"
        return normalized, "provider_reported"
    derived = _derived_cost(payload)
    if derived is not None:
        return derived, "token_pricing"
    return None, "unavailable"


def _derived_cost(payload: object) -> float | None:
    model_id = getattr(payload, "model", None)
    prompt_tokens = getattr(payload, "prompt_tokens", None)
    completion_tokens = getattr(payload, "completion_tokens", None)
    if not isinstance(model_id, str):
        return None
    if not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool):
        return None
    if not isinstance(completion_tokens, int) or isinstance(completion_tokens, bool):
        return None
    normalized_model_id = _normalize_cost_model_id(model_id)
    if ":" in normalized_model_id and not normalized_model_id.startswith("openai:"):
        return None
    from artana_evidence_api.llm_costs import calculate_openai_usage_cost_usd

    with suppress(Exception):
        calculated = calculate_openai_usage_cost_usd(
            model_id=normalized_model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return round(calculated, 8)
    return None


def _normalize_cost_model_id(model_id: str) -> str:
    normalized = model_id.strip()
    if ":" in normalized:
        return normalized
    if "/" in normalized:
        provider, model_name = normalized.split("/", 1)
        if provider.strip() and model_name.strip():
            return f"{provider.strip()}:{model_name.strip()}"
    return normalized


def _unavailable_observation(
    *,
    execution_ids: tuple[str, ...],
    expected_model_id: str,
) -> SemanticRuntimeLedgerObservation:
    terminal_events: tuple[SemanticRuntimeTerminalEvent, ...] = ()
    return SemanticRuntimeLedgerObservation(
        status="unavailable",
        expected_model_id=_normalize_cost_model_id(expected_model_id),
        execution_ids=execution_ids,
        model_terminal_count=0,
        terminal_events=terminal_events,
        terminal_events_sha256=semantic_terminal_events_sha256(terminal_events),
        cost_derivation="unavailable",
    )


def _string_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


__all__ = [
    "SemanticTelemetryReader",
    "SemanticTelemetryStore",
    "collect_semantic_run_telemetry",
]
