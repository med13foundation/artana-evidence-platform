"""Unit tests for categorical scientific-normalization contracts."""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)
from pydantic import ValidationError

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    NormalizationFamily,
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    bind_source_unit_normalization,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v12_contracts import (
    SourceUnitNormalizationOutputV12,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    enumerate_source_units,
)

_NESTED_SOURCE = "ALG-4 regulates Fas ligand expression and cell death."


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


def _controlled_target(
    *,
    local_event_id: str,
    exact_span: str,
    relation_cue_span: str,
    event_type: str,
) -> dict[str, object]:
    return {
        "exact_span": exact_span,
        "relation_cue_span": relation_cue_span,
        "arguments": [],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": event_type,
        "assertion_scope": "CONTROLLED_TARGET",
        "polarity": "UNSCOPED",
        "epistemic_status": "UNASSERTED",
        "local_event_id": local_event_id,
        "inventory_rationale": "The process exists only as a controlled target.",
    }


def _nested_normalization_payload(
    *,
    swapped: bool = False,
    overlapping: bool = False,
) -> dict[str, object]:
    expression_ref = "death-1" if swapped else "expression-1"
    death_ref = "expression-1" if swapped else "death-1"
    expression_span = (
        "Fas ligand expression and cell death"
        if overlapping
        else "Fas ligand expression"
    )
    death_span = "ligand expression and cell death" if overlapping else "cell death"
    outer = {
        "exact_span": _NESTED_SOURCE,
        "relation_cue_span": "regulates",
        "arguments": [
            _argument(
                role="GENE_OR_PROTEIN",
                event_role="CAUSE",
                exact_span="ALG-4",
            ),
            _argument(
                role="BIOLOGICAL_PROCESS",
                event_role="THEME",
                exact_span=expression_span,
                controlled_event_ref=expression_ref,
            ),
            _argument(
                role="BIOLOGICAL_PROCESS",
                event_role="THEME",
                exact_span=death_span,
                controlled_event_ref=death_ref,
            ),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "REGULATION",
        "assertion_scope": "SOURCE_ASSERTED",
        "polarity": "SUPPORT",
        "epistemic_status": "ASSERTED",
        "local_event_id": "regulation-1",
        "inventory_rationale": "The source asserts neutral regulation.",
    }
    events = [
        outer,
        _controlled_target(
            local_event_id="expression-1",
            exact_span="Fas ligand expression",
            relation_cue_span="expression",
            event_type="EXPRESSION",
        ),
        _controlled_target(
            local_event_id="death-1",
            exact_span="cell death",
            relation_cue_span="death",
            event_type="OTHER_EXPLICIT",
        ),
    ]
    return {
        "eligibility_category": "FINDING",
        "family": "NESTED",
        "abstention_reason": "NONE",
        "events": events,
        "mappings": [
            {
                "normalized_event_position": position,
                "source_event_positions": [0],
                "operation": "SPLIT",
                "reasoning": "The normalized event preserves one source component.",
                "falsification_condition": "A missing component would falsify it.",
            }
            for position in range(len(events))
        ],
        "reasoning": "The outer event controls two explicit process targets.",
        "falsification_condition": "A mismatched target ID would falsify topology.",
    }


def _nested_original() -> SourceUnitExtractionOutput:
    payload = _nested_normalization_payload()
    events = payload["events"]
    assert isinstance(events, list)
    outer = dict(events[0])
    arguments = outer["arguments"]
    assert isinstance(arguments, list)
    outer["arguments"] = [
        {**argument, "controlled_event_ref": None} for argument in arguments
    ]
    outer["local_event_id"] = None
    return SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "decision": "EXPLICIT_EVENT",
            "events": [outer],
            "reasoning": "The source explicitly asserts one controlling event.",
        }
    )


def _make_expression_target_source_asserted(payload: dict[str, object]) -> None:
    events = payload["events"]
    assert isinstance(events, list)
    target = events[1]
    assert isinstance(target, dict)
    target.update(
        {
            "arguments": [
                _argument(exact_span="Fas ligand"),
                _argument(
                    role="BIOLOGICAL_PROCESS",
                    event_role="EFFECT",
                    exact_span="expression",
                ),
            ],
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
        }
    )


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


def test_v12_provider_schema_requires_normalized_local_event_id() -> None:
    schema = SourceUnitNormalizationOutputV12.model_json_schema()
    event_schema = schema["$defs"]["V12NormalizedClaimInventoryItem"]

    assert "local_event_id" in event_schema["required"]

    event = _event()
    del event["local_event_id"]
    with pytest.raises(ValidationError, match="local_event_id"):
        SourceUnitNormalizationOutputV12.model_validate(
            {
                "eligibility_category": "NULL_RESULT",
                "family": "DIRECT",
                "abstention_reason": "NONE",
                "events": [event],
                "mappings": [_mapping()],
                "reasoning": "The source contains one direct null event.",
                "falsification_condition": "A controlled target would require nesting.",
            }
        )


def test_historical_provider_schema_hashes_remain_immutable() -> None:
    assert output_schema_json_sha256(SourceUnitExtractionOutput) == (
        "9d2c47920d0ef3b33d7e79ad155b8ea09dad17a3d7db13a8386e724406ca88f5"
    )
    assert output_schema_json_sha256(SourceUnitNormalizationOutputV12) == (
        "a9b25add9f1b868958a3d6d24ccc5661c2f00758d90691433a043ff8714e2648"
    )


def test_v13_provider_schema_explains_reference_ownership() -> None:
    schema = SourceUnitNormalizationOutputV13.model_json_schema()
    argument_schema = schema["$defs"]["V13ClaimInventoryArgument"]
    assert (
        "outer controlling event"
        in (argument_schema["properties"]["controlled_event_ref"]["description"])
    )


def test_v12_rejects_blank_or_duplicate_normalized_local_event_ids() -> None:
    blank = _event(local_event_id=" ")
    with pytest.raises(ValidationError, match="local_event_id"):
        SourceUnitNormalizationOutputV12.model_validate(
            {
                "eligibility_category": "NULL_RESULT",
                "family": "DIRECT",
                "abstention_reason": "NONE",
                "events": [blank],
                "mappings": [_mapping()],
                "reasoning": "The source contains one direct null event.",
                "falsification_condition": "A controlled target would require nesting.",
            }
        )

    duplicate = _event(local_event_id="same-event")
    with pytest.raises(ValidationError, match="must be unique"):
        SourceUnitNormalizationOutputV12.model_validate(
            {
                "eligibility_category": "NULL_RESULT",
                "family": "DIRECT",
                "abstention_reason": "NONE",
                "events": [duplicate, duplicate],
                "mappings": [_mapping(0), _mapping(1)],
                "reasoning": "Two normalized events are represented.",
                "falsification_condition": "Distinct events require distinct IDs.",
            }
        )


def test_v13_accepts_complete_two_target_reference_topology() -> None:
    output = SourceUnitNormalizationOutputV13.model_validate(
        _nested_normalization_payload()
    )

    assert output.events[0].arguments[1].controlled_event_ref == "expression-1"
    assert output.events[0].arguments[2].controlled_event_ref == "death-1"


def test_v13_rejects_self_reference() -> None:
    payload = _nested_normalization_payload()
    events = payload["events"]
    assert isinstance(events, list)
    arguments = events[0]["arguments"]
    assert isinstance(arguments, list)
    arguments[1]["controlled_event_ref"] = "regulation-1"

    with pytest.raises(ValidationError, match="distinct event"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_v13_rejects_missing_reference_target() -> None:
    payload = _nested_normalization_payload()
    events = payload["events"]
    assert isinstance(events, list)
    arguments = events[0]["arguments"]
    assert isinstance(arguments, list)
    arguments[1]["controlled_event_ref"] = "missing-event"

    with pytest.raises(ValidationError, match="returned event"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_v13_accepts_reference_to_source_asserted_scientific_event() -> None:
    payload = _nested_normalization_payload()
    _make_expression_target_source_asserted(payload)

    output = SourceUnitNormalizationOutputV13.model_validate(payload)

    assert output.events[1].assertion_scope.value == "SOURCE_ASSERTED"
    assert output.events[0].arguments[1].controlled_event_ref == "expression-1"
    unit = enumerate_source_units(
        case_id="v13-visible-source-asserted-inner",
        source_text=_NESTED_SOURCE,
    )[0]
    original = bind_source_unit_extraction(_nested_original(), unit=unit)
    result = bind_source_unit_normalization(output, unit=unit, original=original)
    assert len(result.controlled_event_links) == 2


def test_v13_nested_family_allows_only_source_asserted_referenced_events() -> None:
    payload = _nested_normalization_payload()
    _make_expression_target_source_asserted(payload)
    events = payload["events"]
    mappings = payload["mappings"]
    assert isinstance(events, list)
    assert isinstance(mappings, list)
    outer_arguments = events[0]["arguments"]
    assert isinstance(outer_arguments, list)
    del outer_arguments[2]
    del events[2]
    del mappings[2]

    output = SourceUnitNormalizationOutputV13.model_validate(payload)

    assert output.family.value == "NESTED"
    assert all(event.assertion_scope.value == "SOURCE_ASSERTED" for event in output.events)


def test_v13_direct_rejects_valid_reference_topology() -> None:
    payload = _nested_normalization_payload()
    payload["family"] = "DIRECT"

    with pytest.raises(ValidationError, match="DIRECT cannot contain"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_v13_nested_rejects_reference_free_source_asserted_events() -> None:
    payload = _nested_normalization_payload()
    _make_expression_target_source_asserted(payload)
    events = payload["events"]
    mappings = payload["mappings"]
    assert isinstance(events, list)
    assert isinstance(mappings, list)
    outer_arguments = events[0]["arguments"]
    assert isinstance(outer_arguments, list)
    outer_arguments[1]["controlled_event_ref"] = None
    del outer_arguments[2]
    del events[2]
    del mappings[2]

    with pytest.raises(ValidationError, match="explicit event-to-event reference"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_v13_nested_rejects_reference_free_controlled_targets() -> None:
    payload = _nested_normalization_payload()
    events = payload["events"]
    assert isinstance(events, list)
    outer_arguments = events[0]["arguments"]
    assert isinstance(outer_arguments, list)
    outer_arguments[1]["controlled_event_ref"] = None
    outer_arguments[2]["controlled_event_ref"] = None

    with pytest.raises(ValidationError, match="explicit event-to-event reference"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_v13_abstain_rejects_smuggled_events() -> None:
    payload = _nested_normalization_payload()
    payload.update(
        {
            "eligibility_category": "ABSTAIN",
            "family": "ABSTAIN",
            "abstention_reason": "UNRESOLVED_SCOPE",
        }
    )

    with pytest.raises(ValidationError, match="ABSTAIN cannot contain"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_v13_rejects_orphan_controlled_target() -> None:
    payload = _nested_normalization_payload()
    events = payload["events"]
    assert isinstance(events, list)
    arguments = events[0]["arguments"]
    assert isinstance(arguments, list)
    arguments[2]["controlled_event_ref"] = None

    with pytest.raises(ValidationError, match="incoming controlled_event_ref"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_v13_rejects_reference_on_wrong_argument_role() -> None:
    payload = _nested_normalization_payload()
    events = payload["events"]
    assert isinstance(events, list)
    arguments = events[0]["arguments"]
    assert isinstance(arguments, list)
    arguments[1]["role"] = "GENE_OR_PROTEIN"

    with pytest.raises(ValidationError, match="biological-process"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_v13_rejects_reference_owned_by_non_controller_event() -> None:
    payload = _nested_normalization_payload()
    events = payload["events"]
    assert isinstance(events, list)
    events[0]["event_type"] = "ASSOCIATION"

    with pytest.raises(ValidationError, match="source-asserted regulation event"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_v13_rejects_procedural_controller() -> None:
    payload = _nested_normalization_payload()
    events = payload["events"]
    assert isinstance(events, list)
    events[0]["claim_kind"] = "PROCEDURAL_CONTEXT"

    with pytest.raises(ValidationError, match="relation-eligible"):
        SourceUnitNormalizationOutputV13.model_validate(payload)


def test_source_binding_accepts_correct_sibling_target_ids() -> None:
    unit = enumerate_source_units(
        case_id="v13-visible-correct-siblings",
        source_text=_NESTED_SOURCE,
    )[0]
    original = bind_source_unit_extraction(_nested_original(), unit=unit)
    normalized = SourceUnitNormalizationOutputV13.model_validate(
        _nested_normalization_payload()
    )

    result = bind_source_unit_normalization(normalized, unit=unit, original=original)

    assert len(result.controlled_event_links) == 2
    assert {link.controlled_inventory_id for link in result.controlled_event_links} == {
        result.accepted[1].inventory_id,
        result.accepted[2].inventory_id,
    }


def test_source_binding_rejects_swapped_sibling_target_ids() -> None:
    unit = enumerate_source_units(
        case_id="v13-visible-swapped-siblings",
        source_text=_NESTED_SOURCE,
    )[0]
    original = bind_source_unit_extraction(_nested_original(), unit=unit)
    normalized = SourceUnitNormalizationOutputV13.model_validate(
        _nested_normalization_payload(swapped=True)
    )

    with pytest.raises(StructuredModelSemanticError, match="topology is unresolved"):
        bind_source_unit_normalization(normalized, unit=unit, original=original)


def test_source_binding_rejects_swapped_ids_with_overlapping_process_spans() -> None:
    unit = enumerate_source_units(
        case_id="v13-visible-overlapping-siblings",
        source_text=_NESTED_SOURCE,
    )[0]
    original = bind_source_unit_extraction(_nested_original(), unit=unit)
    normalized = SourceUnitNormalizationOutputV13.model_validate(
        _nested_normalization_payload(swapped=True, overlapping=True)
    )

    with pytest.raises(StructuredModelSemanticError, match="topology is unresolved"):
        bind_source_unit_normalization(normalized, unit=unit, original=original)


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
