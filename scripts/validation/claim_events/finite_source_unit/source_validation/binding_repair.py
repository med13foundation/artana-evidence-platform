"""Deterministic semantic invariants for agent-authored binding repair."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryBindingDisposition,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
        ClaimInventoryBindingRejection,
        ClaimInventoryItem,
    )

    from scripts.validation.claim_events.finite_source_unit.contracts import (
        SourceUnitExtractionOutput,
    )


def require_source_binding_repair_invariant(
    *,
    original: SourceUnitExtractionOutput,
    repaired: SourceUnitExtractionOutput,
    binding_errors: tuple[ClaimInventoryBindingRejection, ...],
) -> None:
    """Allow anchor-context correction without allowing scientific mutation."""

    if not binding_errors:
        raise StructuredModelSemanticError("binding repair requires prior rejections")
    if (
        repaired.eligibility_category is not original.eligibility_category
        or repaired.decision is not original.decision
    ):
        raise StructuredModelSemanticError(
            "binding repair changed the source-unit scientific decision",
        )
    if len(repaired.events) != len(original.events):
        raise StructuredModelSemanticError(
            "binding repair added or deleted an event",
        )

    rejected_indices = {error.batch_index for error in binding_errors}
    if any(index < 0 or index >= len(original.events) for index in rejected_indices):
        raise StructuredModelSemanticError("binding repair rejection index is invalid")
    if any(
        error.item != original.events[error.batch_index] for error in binding_errors
    ):
        raise StructuredModelSemanticError(
            "binding repair errors do not identify the original event batch",
        )

    for index, (original_event, repaired_event) in enumerate(
        zip(original.events, repaired.events, strict=True),
    ):
        if index not in rejected_indices and repaired_event != original_event:
            raise StructuredModelSemanticError(
                "binding repair changed an already source-bound sibling",
            )
        exact_span_repair = any(
            error.batch_index == index
            and error.disposition is ClaimInventoryBindingDisposition.EXACT_SPAN_MISSING
            for error in binding_errors
        )
        if _scientific_identity(
            repaired_event,
            include_exact_span=not exact_span_repair,
        ) != _scientific_identity(
            original_event,
            include_exact_span=not exact_span_repair,
        ):
            raise StructuredModelSemanticError(
                "binding repair changed event semantics or source identity",
            )


def require_minimal_exact_span_repairs(
    *,
    repaired: tuple[BoundClaimInventoryItem, ...],
    binding_errors: tuple[ClaimInventoryBindingRejection, ...],
) -> None:
    """Require a repaired missing span to be the minimal fixed-mention envelope."""

    missing_span_indices = {
        error.batch_index
        for error in binding_errors
        if error.disposition is ClaimInventoryBindingDisposition.EXACT_SPAN_MISSING
    }
    for index in missing_span_indices:
        candidate = repaired[index]
        mention_starts = (
            candidate.trigger_mention.source_start,
            *(
                argument.primary_mention.source_start
                for argument in candidate.bound_arguments
            ),
        )
        mention_ends = (
            candidate.trigger_mention.source_end,
            *(
                argument.primary_mention.source_end
                for argument in candidate.bound_arguments
            ),
        )
        if candidate.source_start != min(mention_starts) or candidate.source_end != max(
            mention_ends
        ):
            raise StructuredModelSemanticError(
                "binding repair exact_span is not the minimal fixed-mention envelope",
            )


def _scientific_identity(
    item: ClaimInventoryItem,
    *,
    include_exact_span: bool = True,
) -> tuple[object, ...]:
    """Exclude only left/right anchor context used to localize fixed mentions."""

    cue_anchor_span = (
        None
        if item.relation_cue_anchor is None
        else item.relation_cue_anchor.mention_span
    )
    arguments = tuple(
        (
            argument.role,
            argument.event_role,
            argument.exact_span,
            argument.role_rationale,
            tuple(anchor.mention_span for anchor in argument.mention_anchors),
            tuple(anchor.mention_span for anchor in argument.referent_anchors),
            argument.controlled_event_ref,
        )
        for argument in item.arguments
    )
    return (
        item.exact_span if include_exact_span else None,
        item.relation_cue_span,
        cue_anchor_span,
        item.local_event_id,
        arguments,
        item.source_locator,
        item.claim_kind,
        item.event_type,
        item.assertion_scope,
        item.polarity,
        item.epistemic_status,
        item.inventory_rationale,
    )


__all__ = [
    "require_minimal_exact_span_repairs",
    "require_source_binding_repair_invariant",
]
