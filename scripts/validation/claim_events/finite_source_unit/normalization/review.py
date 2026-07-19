"""Independent categorical review of source-event normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    kernel_run_id_for_invocation,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    AuditedStructuredStepResult,
    StructuredModelSemanticError,
    run_audited_structured_step,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    ModelStepResult,
    fingerprinted_step_key,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    EntailmentDecision,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxisDecision,
    NormalizationFamily,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    SourceUnitNormalizationResult,
    canonical_json_sha256,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
        SourceUnitExtractionResult,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


@dataclass(frozen=True, slots=True)
class SourceUnitNormalizedReviewResult:
    """Validated review plus deterministic categorical failure counts."""

    output: SourceUnitNormalizedReviewOutput
    scientific_loss_count: int
    unsupported_addition_count: int
    unresolved_axis_count: int


def bind_source_unit_normalized_review(
    output: SourceUnitNormalizedReviewOutput,
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
) -> SourceUnitNormalizedReviewResult:
    """Require complete review coverage and verbatim source evidence."""

    if output.eligibility_category is not original.output.eligibility_category:
        raise StructuredModelSemanticError(
            "normalized review changed the source eligibility category"
        )
    expected_candidates = len(normalized.accepted)
    if len(output.candidate_reviews) != expected_candidates:
        raise StructuredModelSemanticError(
            "normalized review must cover every candidate exactly"
        )
    if (
        normalized.output.family is NormalizationFamily.ABSTAIN
        and output.candidate_reviews
    ):
        raise StructuredModelSemanticError("ABSTAIN normalization has no candidates")
    for candidate, review in zip(
        normalized.accepted,
        output.candidate_reviews,
        strict=True,
    ):
        if any(span not in unit.text for span in review.evidence_spans):
            raise StructuredModelSemanticError(
                "candidate review evidence must be verbatim in the source unit"
            )
        if review.source_entailment is EntailmentDecision.ENTAILED:
            required_spans = (
                candidate.item.relation_cue_span,
                *(argument.exact_span for argument in candidate.item.arguments),
            )
            if any(
                not any(required in evidence for evidence in review.evidence_spans)
                for required in required_spans
            ):
                raise StructuredModelSemanticError(
                    "ENTAILED normalized review must cover trigger and arguments"
                )
    for axis in output.axis_reviews:
        if any(span not in unit.text for span in axis.evidence_spans):
            raise StructuredModelSemanticError(
                "axis review evidence must be verbatim in the source unit"
            )

    loss_decisions = {
        MaterialAxisDecision.MATERIAL_LOSS,
        MaterialAxisDecision.CONTRADICTION,
    }
    scientific_loss_count = sum(
        axis.decision in loss_decisions for axis in output.axis_reviews
    )
    unsupported_addition_count = sum(
        axis.decision is MaterialAxisDecision.MATERIAL_ADDITION
        for axis in output.axis_reviews
    )
    unresolved_axis_count = sum(
        axis.decision
        in {
            MaterialAxisDecision.ABSTAIN,
            MaterialAxisDecision.NOT_APPLICABLE,
        }
        for axis in output.axis_reviews
    )
    return SourceUnitNormalizedReviewResult(
        output=output,
        scientific_loss_count=scientific_loss_count,
        unsupported_addition_count=unsupported_addition_count,
        unresolved_axis_count=unresolved_axis_count,
    )


async def review_source_unit_normalization(  # noqa: PLR0913
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
    original_raw_output: dict[str, object],
    normalized_raw_output: dict[str, object],
    prompt: str,
    prompt_version: str,
) -> AuditedStructuredStepResult[
    SourceUnitNormalizedReviewOutput,
    SourceUnitNormalizedReviewResult,
]:
    """Run one role-separated review bound to both prior raw payloads."""

    original_sha256 = canonical_json_sha256(original_raw_output)
    normalized_sha256 = canonical_json_sha256(normalized_raw_output)
    step_key = fingerprinted_step_key(
        prompt_version,
        model_id,
        unit.input_sha256,
        original_sha256,
        normalized_sha256,
        execution_namespace,
    )

    async def invoke(invocation_id: str, provider_prompt: str) -> ModelStepResult:
        return await client.step(
            run_id=kernel_run_id_for_invocation(invocation_id),
            tenant=tenant,
            model=model_id,
            prompt=provider_prompt,
            output_schema=SourceUnitNormalizedReviewOutput,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=SourceUnitNormalizedReviewOutput,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="normalized_review",
            pass_role="normalized_review",  # noqa: S106 - audit role
            retry_context=None,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            semantic_unit_id=unit.unit_id,
        ),
        validate_semantics=lambda output: bind_source_unit_normalized_review(
            output,
            unit=unit,
            original=original,
            normalized=normalized,
        ),
    )


__all__ = [
    "SourceUnitNormalizedReviewResult",
    "bind_source_unit_normalized_review",
    "review_source_unit_normalization",
]
