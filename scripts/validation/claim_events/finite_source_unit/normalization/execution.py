"""Three-agent scientific extraction, normalization, and review execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    fingerprinted_step_key,
    start_model_attempt_audit,
    stop_model_attempt_audit,
)

from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    SourceUnitNormalizationOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    SourceUnitNormalizedReviewResult,
    review_source_unit_normalization,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    SourceUnitNormalizationResult,
    normalize_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    SourceUnitExtractionResult,
    extract_source_unit,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )

    from scripts.validation.claim_events.finite_source_unit.contracts import (
        SourceUnitExtractionOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
        SourceUnitNormalizedReviewOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
        SourceUnitPromptPolicy,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


class NormalizationPromptBuilder(Protocol):
    """Build Call 2 only after Call 1 is frozen."""

    def __call__(
        self,
        *,
        unit: FrozenSourceUnit,
        original: SourceUnitExtractionResult,
    ) -> str: ...


class NormalizedReviewPromptBuilder(Protocol):
    """Build Call 3 only after both prior calls are frozen."""

    def __call__(
        self,
        *,
        unit: FrozenSourceUnit,
        original: SourceUnitExtractionResult,
        normalized: SourceUnitNormalizationResult,
    ) -> str: ...


class SourceUnitPromptBuildError(RuntimeError):
    """Categorical local failure between audited provider stages."""


class SourceUnitEvidencePersistenceError(RuntimeError):
    """Durable evidence could not be persisted after an audited attempt."""


@dataclass(frozen=True, slots=True)
class ThreeCallAgentRunEvidence:
    """Non-lossy evidence from three ordered, audited provider calls."""

    original_extraction: SourceUnitExtractionOutput | None
    original_result: SourceUnitExtractionResult | None
    original_raw_output: dict[str, object] | None
    normalized_extraction: SourceUnitNormalizationOutput | None
    normalized_result: SourceUnitNormalizationResult | None
    normalized_raw_output: dict[str, object] | None
    normalized_review: SourceUnitNormalizedReviewOutput | None
    review_result: SourceUnitNormalizedReviewResult | None
    review_raw_output: dict[str, object] | None
    records: tuple[ModelAttemptAuditRecord, ...]
    error_type: str | None
    execution_contract_version: str | None
    failed_stage: (
        Literal["primary", "structure_normalization", "normalized_review"] | None
    )


class ThreeCallEvidenceObserver(Protocol):
    """Persist a cumulative snapshot immediately after an audited stage."""

    def __call__(self, evidence: ThreeCallAgentRunEvidence) -> None: ...


class ModelAttemptObserver(Protocol):
    """Persist one immutable provider-attempt record at its creation boundary."""

    def __call__(self, record: ModelAttemptAuditRecord) -> None: ...


async def execute_three_source_unit_agents(  # noqa: PLR0913, PLR0915
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    extraction_prompt_policy: SourceUnitPromptPolicy,
    prepared_extraction_prompt: str | None = None,
    normalization_prompt_builder: NormalizationPromptBuilder,
    normalization_prompt_version: str,
    normalization_output_schema: type[SourceUnitNormalizationOutput] = (
        SourceUnitNormalizationOutput
    ),
    review_prompt_builder: NormalizedReviewPromptBuilder,
    review_prompt_version: str,
    execution_contract_version: str | None = None,
    audit_evidence_unit_id: str | None = None,
    evidence_observer: ThreeCallEvidenceObserver | None = None,
    attempt_observer: ModelAttemptObserver | None = None,
) -> ThreeCallAgentRunEvidence:
    """Run exactly three stages; stop on first failure and never retry."""

    if execution_contract_version is not None and (
        not execution_contract_version.strip()
        or execution_contract_version.strip() != execution_contract_version
    ):
        raise ValueError(
            "execution_contract_version must be a nonempty trimmed value"
        )
    contract_bound_namespace = (
        execution_namespace
        if execution_contract_version is None
        else fingerprinted_step_key(
            "execution-contract",
            execution_namespace,
            execution_contract_version,
        )
    )
    audit = start_model_attempt_audit(
        evidence_unit_id=audit_evidence_unit_id or unit.unit_id,
        execution_contract_version=execution_contract_version,
        record_observer=attempt_observer,
    )
    original_output: SourceUnitExtractionOutput | None = None
    original_result: SourceUnitExtractionResult | None = None
    original_raw: dict[str, object] | None = None
    normalized_output: SourceUnitNormalizationOutput | None = None
    normalized_result: SourceUnitNormalizationResult | None = None
    normalized_raw: dict[str, object] | None = None
    review_output: SourceUnitNormalizedReviewOutput | None = None
    review_result: SourceUnitNormalizedReviewResult | None = None
    review_raw: dict[str, object] | None = None
    error_type: str | None = None
    active_stage: Literal["primary", "structure_normalization", "normalized_review"] = (
        "primary"
    )
    failed_stage: (
        Literal["primary", "structure_normalization", "normalized_review"] | None
    ) = None
    try:
        original = await extract_source_unit(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=contract_bound_namespace,
            unit=unit,
            prompt_policy=extraction_prompt_policy,
            prepared_prompt=prepared_extraction_prompt,
        )
        original_output = original.parsed
        original_result = original.value
        original_raw = original.raw_output
        _observe_evidence(
            evidence_observer,
            _agent_run_evidence(
                original_output=original_output,
                original_result=original_result,
                original_raw=original_raw,
                normalized_output=normalized_output,
                normalized_result=normalized_result,
                normalized_raw=normalized_raw,
                review_output=review_output,
                review_result=review_result,
                review_raw=review_raw,
                records=tuple(audit.records),
                error_type=None,
                execution_contract_version=execution_contract_version,
                failed_stage=None,
            ),
        )

        active_stage = "structure_normalization"
        try:
            normalization_prompt = normalization_prompt_builder(
                unit=unit,
                original=original_result,
            )
        except Exception as exc:  # noqa: BLE001 - normalize local failure category
            raise SourceUnitPromptBuildError from exc
        normalized = await normalize_source_unit_extraction(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=contract_bound_namespace,
            unit=unit,
            original=original_result,
            original_raw_output=original_raw,
            prompt=normalization_prompt,
            prompt_version=normalization_prompt_version,
            output_schema=normalization_output_schema,
        )
        normalized_output = normalized.parsed
        normalized_result = normalized.value
        normalized_raw = normalized.raw_output
        _observe_evidence(
            evidence_observer,
            _agent_run_evidence(
                original_output=original_output,
                original_result=original_result,
                original_raw=original_raw,
                normalized_output=normalized_output,
                normalized_result=normalized_result,
                normalized_raw=normalized_raw,
                review_output=review_output,
                review_result=review_result,
                review_raw=review_raw,
                records=tuple(audit.records),
                error_type=None,
                execution_contract_version=execution_contract_version,
                failed_stage=None,
            ),
        )

        active_stage = "normalized_review"
        try:
            review_prompt = review_prompt_builder(
                unit=unit,
                original=original_result,
                normalized=normalized_result,
            )
        except Exception as exc:  # noqa: BLE001 - normalize local failure category
            raise SourceUnitPromptBuildError from exc
        review = await review_source_unit_normalization(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=contract_bound_namespace,
            unit=unit,
            original=original_result,
            normalized=normalized_result,
            original_raw_output=original_raw,
            normalized_raw_output=normalized_raw,
            prompt=review_prompt,
            prompt_version=review_prompt_version,
        )
        review_output = review.parsed
        review_result = review.value
        review_raw = review.raw_output
        _observe_evidence(
            evidence_observer,
            _agent_run_evidence(
                original_output=original_output,
                original_result=original_result,
                original_raw=original_raw,
                normalized_output=normalized_output,
                normalized_result=normalized_result,
                normalized_raw=normalized_raw,
                review_output=review_output,
                review_result=review_result,
                review_raw=review_raw,
                records=tuple(audit.records),
                error_type=None,
                execution_contract_version=execution_contract_version,
                failed_stage=None,
            ),
        )
    except SourceUnitEvidencePersistenceError:
        raise
    except Exception as exc:  # noqa: BLE001 - preserve terminal failure category
        error_type = type(exc).__name__
        failed_stage = active_stage
        if audit.records:
            _observe_evidence(
                evidence_observer,
                _agent_run_evidence(
                    original_output=original_output,
                    original_result=original_result,
                    original_raw=original_raw,
                    normalized_output=normalized_output,
                    normalized_result=normalized_result,
                    normalized_raw=normalized_raw,
                    review_output=review_output,
                    review_result=review_result,
                    review_raw=review_raw,
                    records=tuple(audit.records),
                    error_type=error_type,
                    execution_contract_version=execution_contract_version,
                    failed_stage=failed_stage,
                ),
            )
    finally:
        stop_model_attempt_audit(audit)
    return _agent_run_evidence(
        original_output=original_output,
        original_result=original_result,
        original_raw=original_raw,
        normalized_output=normalized_output,
        normalized_result=normalized_result,
        normalized_raw=normalized_raw,
        review_output=review_output,
        review_result=review_result,
        review_raw=review_raw,
        records=tuple(audit.records),
        error_type=error_type,
        execution_contract_version=execution_contract_version,
        failed_stage=failed_stage,
    )


def _agent_run_evidence(  # noqa: PLR0913
    *,
    original_output: SourceUnitExtractionOutput | None,
    original_result: SourceUnitExtractionResult | None,
    original_raw: dict[str, object] | None,
    normalized_output: SourceUnitNormalizationOutput | None,
    normalized_result: SourceUnitNormalizationResult | None,
    normalized_raw: dict[str, object] | None,
    review_output: SourceUnitNormalizedReviewOutput | None,
    review_result: SourceUnitNormalizedReviewResult | None,
    review_raw: dict[str, object] | None,
    records: tuple[ModelAttemptAuditRecord, ...],
    error_type: str | None,
    execution_contract_version: str | None,
    failed_stage: (
        Literal["primary", "structure_normalization", "normalized_review"] | None
    ),
) -> ThreeCallAgentRunEvidence:
    return ThreeCallAgentRunEvidence(
        original_extraction=original_output,
        original_result=original_result,
        original_raw_output=original_raw,
        normalized_extraction=normalized_output,
        normalized_result=normalized_result,
        normalized_raw_output=normalized_raw,
        normalized_review=review_output,
        review_result=review_result,
        review_raw_output=review_raw,
        records=records,
        error_type=error_type,
        execution_contract_version=execution_contract_version,
        failed_stage=failed_stage,
    )


def _observe_evidence(
    observer: ThreeCallEvidenceObserver | None,
    evidence: ThreeCallAgentRunEvidence,
) -> None:
    if observer is None:
        return
    try:
        observer(evidence)
    except Exception as exc:  # noqa: BLE001 - persistence failures are fail-closed
        raise SourceUnitEvidencePersistenceError from exc


__all__ = [
    "ModelAttemptObserver",
    "NormalizationPromptBuilder",
    "NormalizedReviewPromptBuilder",
    "SourceUnitEvidencePersistenceError",
    "SourceUnitPromptBuildError",
    "ThreeCallAgentRunEvidence",
    "ThreeCallEvidenceObserver",
    "execute_three_source_unit_agents",
]
