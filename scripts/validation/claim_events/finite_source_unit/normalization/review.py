"""Independent categorical review of source-event normalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, cast

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
    CueAlignmentDecision,
    FamilyValidityDecision,
    InventoryCoverageDecision,
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


class LocalReviewDisposition(StrEnum):
    """Deterministic local-consistency result without qualification authority."""

    PASS = "PASS"
    FAIL = "FAIL"
    ABSTAIN = "ABSTAIN"


class _ContextDimensionReviewLike(Protocol):
    decision: object


@dataclass(frozen=True, slots=True)
class SourceUnitNormalizedReviewResult:
    """Validated categorical review with deterministically derived diagnostics."""

    output: SourceUnitNormalizedReviewOutput
    output_sha256: str
    source_unit_input_sha256: str
    normalization_envelope_sha256: str

    def __post_init__(self) -> None:
        try:
            type(self.output).model_validate(
                self.output.model_dump(mode="python", warnings=False),
                strict=True,
            )
        except ValueError as exc:
            raise ValueError(
                "review result contains unvalidated categorical values"
            ) from exc
        if self.output_sha256 != canonical_json_sha256(
            self.output.model_dump(mode="json")
        ):
            raise ValueError("review result does not match its categorical output")

    @property
    def scientific_loss_count(self) -> int:
        loss_decisions = {
            MaterialAxisDecision.MATERIAL_LOSS,
            MaterialAxisDecision.CONTRADICTION,
        }
        return sum(
            axis.decision in loss_decisions for axis in self.output.axis_reviews
        )

    @property
    def unsupported_addition_count(self) -> int:
        return sum(
            axis.decision is MaterialAxisDecision.MATERIAL_ADDITION
            for axis in self.output.axis_reviews
        )

    @property
    def unresolved_axis_count(self) -> int:
        return sum(
            axis.decision
            in {
                MaterialAxisDecision.ABSTAIN,
                MaterialAxisDecision.NOT_APPLICABLE,
            }
            for axis in self.output.axis_reviews
        )

    @property
    def unsupported_context_dimension_count(self) -> int:
        return sum(
            getattr(review.decision, "value", review.decision) == "UNSUPPORTED"
            for review in _context_dimension_reviews(self.output)
        )

    @property
    def unresolved_context_dimension_count(self) -> int:
        return sum(
            getattr(review.decision, "value", review.decision) == "ABSTAIN"
            for review in _context_dimension_reviews(self.output)
        )

    @property
    def provisional_context_dimension_count(self) -> int:
        return sum(
            getattr(review.decision, "value", review.decision) == "SUPPORTED"
            for review in _context_dimension_reviews(self.output)
        )

    @property
    def unsupported_candidate_count(self) -> int:
        return sum(
            review.source_entailment is EntailmentDecision.CONTRADICTED
            for review in self.output.candidate_reviews
        )

    @property
    def unresolved_candidate_count(self) -> int:
        return sum(
            review.source_entailment
            in {EntailmentDecision.INSUFFICIENT, EntailmentDecision.ABSTAIN}
            for review in self.output.candidate_reviews
        )

    @property
    def missing_inventory_count(self) -> int:
        return int(
            self.output.inventory_coverage
            in {
                InventoryCoverageDecision.MISSING_EVENT,
                InventoryCoverageDecision.MISSING_AND_EXTRA,
            }
        )

    @property
    def extra_inventory_count(self) -> int:
        return int(
            self.output.inventory_coverage
            in {
                InventoryCoverageDecision.EXTRA_EVENT,
                InventoryCoverageDecision.MISSING_AND_EXTRA,
            }
        )

    @property
    def unresolved_inventory_count(self) -> int:
        return int(
            self.output.inventory_coverage is InventoryCoverageDecision.ABSTAIN
        )

    @property
    def invalid_family_count(self) -> int:
        return int(self.output.family_validity is FamilyValidityDecision.INVALID)

    @property
    def unresolved_family_count(self) -> int:
        return int(self.output.family_validity is FamilyValidityDecision.ABSTAIN)

    @property
    def cue_mismatch_count(self) -> int:
        return int(
            self.output.cue_alignment is CueAlignmentDecision.MATERIAL_MISMATCH
        )

    @property
    def unresolved_cue_count(self) -> int:
        return int(self.output.cue_alignment is CueAlignmentDecision.ABSTAIN)

    @property
    def local_review_disposition(self) -> LocalReviewDisposition:
        """Consume every failure counter with fail-before-abstain precedence."""

        if any(
            (
                self.scientific_loss_count,
                self.unsupported_addition_count,
                self.unsupported_context_dimension_count,
                self.unsupported_candidate_count,
                self.missing_inventory_count,
                self.extra_inventory_count,
                self.invalid_family_count,
                self.cue_mismatch_count,
            )
        ):
            return LocalReviewDisposition.FAIL
        if any(
            (
                self.unresolved_axis_count,
                self.unresolved_context_dimension_count,
                self.unresolved_candidate_count,
                self.unresolved_inventory_count,
                self.unresolved_family_count,
                self.unresolved_cue_count,
                self.provisional_context_dimension_count,
            )
        ):
            return LocalReviewDisposition.ABSTAIN
        return LocalReviewDisposition.PASS


class NormalizedReviewBinder(Protocol):
    """Bind one versioned source-only review contract."""

    __module__: str
    __qualname__: str

    def __call__(
        self,
        output: SourceUnitNormalizedReviewOutput,
        *,
        unit: FrozenSourceUnit,
        original: SourceUnitExtractionResult,
        normalized: SourceUnitNormalizationResult,
    ) -> SourceUnitNormalizedReviewResult: ...


def bind_source_unit_normalized_review(
    output: SourceUnitNormalizedReviewOutput,
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
) -> SourceUnitNormalizedReviewResult:
    """Require complete review coverage and verbatim source evidence."""

    normalized.require_canonical_envelope(unit=unit, original=original)
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

    return SourceUnitNormalizedReviewResult(
        output=output,
        output_sha256=canonical_json_sha256(output.model_dump(mode="json")),
        source_unit_input_sha256=unit.input_sha256,
        normalization_envelope_sha256=normalized.envelope_sha256,
    )


def _context_dimension_reviews(
    output: SourceUnitNormalizedReviewOutput,
) -> tuple[_ContextDimensionReviewLike, ...]:
    reviews = getattr(output, "context_dimension_reviews", ())
    return (
        cast("tuple[_ContextDimensionReviewLike, ...]", reviews)
        if isinstance(reviews, tuple)
        else ()
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
    output_schema: type[SourceUnitNormalizedReviewOutput] = (
        SourceUnitNormalizedReviewOutput
    ),
    review_binder: NormalizedReviewBinder = bind_source_unit_normalized_review,
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
            output_schema=output_schema,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

    return await run_audited_structured_step(
        invoke_model=invoke,
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=ModelAttemptAuditContext(
            attempt_role="normalized_review",
            pass_role="normalized_review",  # noqa: S106 - audit role
            retry_context=None,
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            semantic_unit_id=unit.unit_id,
        ),
        validate_semantics=lambda output: review_binder(
            output,
            unit=unit,
            original=original,
            normalized=normalized,
        ),
    )


__all__ = [
    "NormalizedReviewBinder",
    "LocalReviewDisposition",
    "SourceUnitNormalizedReviewResult",
    "bind_source_unit_normalized_review",
    "review_source_unit_normalization",
]
