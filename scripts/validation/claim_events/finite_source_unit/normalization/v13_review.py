"""Fail-closed binding for V13-v6 context-dimension adjudication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)

from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    MaterialAxisDecision,
    PresenceDecision,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    SourceUnitNormalizedReviewResult,
    bind_source_unit_normalized_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
    ContextCrossingDecision,
    ContextDimensionDecision,
    SourceUnitNormalizedReviewOutputV13V6,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        ClaimInventoryItem,
    )

    from scripts.validation.claim_events.finite_source_unit.normalization.context_dimensions import (
        ContextDimension,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.service import (
        SourceUnitNormalizationResult,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
        ContextDimensionReview,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        SourceUnitExtractionResult,
    )
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )


def bind_v13_context_dimension_review(
    output: SourceUnitNormalizedReviewOutput,
    *,
    unit: FrozenSourceUnit,
    original: SourceUnitExtractionResult,
    normalized: SourceUnitNormalizationResult,
) -> SourceUnitNormalizedReviewResult:
    """Require complete source-only review for every proposed context dimension."""

    if not isinstance(output, SourceUnitNormalizedReviewOutputV13V6):
        raise StructuredModelSemanticError(
            "V13-v6 requires its versioned normalized-review contract"
        )
    base = bind_source_unit_normalized_review(
        output,
        unit=unit,
        original=original,
        normalized=normalized,
    )
    dimensions = normalized.output.context_dimensions
    reviews = output.context_dimension_reviews
    if len(reviews) != len(dimensions):
        raise StructuredModelSemanticError(
            "V13-v6 review must cover every context dimension exactly"
        )

    for dimension, review in zip(dimensions, reviews, strict=True):
        _require_context_review(
            dimension=dimension,
            review=review,
            dimensions=dimensions,
            events=normalized.output.events,
            source_text=unit.text,
        )

    unsupported_count = sum(
        review.decision is ContextDimensionDecision.UNSUPPORTED for review in reviews
    )
    unresolved_count = sum(
        review.decision is ContextDimensionDecision.ABSTAIN for review in reviews
    )
    provisional_count = sum(
        review.decision is ContextDimensionDecision.SUPPORTED for review in reviews
    )
    _require_context_aggregate(
        output=output,
        unsupported_count=unsupported_count,
        unresolved_count=unresolved_count,
    )
    _require_unsupported_additions_consistency(
        output=output,
        has_addition=bool(
            base.unsupported_addition_count
            or unsupported_count
            or base.unsupported_candidate_count
            or base.extra_inventory_count
        ),
        has_unresolved_addition=bool(
            unresolved_count
            or base.unresolved_candidate_count
            or base.unresolved_inventory_count
        ),
    )
    if (
        base.unsupported_context_dimension_count != unsupported_count
        or base.unresolved_context_dimension_count != unresolved_count
        or base.provisional_context_dimension_count != provisional_count
    ):
        raise StructuredModelSemanticError(
            "context diagnostics do not match categorical review output"
        )
    return base


def _require_context_review(
    *,
    dimension: ContextDimension,
    review: ContextDimensionReview,
    dimensions: tuple[ContextDimension, ...],
    events: tuple[ClaimInventoryItem, ...],
    source_text: str,
) -> None:
    if review.dimension_id != dimension.dimension_id:
        raise StructuredModelSemanticError(
            "context review dimension identity does not match normalization"
        )
    if any(span not in source_text for span in _all_review_evidence(review)):
        raise StructuredModelSemanticError(
            "context review evidence must be verbatim in the source unit"
        )
    _require_factor_and_level_evidence(dimension=dimension, review=review)
    if review.decision is ContextDimensionDecision.SUPPORTED:
        _require_supported_evidence(
            dimension=dimension,
            review=review,
            events=events,
            source_text=source_text,
        )
    _require_crossing_review(
        dimension=dimension,
        review=review,
        dimensions=dimensions,
        source_text=source_text,
    )


def _require_supported_evidence(
    *,
    dimension: ContextDimension,
    review: ContextDimensionReview,
    events: tuple[ClaimInventoryItem, ...],
    source_text: str,
) -> None:
    if any(
        _is_source_saturating_evidence(evidence, source_text)
        for evidence in (
            *review.contrast_evidence_spans,
            *review.event_scope_evidence_spans,
        )
    ):
        raise StructuredModelSemanticError(
            "supported context subdecisions require narrower evidence than the source unit"
        )
    required_spans = (dimension.factor_span, *dimension.level_spans)
    if not any(
        all(required in evidence for required in required_spans)
        for evidence in review.contrast_evidence_spans
    ):
        raise StructuredModelSemanticError(
            "one supported contrast span must jointly cover factor and every level"
        )
    events_by_id = {event.local_event_id: event for event in events}
    for event_id in dimension.applies_to_local_event_ids:
        event = events_by_id[event_id]
        event_spans = (
            event.relation_cue_span,
            *(argument.exact_span for argument in event.arguments),
        )
        if not any(
            all(required in evidence for required in event_spans)
            for evidence in review.event_scope_evidence_spans
        ):
            raise StructuredModelSemanticError(
                "one event-scope span must jointly cover each referenced event"
            )


def _require_factor_and_level_evidence(
    *,
    dimension: ContextDimension,
    review: ContextDimensionReview,
) -> None:
    if review.factor_evidence_spans != (dimension.factor_span,):
        raise StructuredModelSemanticError(
            "factor evidence must equal the proposed factor span exactly"
        )
    if len(review.level_reviews) != len(dimension.level_spans):
        raise StructuredModelSemanticError(
            "context review must cover every proposed level exactly"
        )
    for level_position, (level_span, level_review) in enumerate(
        zip(dimension.level_spans, review.level_reviews, strict=True)
    ):
        if (
            level_review.level_position != level_position
            or level_review.level_span != level_span
        ):
            raise StructuredModelSemanticError(
                "level review identity does not match the proposed dimension"
            )
        if level_review.evidence_spans != (level_span,):
            raise StructuredModelSemanticError(
                "level evidence must equal its proposed level span exactly"
            )


def _all_review_evidence(review: ContextDimensionReview) -> tuple[str, ...]:
    return (
        *review.factor_evidence_spans,
        *(span for level in review.level_reviews for span in level.evidence_spans),
        *review.contrast_evidence_spans,
        *review.event_scope_evidence_spans,
        *review.crossing_evidence_spans,
    )


def _require_crossing_review(
    *,
    dimension: ContextDimension,
    review: ContextDimensionReview,
    dimensions: tuple[ContextDimension, ...],
    source_text: str,
) -> None:
    has_crossing = bool(dimension.crossed_dimension_ids)
    if (
        has_crossing
        and review.crossing_validity is ContextCrossingDecision.NOT_APPLICABLE
    ):
        raise StructuredModelSemanticError(
            "declared context crossing cannot be NOT_APPLICABLE"
        )
    if (
        has_crossing
        and review.decision is ContextDimensionDecision.SUPPORTED
        and review.crossing_validity is not ContextCrossingDecision.SOURCE_EXPLICIT
    ):
        raise StructuredModelSemanticError(
            "declared context crossing requires SOURCE_EXPLICIT review"
        )
    if (
        not has_crossing
        and review.crossing_validity is not ContextCrossingDecision.NOT_APPLICABLE
    ):
        raise StructuredModelSemanticError(
            "uncrossed context requires NOT_APPLICABLE crossing review"
        )
    if not has_crossing or review.decision is not ContextDimensionDecision.SUPPORTED:
        return
    if any(
        _is_source_saturating_evidence(evidence, source_text)
        for evidence in review.crossing_evidence_spans
    ):
        raise StructuredModelSemanticError(
            "supported crossing requires narrower evidence than the source unit"
        )
    crossed_dimensions = tuple(
        candidate
        for candidate in dimensions
        if candidate.dimension_id in dimension.crossed_dimension_ids
    )
    required_crossing_spans = (
        dimension.factor_span,
        *dimension.level_spans,
        *(
            span
            for candidate in crossed_dimensions
            for span in (candidate.factor_span, *candidate.level_spans)
        ),
    )
    if not any(
        all(required in evidence for required in required_crossing_spans)
        for evidence in review.crossing_evidence_spans
    ):
        raise StructuredModelSemanticError(
            "one crossing span must jointly cover all factors and levels"
        )


def _is_source_saturating_evidence(evidence: str, source_text: str) -> bool:
    evidence_length = len(evidence.strip())
    source_length = len(source_text.strip())
    if source_length == 0:
        return False
    return evidence_length * 10 >= source_length * 9


def _require_context_aggregate(
    *,
    output: SourceUnitNormalizedReviewOutputV13V6,
    unsupported_count: int,
    unresolved_count: int,
) -> None:
    context_axis = next(
        review
        for review in output.axis_reviews
        if review.axis is MaterialAxis.CONTEXT_SCOPE
    )
    if unsupported_count:
        if output.unsupported_additions is not PresenceDecision.PRESENT:
            raise StructuredModelSemanticError(
                "unsupported context requires unsupported_additions PRESENT"
            )
        if context_axis.decision is not MaterialAxisDecision.MATERIAL_ADDITION:
            raise StructuredModelSemanticError(
                "unsupported context requires CONTEXT_SCOPE MATERIAL_ADDITION"
            )
        return
    if unresolved_count:
        if context_axis.decision is not MaterialAxisDecision.ABSTAIN:
            raise StructuredModelSemanticError(
                "unresolved context requires CONTEXT_SCOPE ABSTAIN"
            )
        return
    if output.context_dimension_reviews and context_axis.decision not in {
        MaterialAxisDecision.PRESERVED,
        MaterialAxisDecision.COMPATIBLE_REFINEMENT,
    }:
        raise StructuredModelSemanticError(
            "supported context requires a preserved or refined CONTEXT_SCOPE"
        )


def _require_unsupported_additions_consistency(
    *,
    output: SourceUnitNormalizedReviewOutputV13V6,
    has_addition: bool,
    has_unresolved_addition: bool,
) -> None:
    expected = (
        PresenceDecision.PRESENT
        if has_addition
        else PresenceDecision.ABSTAIN
        if has_unresolved_addition
        else PresenceDecision.ABSENT
    )
    if output.unsupported_additions is not expected:
        raise StructuredModelSemanticError(
            "unsupported_additions must match deterministic review findings"
        )


__all__ = ["bind_v13_context_dimension_review"]
