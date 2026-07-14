"""Deterministic policy for semantic runtime-ledger observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.evidence_selection.repeatability.contracts import (
    SemanticRuntimeModelAttempt,
    SemanticTelemetryUnavailableReason,
    SemanticUsageProvenance,
)


@dataclass(frozen=True)
class SemanticRuntimeEventAggregate:
    """Usage and latency totals derived from complete immutable attempts."""

    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    model_latency_seconds: float | None
    token_usage_provenance: SemanticUsageProvenance
    cost_usage_provenance: SemanticUsageProvenance
    unavailable_reasons: tuple[SemanticTelemetryUnavailableReason, ...]


def validate_semantic_attempt_order(
    attempts: tuple[SemanticRuntimeModelAttempt, ...],
) -> None:
    """Require one exact, unique, contiguous global and per-batch sequence."""

    execution_ids = tuple(attempt.execution_id for attempt in attempts)
    if len(set(execution_ids)) != len(execution_ids):
        raise ValueError("runtime attempt execution IDs must be unique")
    sequences = tuple(attempt.attempt_sequence for attempt in attempts)
    if sequences != tuple(range(1, len(attempts) + 1)):
        raise ValueError("runtime attempt sequence must be contiguous from one")
    batch_numbers: dict[str, list[int]] = {}
    for attempt in attempts:
        batch_numbers.setdefault(attempt.batch_id, []).append(
            attempt.batch_attempt_number,
        )
    for numbers in batch_numbers.values():
        if tuple(numbers) != tuple(range(1, len(numbers) + 1)):
            raise ValueError("runtime per-batch attempt numbers must be contiguous")


def aggregate_semantic_model_attempts(
    attempts: tuple[SemanticRuntimeModelAttempt, ...],
) -> SemanticRuntimeEventAggregate:
    """Derive usage totals solely from embedded immutable attempt facts."""

    if not attempts:
        return SemanticRuntimeEventAggregate(
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            cost_usd=None,
            model_latency_seconds=None,
            token_usage_provenance="unavailable",
            cost_usage_provenance="unavailable",
            unavailable_reasons=("no_model_attempts",),
        )
    prompt_tokens = _complete_int_sum(
        tuple(attempt.prompt_tokens for attempt in attempts),
    )
    completion_tokens = _complete_int_sum(
        tuple(attempt.completion_tokens for attempt in attempts),
    )
    total_tokens = (
        prompt_tokens + completion_tokens
        if prompt_tokens is not None and completion_tokens is not None
        else None
    )
    cost_values = tuple(attempt.cost_usd for attempt in attempts)
    cost_usd = (
        round(sum(value for value in cost_values if value is not None), 8)
        if all(value is not None for value in cost_values)
        else None
    )
    unavailable_reasons = tuple(
        sorted(
            {
                reason
                for attempt in attempts
                for reason in (
                    attempt.token_usage_unavailable_reason,
                    attempt.cost_usage_unavailable_reason,
                )
                if reason is not None
            },
        ),
    )
    return SemanticRuntimeEventAggregate(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        model_latency_seconds=(
            round(
                sum(
                    attempt.elapsed_ms
                    for attempt in attempts
                    if attempt.elapsed_ms is not None
                )
                / 1000.0,
                6,
            )
            if any(attempt.elapsed_ms is not None for attempt in attempts)
            else None
        ),
        token_usage_provenance=(
            "artana_model_terminal" if total_tokens is not None else "unavailable"
        ),
        cost_usage_provenance=(
            "artana_model_terminal" if cost_usd is not None else "unavailable"
        ),
        unavailable_reasons=unavailable_reasons,
    )


def semantic_model_attempts_sha256(
    attempts: tuple[SemanticRuntimeModelAttempt, ...],
) -> str:
    """Hash the complete normalized model-attempt snapshot."""

    payload = json.dumps(
        [attempt.model_dump(mode="json") for attempt in attempts],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def semantic_ledger_status(
    attempts: tuple[SemanticRuntimeModelAttempt, ...],
) -> Literal["available", "partial", "unavailable"]:
    """Derive availability from event coverage and provider-owned usage."""

    if not attempts or not any(
        attempt.terminal_outcome is not None for attempt in attempts
    ):
        return "unavailable"
    aggregate = aggregate_semantic_model_attempts(attempts)
    complete = all(
        value is not None
        for value in (
            aggregate.prompt_tokens,
            aggregate.completion_tokens,
            aggregate.total_tokens,
            aggregate.cost_usd,
            aggregate.model_latency_seconds,
        )
    ) and all(attempt.terminal_outcome is not None for attempt in attempts)
    return "available" if complete else "partial"


def _complete_int_sum(values: tuple[int | None, ...]) -> int | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


__all__ = [
    "SemanticRuntimeEventAggregate",
    "aggregate_semantic_model_attempts",
    "semantic_ledger_status",
    "semantic_model_attempts_sha256",
    "validate_semantic_attempt_order",
]
