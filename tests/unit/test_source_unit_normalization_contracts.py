"""Unit tests for categorical scientific-normalization contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    NormalizationFamily,
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)


def _argument(
    *,
    role: str = "GENE_OR_PROTEIN",
    event_role: str = "THEME",
    exact_span: str = "Foxp3",
    controlled_event_ref: str | None = None,
) -> dict[str, object]:
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": exact_span,
        "mention_anchors": [],
        "referent_anchors": [],
        "controlled_event_ref": controlled_event_ref,
        "role_rationale": "The source names Foxp3 as the event theme.",
    }


def _event(
    *,
    local_event_id: str = "direct-event",
    controlled_target: bool = False,
    controlled_event_ref: str | None = None,
) -> dict[str, object]:
    return {
        "exact_span": "IL-4 does not affect Foxp3 expression.",
        "relation_cue_span": "does not affect",
        "arguments": [
            _argument(
                role=(
                    "BIOLOGICAL_PROCESS"
                    if controlled_event_ref is not None
                    else "GENE_OR_PROTEIN"
                ),
                exact_span=(
                    "Foxp3 expression" if controlled_event_ref is not None else "Foxp3"
                ),
                controlled_event_ref=controlled_event_ref,
            ),
            _argument(
                role="GENE_OR_PROTEIN",
                event_role="AGENT",
                exact_span="IL-4",
            ),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "NO_EFFECT",
        "assertion_scope": (
            "CONTROLLED_TARGET" if controlled_target else "SOURCE_ASSERTED"
        ),
        "polarity": "UNSCOPED" if controlled_target else "NULL_RESULT",
        "epistemic_status": "UNASSERTED" if controlled_target else "ASSERTED",
        "local_event_id": local_event_id,
        "inventory_rationale": "The source explicitly reports the null event.",
    }


def _mapping(position: int = 0) -> dict[str, object]:
    return {
        "normalized_event_position": position,
        "source_event_positions": [0],
        "operation": "REFRAME",
        "reasoning": "The output makes the same null predicate explicit.",
        "falsification_condition": "A changed participant would falsify this map.",
    }


def test_direct_normalization_is_categorical_and_mapped() -> None:
    output = SourceUnitNormalizationOutput.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "family": "DIRECT",
            "abstention_reason": "NONE",
            "events": [_event()],
            "mappings": [_mapping()],
            "reasoning": "A direct no-effect event preserves the source meaning.",
            "falsification_condition": "Explicit event control would require nesting.",
        }
    )

    assert output.family is NormalizationFamily.DIRECT
    assert output.mappings[0].source_event_positions == (0,)
    assert "score" not in SourceUnitNormalizationOutput.model_fields


def test_direct_rejects_hidden_controlled_event_structure() -> None:
    with pytest.raises(ValidationError, match="DIRECT cannot contain"):
        SourceUnitNormalizationOutput.model_validate(
            {
                "eligibility_category": "NULL_RESULT",
                "family": "DIRECT",
                "abstention_reason": "NONE",
                "events": [_event(controlled_event_ref="target")],
                "mappings": [_mapping()],
                "reasoning": "Invalid direct output.",
                "falsification_condition": "The controlled reference is decisive.",
            }
        )


def test_abstention_cannot_smuggle_events() -> None:
    with pytest.raises(ValidationError, match="ABSTAIN cannot contain"):
        SourceUnitNormalizationOutput.model_validate(
            {
                "eligibility_category": "ABSTAIN",
                "family": "ABSTAIN",
                "abstention_reason": "UNRESOLVED_SCOPE",
                "events": [_event()],
                "mappings": [_mapping()],
                "reasoning": "Scope cannot be resolved.",
                "falsification_condition": "Explicit scope would resolve it.",
            }
        )


def _axis_review(axis: MaterialAxis) -> dict[str, object]:
    return {
        "axis": axis.value,
        "decision": "PRESERVED",
        "evidence_spans": ["does not affect"],
        "reasoning": "The original and normalized structures agree.",
        "falsification_condition": "A changed value on this axis would falsify it.",
    }


def test_review_requires_every_scientific_axis_in_enum_order() -> None:
    payload = {
        "eligibility_category": "NULL_RESULT",
        "inventory_coverage": "COMPLETE",
        "unsupported_additions": "ABSENT",
        "family_validity": "VALID",
        "cue_alignment": "SURFACE_EQUIVALENT",
        "axis_reviews": [_axis_review(axis) for axis in MaterialAxis],
        "candidate_reviews": [
            {
                "normalized_event_position": 0,
                "source_entailment": "ENTAILED",
                "evidence_spans": ["does not affect"],
                "reasoning": "The source entails this event.",
                "falsification_condition": "A different outcome would falsify it.",
            }
        ],
        "reasoning": "The representation is complete and source supported.",
        "falsification_condition": "Any missing material axis would change this result.",
    }

    output = SourceUnitNormalizedReviewOutput.model_validate(payload)
    assert tuple(review.axis for review in output.axis_reviews) == tuple(MaterialAxis)
    assert "confidence" not in SourceUnitNormalizedReviewOutput.model_fields

    payload["axis_reviews"] = list(reversed(payload["axis_reviews"]))
    with pytest.raises(ValidationError, match="enum order"):
        SourceUnitNormalizedReviewOutput.model_validate(payload)


def test_review_rejects_unsupported_decisive_axis_without_evidence() -> None:
    axis_reviews = [_axis_review(axis) for axis in MaterialAxis]
    axis_reviews[0]["evidence_spans"] = []

    with pytest.raises(ValidationError, match="requires source evidence"):
        SourceUnitNormalizedReviewOutput.model_validate(
            {
                "eligibility_category": "NULL_RESULT",
                "inventory_coverage": "COMPLETE",
                "unsupported_additions": "ABSENT",
                "family_validity": "VALID",
                "cue_alignment": "EXACT",
                "axis_reviews": axis_reviews,
                "candidate_reviews": [],
                "reasoning": "The review claims preservation without evidence.",
                "falsification_condition": "Evidence would be required.",
            }
        )
