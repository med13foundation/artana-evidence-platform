"""Source artifact for the exact semantic executions attempted by one run."""

from __future__ import annotations

from artana_evidence_api.evidence_selection.repeatability.contracts import (
    SemanticRuntimeModelAttempt,
)
from artana_evidence_api.evidence_selection.semantic.attempts import (
    SemanticModelAttemptContext,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SemanticAttemptedExecutionManifest(BaseModel):
    """Immutable recorder snapshot written before ledger normalization."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: str = Field(
        default="evidence_selection_semantic_attempt_manifest.v1",
        pattern=r"^evidence_selection_semantic_attempt_manifest\.v1$",
    )
    model_id: str = Field(min_length=1)
    attempts: tuple[SemanticModelAttemptContext, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _attempt_order_is_exact(self) -> SemanticAttemptedExecutionManifest:
        _validate_manifest_order(self.attempts)
        return self


def validate_attempt_manifest_matches_ledger(
    *,
    manifest: SemanticAttemptedExecutionManifest,
    attempts: tuple[SemanticRuntimeModelAttempt, ...],
) -> None:
    """Require exact attempted-execution equality, not subset inclusion."""

    if manifest.model_id != (attempts[0].model_id if attempts else None):
        raise ValueError("attempt manifest model does not match runtime ledger")
    declared = tuple(_runtime_attempt_context(attempt) for attempt in attempts)
    if manifest.attempts != declared:
        raise ValueError("attempt manifest does not exactly match runtime ledger")


def _validate_manifest_order(
    attempts: tuple[SemanticModelAttemptContext, ...],
) -> None:
    execution_ids = tuple(attempt.execution_id for attempt in attempts)
    if len(set(execution_ids)) != len(execution_ids):
        raise ValueError("attempt manifest execution IDs must be unique")
    sequences = tuple(attempt.attempt_sequence for attempt in attempts)
    if sequences != tuple(range(1, len(attempts) + 1)):
        raise ValueError("attempt manifest sequence must be contiguous from one")
    per_batch: dict[str, list[int]] = {}
    for attempt in attempts:
        per_batch.setdefault(attempt.batch_id, []).append(
            attempt.batch_attempt_number,
        )
    for numbers in per_batch.values():
        if tuple(numbers) != tuple(range(1, len(numbers) + 1)):
            raise ValueError("attempt manifest per-batch numbers must be contiguous")


def _runtime_attempt_context(
    attempt: SemanticRuntimeModelAttempt,
) -> SemanticModelAttemptContext:
    local_failure = None
    if attempt.status == "rejected":
        from artana_evidence_api.evidence_selection.semantic.attempts import (
            SemanticLocalValidationFailure,
        )

        local_failure = SemanticLocalValidationFailure.model_validate(
            {"stage": attempt.failure_stage, "cause": attempt.failure_cause},
        )
    return SemanticModelAttemptContext(
        execution_id=attempt.execution_id,
        batch_id=attempt.batch_id,
        governed_context_sha256=attempt.governed_context_sha256,
        attempt_sequence=attempt.attempt_sequence,
        batch_attempt_number=attempt.batch_attempt_number,
        step_key=attempt.step_key,
        source_key=attempt.source_key,
        search_id=attempt.search_id,
        record_references=attempt.record_references,
        local_failure=local_failure,
    )


__all__ = [
    "SemanticAttemptedExecutionManifest",
    "validate_attempt_manifest_matches_ledger",
]
