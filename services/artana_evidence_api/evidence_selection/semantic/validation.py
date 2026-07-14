"""Grounding validation and bounded retries for semantic agent batches."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.evidence_selection.semantic.attempts import (
    SemanticLocalFailureCause,
    SemanticLocalFailureRecorder,
    SemanticLocalFailureStage,
    SemanticLocalValidationFailure,
)
from artana_evidence_api.evidence_selection.semantic.contracts import (
    EvidenceSelectionSemanticBatchContract,
    EvidenceSelectionSemanticCandidateAssessment,
)
from artana_evidence_api.evidence_selection.semantic.evidence import (
    SemanticEvidenceOption,
    resolve_semantic_evidence_references,
)
from artana_evidence_api.evidence_selection.semantic.model import (
    EvidenceSelectionSemanticContext,
    EvidenceSelectionSemanticModelRunner,
    SemanticSelectionAgentUnavailableError,
)

_MAX_AGENT_ATTEMPTS = 2


class SemanticLocalValidationError(ValueError):
    """Typed service-local rejection of an otherwise completed model response."""

    def __init__(
        self,
        message: str,
        *,
        stage: SemanticLocalFailureStage,
        cause: SemanticLocalFailureCause,
    ) -> None:
        super().__init__(message)
        self.failure = SemanticLocalValidationFailure(stage=stage, cause=cause)


@dataclass(frozen=True, slots=True)
class ValidatedSemanticAssessmentBatch:
    """One complete grounded contract and its indexed assessments."""

    contract: EvidenceSelectionSemanticBatchContract
    agent_run_id: str
    assessments: dict[int, EvidenceSelectionSemanticCandidateAssessment]
    evidence_options: dict[int, tuple[SemanticEvidenceOption, ...]]
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
            try:
                assessments = validate_semantic_assessment_batch(
                    contract=contract,
                    context=context,
                )
                agent_run_id = _require_agent_run_id(contract)
                records_by_index = dict(
                    zip(context.record_indices, context.records, strict=True),
                )
                try:
                    evidence_options = {
                        index: resolve_semantic_evidence_references(
                            record_ref=assessment.record_ref,
                            record=records_by_index[index],
                            references=assessment.evidence_references,
                        )
                        for index, assessment in assessments.items()
                    }
                except Exception as exc:
                    raise SemanticLocalValidationError(
                        str(exc),
                        stage="evidence_reference_validation",
                        cause="evidence_reference_invalid",
                    ) from exc
            except SemanticLocalValidationError as exc:
                _record_local_validation_failure(runner=runner, failure=exc.failure)
                raise
            except Exception as exc:
                failure = SemanticLocalValidationFailure(
                    stage="semantic_batch_validation",
                    cause="unexpected_local_validation_error",
                )
                _record_local_validation_failure(runner=runner, failure=failure)
                raise SemanticLocalValidationError(
                    str(exc),
                    stage=failure.stage,
                    cause=failure.cause,
                ) from exc
        except SemanticSelectionAgentUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - Agent retries are bounded.
            last_error = exc
            continue
        return ValidatedSemanticAssessmentBatch(
            contract=contract,
            agent_run_id=agent_run_id,
            assessments=assessments,
            evidence_options=evidence_options,
            attempt_count=attempt_count,
        )
    if last_error is None:
        raise RuntimeError("semantic agent validation failed without an error")
    raise last_error


def validate_semantic_assessment_batch(
    *,
    contract: EvidenceSelectionSemanticBatchContract,
    context: EvidenceSelectionSemanticContext,
) -> dict[int, EvidenceSelectionSemanticCandidateAssessment]:
    """Require exact record coverage before resolving source-owned evidence."""

    by_reference = {
        assessment.record_ref: assessment for assessment in contract.assessments
    }
    expected = set(context.record_references)
    if set(by_reference) != expected:
        missing = sorted(expected - set(by_reference))
        unexpected = sorted(set(by_reference) - expected)
        msg = (
            "semantic agent assessment coverage mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )
        raise SemanticLocalValidationError(
            msg,
            stage="semantic_batch_validation",
            cause="record_coverage_mismatch",
        )
    return {
        index: by_reference[record_ref]
        for index, record_ref in zip(
            context.record_indices,
            context.record_references,
            strict=True,
        )
    }


def _require_agent_run_id(
    contract: EvidenceSelectionSemanticBatchContract,
) -> str:
    if contract.agent_run_id is None:
        raise SemanticLocalValidationError(
            "semantic agent contract is missing service run identity",
            stage="service_run_identity_validation",
            cause="agent_run_identity_missing",
        )
    return contract.agent_run_id


def _record_local_validation_failure(
    *,
    runner: EvidenceSelectionSemanticModelRunner,
    failure: SemanticLocalValidationFailure,
) -> None:
    if isinstance(runner, SemanticLocalFailureRecorder):
        runner.record_local_validation_failure(failure)


__all__ = [
    "ValidatedSemanticAssessmentBatch",
    "SemanticLocalValidationError",
    "assess_validated_semantic_batch",
    "validate_semantic_assessment_batch",
]
