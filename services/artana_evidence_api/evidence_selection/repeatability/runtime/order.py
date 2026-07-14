"""Shared ordering invariant for semantic attempt snapshots."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class SemanticAttemptOrderItem(Protocol):
    """Structural fields required to validate semantic attempt order."""

    execution_id: str
    batch_id: str
    attempt_sequence: int
    batch_attempt_number: int


def validate_semantic_attempt_order(
    attempts: Sequence[SemanticAttemptOrderItem],
) -> None:
    """Require unique executions and contiguous global and per-batch order."""

    execution_ids = tuple(attempt.execution_id for attempt in attempts)
    if len(set(execution_ids)) != len(execution_ids):
        raise ValueError("attempt execution IDs must be unique")
    sequences = tuple(attempt.attempt_sequence for attempt in attempts)
    if sequences != tuple(range(1, len(attempts) + 1)):
        raise ValueError("attempt sequence must be contiguous from one")
    batch_numbers: dict[str, list[int]] = {}
    for attempt in attempts:
        batch_numbers.setdefault(attempt.batch_id, []).append(
            attempt.batch_attempt_number,
        )
    for numbers in batch_numbers.values():
        if tuple(numbers) != tuple(range(1, len(numbers) + 1)):
            raise ValueError("per-batch attempt numbers must be contiguous")


__all__ = ["SemanticAttemptOrderItem", "validate_semantic_attempt_order"]
