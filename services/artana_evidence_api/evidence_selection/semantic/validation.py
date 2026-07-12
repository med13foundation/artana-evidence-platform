"""Grounding validation and bounded retries for semantic agent batches."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.evidence_selection.semantic.contracts import (
    EvidenceSelectionSemanticBatchContract,
    EvidenceSelectionSemanticCandidateAssessment,
)
from artana_evidence_api.evidence_selection.semantic.model import (
    EvidenceSelectionSemanticContext,
    EvidenceSelectionSemanticModelRunner,
    SemanticSelectionAgentUnavailableError,
)
from artana_evidence_api.types.common import JSONObject, JSONValue

_MAX_AGENT_ATTEMPTS = 2


@dataclass(frozen=True, slots=True)
class ValidatedSemanticAssessmentBatch:
    """One complete grounded contract and its indexed assessments."""

    contract: EvidenceSelectionSemanticBatchContract
    assessments: dict[int, EvidenceSelectionSemanticCandidateAssessment]
    attempt_count: int


async def assess_validated_semantic_batch(
    *,
    runner: EvidenceSelectionSemanticModelRunner,
    context: EvidenceSelectionSemanticContext,
) -> ValidatedSemanticAssessmentBatch:
    """Retry the agent once, then fail closed if output remains invalid."""

    last_error: Exception | None = None
    for attempt_count in range(1, _MAX_AGENT_ATTEMPTS + 1):
        try:
            contract = await runner.assess(context=context)
            assessments = validate_semantic_assessment_batch(
                contract=contract,
                records=context.records,
                record_indices=context.record_indices,
            )
        except SemanticSelectionAgentUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - Agent retries are bounded.
            last_error = exc
            continue
        return ValidatedSemanticAssessmentBatch(
            contract=contract,
            assessments=assessments,
            attempt_count=attempt_count,
        )
    if last_error is None:
        raise RuntimeError("semantic agent validation failed without an error")
    raise last_error


def validate_semantic_assessment_batch(
    *,
    contract: EvidenceSelectionSemanticBatchContract,
    records: tuple[JSONObject, ...],
    record_indices: tuple[int, ...] | None = None,
) -> dict[int, EvidenceSelectionSemanticCandidateAssessment]:
    """Require exact record coverage and verbatim grounding in source values."""

    by_index = {
        assessment.record_index: assessment for assessment in contract.assessments
    }
    indices = record_indices or tuple(range(len(records)))
    if len(indices) != len(records) or len(set(indices)) != len(indices):
        raise ValueError("semantic validation records and indices must align")
    expected = set(indices)
    if set(by_index) != expected:
        missing = sorted(expected - set(by_index))
        unexpected = sorted(set(by_index) - expected)
        msg = (
            "semantic agent assessment coverage mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )
        raise ValueError(msg)
    records_by_index = dict(zip(indices, records, strict=True))
    for index, assessment in by_index.items():
        source_strings = tuple(_source_string_values(records_by_index[index]))
        if any(
            not any(span.casefold() in value.casefold() for value in source_strings)
            for span in assessment.evidence_spans
        ):
            msg = f"semantic agent evidence span was not found in record {index}"
            raise ValueError(msg)
    return by_index


def _source_string_values(value: JSONValue) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        return tuple(
            text for nested in value.values() for text in _source_string_values(nested)
        )
    if isinstance(value, list | tuple):
        return tuple(text for nested in value for text in _source_string_values(nested))
    return ()


__all__ = [
    "ValidatedSemanticAssessmentBatch",
    "assess_validated_semantic_batch",
    "validate_semantic_assessment_batch",
]
