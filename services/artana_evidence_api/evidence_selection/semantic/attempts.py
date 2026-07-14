"""Deterministic service-owned identity for semantic model attempts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Literal, Protocol, runtime_checkable

from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, model_validator

SemanticLocalFailureStage = Literal[
    "semantic_batch_validation",
    "evidence_reference_validation",
    "service_run_identity_validation",
]
SemanticLocalFailureCause = Literal[
    "record_coverage_mismatch",
    "evidence_reference_invalid",
    "agent_run_identity_missing",
    "unexpected_local_validation_error",
]


class SemanticLocalValidationFailure(BaseModel):
    """Categorical reason a completed model response was rejected locally."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    stage: SemanticLocalFailureStage
    cause: SemanticLocalFailureCause


class SemanticModelAttemptContext(BaseModel):
    """Stable semantic-batch association for one service model execution."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    execution_id: str = Field(min_length=1)
    batch_id: str = Field(pattern=r"^semantic_batch_[a-f0-9]{32}$")
    governed_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt_sequence: int = Field(ge=1)
    batch_attempt_number: int = Field(ge=1)
    step_key: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    search_id: str = Field(min_length=1)
    record_references: tuple[str, ...] = Field(min_length=1)
    local_failure: SemanticLocalValidationFailure | None = None

    @model_validator(mode="after")
    def _record_references_must_be_unique(self) -> SemanticModelAttemptContext:
        if len(set(self.record_references)) != len(self.record_references):
            raise ValueError("semantic attempt record references must be unique")
        return self


@runtime_checkable
class SemanticAttemptReporter(Protocol):
    """Boundary exposed by runners that retain every semantic model attempt."""

    def model_attempts(self) -> tuple[SemanticModelAttemptContext, ...]: ...


@runtime_checkable
class SemanticLocalFailureRecorder(Protocol):
    """Boundary used by local validation to reject the latest model attempt."""

    def record_local_validation_failure(
        self,
        failure: SemanticLocalValidationFailure,
    ) -> None: ...


class SemanticAttemptRecorder:
    """Mutable request-local recorder that emits immutable attempt contexts."""

    def __init__(self, *, step_key: str) -> None:
        self._step_key = step_key
        self._attempts: list[SemanticModelAttemptContext] = []
        self._batch_counts: Counter[str] = Counter()

    def start_attempt(
        self,
        *,
        execution_id: str,
        source_key: str,
        search_id: str,
        record_references: tuple[str, ...],
        governed_context_sha256: str,
    ) -> SemanticModelAttemptContext:
        """Record an attempt before any runtime component can fail."""

        batch_id = semantic_batch_id(
            source_key=source_key,
            search_id=search_id,
            record_references=record_references,
            governed_context_sha256=governed_context_sha256,
        )
        self._batch_counts[batch_id] += 1
        attempt = SemanticModelAttemptContext(
            execution_id=execution_id,
            batch_id=batch_id,
            governed_context_sha256=governed_context_sha256,
            attempt_sequence=len(self._attempts) + 1,
            batch_attempt_number=self._batch_counts[batch_id],
            step_key=self._step_key,
            source_key=source_key,
            search_id=search_id,
            record_references=record_references,
        )
        self._attempts.append(attempt)
        return attempt

    def record_local_validation_failure(
        self,
        failure: SemanticLocalValidationFailure,
    ) -> None:
        """Attach a categorical local rejection to the latest attempt."""

        if not self._attempts:
            raise RuntimeError("cannot reject a semantic attempt before it starts")
        latest = self._attempts[-1]
        if latest.local_failure is not None:
            raise RuntimeError("semantic attempt already has a local failure")
        self._attempts[-1] = latest.model_copy(update={"local_failure": failure})

    def attempts(self) -> tuple[SemanticModelAttemptContext, ...]:
        """Return immutable attempts in execution order."""

        return tuple(self._attempts)

    def execution_ids(self) -> tuple[str, ...]:
        """Derive execution identity from the recorder's immutable attempt order."""

        return tuple(attempt.execution_id for attempt in self._attempts)


def semantic_batch_id(
    *,
    source_key: str,
    search_id: str,
    record_references: tuple[str, ...],
    governed_context_sha256: str,
) -> str:
    """Hash the source-owned batch identity without storing prompt text."""

    payload = json.dumps(
        {
            "record_references": record_references,
            "search_id": search_id,
            "source_key": source_key,
            "governed_context_sha256": governed_context_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"semantic_batch_{hashlib.sha256(payload).hexdigest()[:32]}"


def semantic_governed_context_sha256(
    *,
    goal: str,
    instructions: str | None,
    inclusion_criteria: tuple[str, ...],
    exclusion_criteria: tuple[str, ...],
    population_context: str | None,
    evidence_types: tuple[str, ...],
    priority_outcomes: tuple[str, ...],
    source_key: str,
    search_id: str,
    records: tuple[JSONObject, ...],
    record_indices: tuple[int, ...],
) -> str:
    """Fingerprint every governed input that can change a semantic judgment."""

    payload = json.dumps(
        {
            "evidence_types": evidence_types,
            "exclusion_criteria": exclusion_criteria,
            "goal": goal,
            "inclusion_criteria": inclusion_criteria,
            "instructions": instructions,
            "population_context": population_context,
            "priority_outcomes": priority_outcomes,
            "record_indices": record_indices,
            "records": records,
            "search_id": search_id,
            "source_key": source_key,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "SemanticAttemptRecorder",
    "SemanticAttemptReporter",
    "SemanticLocalFailureCause",
    "SemanticLocalFailureRecorder",
    "SemanticLocalFailureStage",
    "SemanticLocalValidationFailure",
    "SemanticModelAttemptContext",
    "semantic_batch_id",
    "semantic_governed_context_sha256",
]
