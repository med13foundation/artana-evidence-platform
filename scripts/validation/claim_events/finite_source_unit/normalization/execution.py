"""Three-agent scientific extraction, normalization, and review execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
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
        SourceUnitNormalizationOutput,
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
    failed_stage: (
        Literal["primary", "structure_normalization", "normalized_review"] | None
    )


async def execute_three_source_unit_agents(  # noqa: PLR0913
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
    review_prompt_builder: NormalizedReviewPromptBuilder,
    review_prompt_version: str,
    audit_evidence_unit_id: str | None = None,
) -> ThreeCallAgentRunEvidence:
    """Run exactly three stages; stop on first failure and never retry."""

    audit = start_model_attempt_audit(
        evidence_unit_id=audit_evidence_unit_id or unit.unit_id
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
            execution_namespace=execution_namespace,
            unit=unit,
            prompt_policy=extraction_prompt_policy,
            prepared_prompt=prepared_extraction_prompt,
        )
        original_output = original.parsed
        original_result = original.value
        original_raw = original.raw_output

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
            execution_namespace=execution_namespace,
            unit=unit,
            original=original_result,
            original_raw_output=original_raw,
            prompt=normalization_prompt,
            prompt_version=normalization_prompt_version,
        )
        normalized_output = normalized.parsed
        normalized_result = normalized.value
        normalized_raw = normalized.raw_output

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
            execution_namespace=execution_namespace,
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
    except Exception as exc:  # noqa: BLE001 - preserve terminal failure category
        error_type = type(exc).__name__
        failed_stage = active_stage
    finally:
        stop_model_attempt_audit(audit)
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
        records=tuple(audit.records),
        error_type=error_type,
        failed_stage=failed_stage,
    )


__all__ = [
    "NormalizationPromptBuilder",
    "NormalizedReviewPromptBuilder",
    "SourceUnitPromptBuildError",
    "ThreeCallAgentRunEvidence",
    "execute_three_source_unit_agents",
]
