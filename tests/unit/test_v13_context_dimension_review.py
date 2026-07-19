"""Adversarial V13 context-dimension review and topology regressions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryBindingDisposition,
    ClaimInventoryBindingRejection,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)

from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    LocalReviewDisposition,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    bind_source_unit_normalization,
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review import (
    bind_v13_context_dimension_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
    SourceUnitNormalizedReviewOutputV13V6,
)
from tests.unit.v13_context_dimension_test_support import (
    _all_verbatim_mixed_context,
    _context_review,
    _fixture,
    _original,
    _payload,
    _review_payload,
    _unit,
)


def test_source_explicit_two_level_factor_remains_bindable() -> None:
    fixture = _fixture()
    event_sentence = cast("str", fixture["source"])
    contrast_sentence = (
        " The reduction of that activation was compared between genotype groups "
        "MEK1-null and MEK1-wild-type."
    )
    source = event_sentence + contrast_sentence
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    payload = deepcopy(_payload(fixture, "normalization"))
    payload["context_dimensions"] = [
        {
            "dimension_id": "genotype-groups",
            "dimension_type": "GENOTYPE",
            "operator": "ALTERNATIVE_LEVELS",
            "factor_span": "genotype groups",
            "level_spans": ["MEK1-null", "MEK1-wild-type"],
            "applies_to_local_event_ids": ["reduction-1"],
            "crossed_dimension_ids": [],
            "reasoning": "The source explicitly names two genotype groups.",
            "falsification_condition": (
                "The dimension is false if either genotype group is absent."
            ),
        }
    ]

    normalized = SourceUnitNormalizationOutputV13.model_validate(payload)
    result = bind_source_unit_normalization(normalized, unit=unit, original=original)

    assert len(result.accepted) == 2
    assert result.output.context_dimensions[0].level_spans == (
        "MEK1-null",
        "MEK1-wild-type",
    )
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        _review_payload(
            source=source,
            dimension_id="genotype-groups",
            factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
            level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
            event_scope_validity="SOURCE_EXPLICIT",
            crossing_validity="NOT_APPLICABLE",
            dimension_decision="SUPPORTED",
            context_axis_decision="PRESERVED",
            unsupported_additions="ABSENT",
            factor_span="genotype groups",
            level_spans=("MEK1-null", "MEK1-wild-type"),
            contrast_evidence_span=contrast_sentence.strip(),
            event_scope_evidence_span=event_sentence,
        )
    )
    reviewed = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=result,
    )
    assert reviewed.unsupported_context_dimension_count == 0
    assert reviewed.unresolved_context_dimension_count == 0
    assert reviewed.provisional_context_dimension_count == 1
    assert (
        reviewed.local_review_disposition is LocalReviewDisposition.ABSTAIN
    )

    false_crossing = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        _review_payload(
            source=source,
            dimension_id="genotype-groups",
            factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
            level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
            event_scope_validity="SOURCE_EXPLICIT",
            crossing_validity="SOURCE_EXPLICIT",
            dimension_decision="SUPPORTED",
            context_axis_decision="PRESERVED",
            unsupported_additions="ABSENT",
            factor_span="genotype groups",
            level_spans=("MEK1-null", "MEK1-wild-type"),
            contrast_evidence_span=contrast_sentence.strip(),
            event_scope_evidence_span=event_sentence,
            crossing_evidence_span=contrast_sentence.strip(),
        )
    )
    with pytest.raises(
        StructuredModelSemanticError,
        match="uncrossed context requires NOT_APPLICABLE",
    ):
        bind_v13_context_dimension_review(
            false_crossing,
            unit=unit,
            original=original,
            normalized=result,
        )

    contradictory_aggregate_payload = _review_payload(
        source=source,
        dimension_id="genotype-groups",
        factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
        level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
        event_scope_validity="SOURCE_EXPLICIT",
        crossing_validity="NOT_APPLICABLE",
        dimension_decision="SUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions="PRESENT",
        factor_span="genotype groups",
        level_spans=("MEK1-null", "MEK1-wild-type"),
        contrast_evidence_span=contrast_sentence.strip(),
        event_scope_evidence_span=event_sentence,
    )
    contradictory_aggregate = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        contradictory_aggregate_payload
    )
    with pytest.raises(
        StructuredModelSemanticError,
        match="unsupported_additions must match deterministic review findings",
    ):
        bind_v13_context_dimension_review(
            contradictory_aggregate,
            unit=unit,
            original=original,
            normalized=result,
        )


def test_normalization_copy_cannot_swap_output_after_source_binding() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalized = _all_verbatim_mixed_context(fixture=fixture, unit=unit)
    normalized_payload = normalized.output.model_dump(mode="json")
    context_free_payload = deepcopy(normalized_payload)
    context_free_payload["context_dimensions"] = []
    context_free_output = SourceUnitNormalizationOutputV13.model_validate(
        context_free_payload
    )
    copied = replace(normalized, output=context_free_output)
    review_payload = _review_payload(
        source=source,
        dimension_id="unused",
        factor_eligibility="PARTICIPANT_ONLY",
        level_set_validity="MIXED_OR_UNRELATED",
        event_scope_validity="UNSUPPORTED",
        crossing_validity="NOT_APPLICABLE",
        dimension_decision="UNSUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions="ABSENT",
    )
    review_payload["context_dimension_reviews"] = []
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(review_payload)

    with pytest.raises(
        StructuredModelSemanticError,
        match="canonical source envelope",
    ):
        bind_v13_context_dimension_review(
            review,
            unit=unit,
            original=original,
            normalized=copied,
        )


def test_review_result_counters_cannot_be_replaced_to_create_false_pass() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalized = _all_verbatim_mixed_context(fixture=fixture, unit=unit)
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        _review_payload(
            source=source,
            dimension_id="mixed-participants",
            factor_eligibility="PARTICIPANT_ONLY",
            level_set_validity="MIXED_OR_UNRELATED",
            event_scope_validity="UNSUPPORTED",
            crossing_validity="NOT_APPLICABLE",
            dimension_decision="UNSUPPORTED",
            context_axis_decision="MATERIAL_ADDITION",
            unsupported_additions="PRESENT",
        )
    )
    result = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=normalized,
    )

    assert result.local_review_disposition is LocalReviewDisposition.FAIL
    assert {field.name for field in fields(result)} == {
        "normalization_envelope_sha256",
        "output",
        "output_sha256",
        "source_unit_input_sha256",
    }
    with pytest.raises(TypeError, match="unexpected keyword"):
        replace(result, unsupported_context_dimension_count=0)

    clean_payload = deepcopy(review.model_dump(mode="json"))
    clean_payload["context_dimension_reviews"] = []
    clean_payload["unsupported_additions"] = "ABSENT"
    context_axis = next(
        axis
        for axis in cast("list[dict[str, object]]", clean_payload["axis_reviews"])
        if axis["axis"] == "CONTEXT_SCOPE"
    )
    context_axis["decision"] = "PRESERVED"
    clean_output = SourceUnitNormalizedReviewOutputV13V6.model_validate(clean_payload)
    with pytest.raises(ValueError, match="categorical output"):
        replace(result, output=clean_output)


def test_original_rejection_copy_cannot_change_downstream_prompt_custody() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalized = _all_verbatim_mixed_context(fixture=fixture, unit=unit)
    fabricated_rejection = ClaimInventoryBindingRejection(
        rejection_id="attacker-rejection",
        source_sha256=unit.source_sha256,
        chunk_index=unit.index,
        batch_index=0,
        item=original.output.events[0],
        disposition=ClaimInventoryBindingDisposition.SOURCE_SPAN_MISMATCH,
        validation_evidence="attacker-controlled rejection",
    )
    copied = replace(original, rejected=(*original.rejected, fabricated_rejection))

    with pytest.raises(
        StructuredModelSemanticError,
        match="canonical source envelope",
    ):
        bind_source_unit_normalization(
            normalized.output,
            unit=unit,
            original=copied,
        )


def test_model_copy_cannot_inject_unvalidated_review_categories() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalized = _all_verbatim_mixed_context(fixture=fixture, unit=unit)
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        _review_payload(
            source=source,
            dimension_id="mixed-participants",
            factor_eligibility="PARTICIPANT_ONLY",
            level_set_validity="MIXED_OR_UNRELATED",
            event_scope_validity="UNSUPPORTED",
            crossing_validity="NOT_APPLICABLE",
            dimension_decision="UNSUPPORTED",
            context_axis_decision="MATERIAL_ADDITION",
            unsupported_additions="PRESENT",
        )
    )
    result = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=normalized,
    )
    unvalidated = result.output.model_copy(update={"family_validity": "INVALID"})

    with pytest.raises(ValueError, match="unvalidated categorical values"):
        replace(
            result,
            output=unvalidated,
            output_sha256=canonical_json_sha256(
                unvalidated.model_dump(mode="json", warnings=False)
            ),
        )


def test_all_verbatim_mixed_levels_require_source_only_rejection() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalized = _all_verbatim_mixed_context(fixture=fixture, unit=unit)
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        _review_payload(
            source=source,
            dimension_id="mixed-participants",
            factor_eligibility="PARTICIPANT_ONLY",
            level_set_validity="MIXED_OR_UNRELATED",
            event_scope_validity="UNSUPPORTED",
            crossing_validity="NOT_APPLICABLE",
            dimension_decision="UNSUPPORTED",
            context_axis_decision="MATERIAL_ADDITION",
            unsupported_additions="PRESENT",
        )
    )

    result = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=normalized,
    )

    assert result.unsupported_context_dimension_count == 1
    assert result.unsupported_addition_count == 1
    assert result.local_review_disposition is LocalReviewDisposition.FAIL


def test_supported_context_requires_identity_bound_subdecision_evidence() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalized = _all_verbatim_mixed_context(fixture=fixture, unit=unit)
    payload = _review_payload(
        source=source,
        dimension_id="mixed-participants",
        factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
        level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
        event_scope_validity="SOURCE_EXPLICIT",
        crossing_validity="NOT_APPLICABLE",
        dimension_decision="SUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions="ABSENT",
    )
    context_reviews = cast(
        "list[dict[str, object]]",
        payload["context_dimension_reviews"],
    )
    context_reviews[0]["contrast_evidence_spans"] = ["MEK1-null genotype"]
    context_reviews[0]["event_scope_evidence_spans"] = [
        "MEK1-null genotype reduced that activation"
    ]
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(payload)

    with pytest.raises(
        StructuredModelSemanticError,
        match="one supported contrast span must jointly cover factor and every level",
    ):
        bind_v13_context_dimension_review(
            review,
            unit=unit,
            original=original,
            normalized=normalized,
        )

    wrong_identity_payload = deepcopy(payload)
    wrong_identity_reviews = cast(
        "list[dict[str, object]]",
        wrong_identity_payload["context_dimension_reviews"],
    )
    level_reviews = cast(
        "list[dict[str, object]]",
        wrong_identity_reviews[0]["level_reviews"],
    )
    level_reviews[1]["level_span"] = "ERK"
    wrong_identity_reviews[0]["contrast_evidence_spans"] = [source]
    wrong_identity = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        wrong_identity_payload
    )
    with pytest.raises(
        StructuredModelSemanticError,
        match="level review identity does not match",
    ):
        bind_v13_context_dimension_review(
            wrong_identity,
            unit=unit,
            original=original,
            normalized=normalized,
        )


def test_near_whole_source_cannot_rubber_stamp_mixed_factor_levels() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalized = _all_verbatim_mixed_context(fixture=fixture, unit=unit)
    payload = _review_payload(
        source=source,
        dimension_id="mixed-participants",
        factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
        level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
        event_scope_validity="SOURCE_EXPLICIT",
        crossing_validity="NOT_APPLICABLE",
        dimension_decision="SUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions="ABSENT",
        contrast_evidence_span=source[:-1],
        event_scope_evidence_span="MEK1-null genotype reduced that activation",
    )
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(payload)

    with pytest.raises(
        StructuredModelSemanticError,
        match="require narrower evidence than the source unit",
    ):
        bind_v13_context_dimension_review(
            review,
            unit=unit,
            original=original,
            normalized=normalized,
        )

    narrower_payload = deepcopy(payload)
    narrower_reviews = cast(
        "list[dict[str, object]]",
        narrower_payload["context_dimension_reviews"],
    )
    narrower_reviews[0]["contrast_evidence_spans"] = [
        "EGF activated ERK, and the MEK1-null genotype"
    ]
    narrower = SourceUnitNormalizedReviewOutputV13V6.model_validate(narrower_payload)
    provisional = bind_v13_context_dimension_review(
        narrower,
        unit=unit,
        original=original,
        normalized=normalized,
    )
    assert provisional.provisional_context_dimension_count == 1
    assert (
        provisional.local_review_disposition
        is LocalReviewDisposition.ABSTAIN
    )


def test_context_review_cannot_omit_dimension_or_hide_unsupported_aggregate() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalized = _all_verbatim_mixed_context(fixture=fixture, unit=unit)
    omitted_payload = _review_payload(
        source=source,
        dimension_id="mixed-participants",
        factor_eligibility="PARTICIPANT_ONLY",
        level_set_validity="MIXED_OR_UNRELATED",
        event_scope_validity="UNSUPPORTED",
        crossing_validity="NOT_APPLICABLE",
        dimension_decision="UNSUPPORTED",
        context_axis_decision="MATERIAL_ADDITION",
        unsupported_additions="PRESENT",
    )
    omitted_payload["context_dimension_reviews"] = []
    omitted = SourceUnitNormalizedReviewOutputV13V6.model_validate(omitted_payload)
    with pytest.raises(StructuredModelSemanticError, match="cover every context"):
        bind_v13_context_dimension_review(
            omitted,
            unit=unit,
            original=original,
            normalized=normalized,
        )

    hidden_payload = _review_payload(
        source=source,
        dimension_id="mixed-participants",
        factor_eligibility="PARTICIPANT_ONLY",
        level_set_validity="MIXED_OR_UNRELATED",
        event_scope_validity="UNSUPPORTED",
        crossing_validity="NOT_APPLICABLE",
        dimension_decision="UNSUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions="ABSENT",
    )
    hidden = SourceUnitNormalizedReviewOutputV13V6.model_validate(hidden_payload)
    with pytest.raises(
        StructuredModelSemanticError,
        match="unsupported_additions PRESENT",
    ):
        bind_v13_context_dimension_review(
            hidden,
            unit=unit,
            original=original,
            normalized=normalized,
        )


@pytest.mark.parametrize(
    ("factor_eligibility", "level_set_validity", "event_scope_validity"),
    [
        ("IMPLICIT_OR_INFERRED", "IMPLICIT_OR_INFERRED", "SOURCE_EXPLICIT"),
        (
            "EXPLICIT_MULTI_LEVEL_FACTOR",
            "SERIES_OR_OVERLAPPING",
            "SOURCE_EXPLICIT",
        ),
        (
            "EXPLICIT_MULTI_LEVEL_FACTOR",
            "SAME_FACTOR_MUTUALLY_EXCLUSIVE",
            "UNSUPPORTED",
        ),
    ],
)
def test_disqualified_context_categories_force_fail_closed_aggregate(
    factor_eligibility: str,
    level_set_validity: str,
    event_scope_validity: str,
) -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalized = _all_verbatim_mixed_context(fixture=fixture, unit=unit)
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        _review_payload(
            source=source,
            dimension_id="mixed-participants",
            factor_eligibility=factor_eligibility,
            level_set_validity=level_set_validity,
            event_scope_validity=event_scope_validity,
            crossing_validity="NOT_APPLICABLE",
            dimension_decision="UNSUPPORTED",
            context_axis_decision="MATERIAL_ADDITION",
            unsupported_additions="PRESENT",
        )
    )

    result = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=normalized,
    )

    assert result.unsupported_context_dimension_count == 1
    assert result.output.unsupported_additions.value == "PRESENT"


@pytest.mark.parametrize(
    (
        "inventory_coverage",
        "unsupported_additions",
        "missing_count",
        "extra_count",
        "unresolved_count",
        "expected_disposition",
    ),
    [
        ("COMPLETE", "ABSENT", 0, 0, 0, LocalReviewDisposition.PASS),
        ("MISSING_EVENT", "ABSENT", 1, 0, 0, LocalReviewDisposition.FAIL),
        ("EXTRA_EVENT", "PRESENT", 0, 1, 0, LocalReviewDisposition.FAIL),
        (
            "MISSING_AND_EXTRA",
            "PRESENT",
            1,
            1,
            0,
            LocalReviewDisposition.FAIL,
        ),
        ("ABSTAIN", "ABSTAIN", 0, 0, 1, LocalReviewDisposition.ABSTAIN),
    ],
)
def test_inventory_category_has_separate_deterministic_failure_counts(
    inventory_coverage: str,
    unsupported_additions: str,
    missing_count: int,
    extra_count: int,
    unresolved_count: int,
    expected_disposition: LocalReviewDisposition,
) -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalization_payload = deepcopy(_payload(fixture, "normalization"))
    normalization_payload["context_dimensions"] = []
    normalized = bind_source_unit_normalization(
        SourceUnitNormalizationOutputV13.model_validate(normalization_payload),
        unit=unit,
        original=original,
    )
    review_payload = _review_payload(
        source=source,
        dimension_id="unused",
        factor_eligibility="PARTICIPANT_ONLY",
        level_set_validity="MIXED_OR_UNRELATED",
        event_scope_validity="UNSUPPORTED",
        crossing_validity="NOT_APPLICABLE",
        dimension_decision="UNSUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions=unsupported_additions,
    )
    review_payload["context_dimension_reviews"] = []
    review_payload["inventory_coverage"] = inventory_coverage
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(review_payload)

    result = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=normalized,
    )

    assert result.missing_inventory_count == missing_count
    assert result.extra_inventory_count == extra_count
    assert result.unresolved_inventory_count == unresolved_count
    assert result.scientific_loss_count == 0
    assert result.local_review_disposition is expected_disposition


def test_contradicted_candidate_cannot_be_invisible_to_qualification() -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalization_payload = deepcopy(_payload(fixture, "normalization"))
    normalization_payload["context_dimensions"] = []
    normalized = bind_source_unit_normalization(
        SourceUnitNormalizationOutputV13.model_validate(normalization_payload),
        unit=unit,
        original=original,
    )
    review_payload = _review_payload(
        source=source,
        dimension_id="unused",
        factor_eligibility="PARTICIPANT_ONLY",
        level_set_validity="MIXED_OR_UNRELATED",
        event_scope_validity="UNSUPPORTED",
        crossing_validity="NOT_APPLICABLE",
        dimension_decision="UNSUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions="PRESENT",
    )
    review_payload["context_dimension_reviews"] = []
    candidate_reviews = cast(
        "list[dict[str, object]]",
        review_payload["candidate_reviews"],
    )
    candidate_reviews[0]["source_entailment"] = "CONTRADICTED"
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(review_payload)

    result = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=normalized,
    )

    assert result.unsupported_candidate_count == 1
    assert result.unsupported_addition_count == 0
    assert result.local_review_disposition is LocalReviewDisposition.FAIL


@pytest.mark.parametrize(
    ("field", "value", "expected_disposition", "counter_name"),
    [
        (
            "family_validity",
            "INVALID",
            LocalReviewDisposition.FAIL,
            "invalid_family_count",
        ),
        (
            "family_validity",
            "ABSTAIN",
            LocalReviewDisposition.ABSTAIN,
            "unresolved_family_count",
        ),
        (
            "cue_alignment",
            "MATERIAL_MISMATCH",
            LocalReviewDisposition.FAIL,
            "cue_mismatch_count",
        ),
        (
            "cue_alignment",
            "ABSTAIN",
            LocalReviewDisposition.ABSTAIN,
            "unresolved_cue_count",
        ),
    ],
)
def test_family_and_cue_findings_always_reach_qualification(
    field: str,
    value: str,
    expected_disposition: LocalReviewDisposition,
    counter_name: str,
) -> None:
    fixture = _fixture()
    source = cast("str", fixture["source"])
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    normalization_payload = deepcopy(_payload(fixture, "normalization"))
    normalization_payload["context_dimensions"] = []
    normalized = bind_source_unit_normalization(
        SourceUnitNormalizationOutputV13.model_validate(normalization_payload),
        unit=unit,
        original=original,
    )
    review_payload = _review_payload(
        source=source,
        dimension_id="unused",
        factor_eligibility="PARTICIPANT_ONLY",
        level_set_validity="MIXED_OR_UNRELATED",
        event_scope_validity="UNSUPPORTED",
        crossing_validity="NOT_APPLICABLE",
        dimension_decision="UNSUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions="ABSENT",
    )
    review_payload["context_dimension_reviews"] = []
    review_payload[field] = value
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(review_payload)

    result = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=normalized,
    )

    assert getattr(result, counter_name) == 1
    assert result.local_review_disposition is expected_disposition


def test_crossing_review_must_match_explicit_symmetric_topology() -> None:
    fixture = _fixture()
    event_sentence = cast("str", fixture["source"])
    crossing_sentence = (
        " The reduction was compared across genotype groups MEK1-null and "
        "MEK1-wild-type and treatment groups trametinib and vehicle in a crossed "
        "design."
    )
    source = event_sentence + crossing_sentence
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    payload = deepcopy(_payload(fixture, "normalization"))
    payload["context_dimensions"] = [
        {
            "dimension_id": "genotype-groups",
            "dimension_type": "GENOTYPE",
            "operator": "ALTERNATIVE_LEVELS",
            "factor_span": "genotype groups",
            "level_spans": ["MEK1-null", "MEK1-wild-type"],
            "applies_to_local_event_ids": ["reduction-1"],
            "crossed_dimension_ids": ["treatment-groups"],
            "reasoning": "The source explicitly contrasts genotype groups.",
            "falsification_condition": "The genotype contrast may be absent.",
        },
        {
            "dimension_id": "treatment-groups",
            "dimension_type": "TREATMENT",
            "operator": "ALTERNATIVE_LEVELS",
            "factor_span": "treatment groups",
            "level_spans": ["trametinib", "vehicle"],
            "applies_to_local_event_ids": ["reduction-1"],
            "crossed_dimension_ids": ["genotype-groups"],
            "reasoning": "The source explicitly contrasts treatment groups.",
            "falsification_condition": "The treatment contrast may be absent.",
        },
    ]
    normalized = bind_source_unit_normalization(
        SourceUnitNormalizationOutputV13.model_validate(payload),
        unit=unit,
        original=original,
    )
    review_payload = _review_payload(
        source=source,
        dimension_id="genotype-groups",
        factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
        level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
        event_scope_validity="SOURCE_EXPLICIT",
        crossing_validity="SOURCE_EXPLICIT",
        dimension_decision="SUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions="ABSENT",
    )
    review_payload["context_dimension_reviews"] = [
        _context_review(
            source=source,
            position=0,
            dimension_id="genotype-groups",
            factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
            level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
            event_scope_validity="SOURCE_EXPLICIT",
            crossing_validity="SOURCE_EXPLICIT",
            dimension_decision="SUPPORTED",
            factor_span="genotype groups",
            level_spans=("MEK1-null", "MEK1-wild-type"),
            contrast_evidence_span=crossing_sentence.strip(),
            event_scope_evidence_span=event_sentence,
            crossing_evidence_span=crossing_sentence.strip(),
        ),
        _context_review(
            source=source,
            position=1,
            dimension_id="treatment-groups",
            factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
            level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
            event_scope_validity="SOURCE_EXPLICIT",
            crossing_validity="SOURCE_EXPLICIT",
            dimension_decision="SUPPORTED",
            factor_span="treatment groups",
            level_spans=("trametinib", "vehicle"),
            contrast_evidence_span=crossing_sentence.strip(),
            event_scope_evidence_span=event_sentence,
            crossing_evidence_span=crossing_sentence.strip(),
        ),
    ]
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(review_payload)

    result = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=normalized,
    )
    assert result.unsupported_context_dimension_count == 0
    assert result.provisional_context_dimension_count == 2
    assert (
        result.local_review_disposition is LocalReviewDisposition.ABSTAIN
    )

    invalid_payload = deepcopy(review_payload)
    invalid_reviews = cast(
        "list[dict[str, object]]", invalid_payload["context_dimension_reviews"]
    )
    invalid_reviews[0]["crossing_validity"] = "NOT_APPLICABLE"
    invalid_reviews[0]["crossing_evidence_spans"] = []
    invalid = SourceUnitNormalizedReviewOutputV13V6.model_validate(invalid_payload)
    with pytest.raises(
        StructuredModelSemanticError,
        match="declared context crossing cannot be NOT_APPLICABLE",
    ):
        bind_v13_context_dimension_review(
            invalid,
            unit=unit,
            original=original,
            normalized=normalized,
        )

    unsupported_crossing_payload = deepcopy(review_payload)
    unsupported_crossing_reviews = cast(
        "list[dict[str, object]]",
        unsupported_crossing_payload["context_dimension_reviews"],
    )
    unsupported_crossing_reviews[0]["crossing_validity"] = "UNSUPPORTED"
    unsupported_crossing_reviews[0]["decision"] = "UNSUPPORTED"
    unsupported_crossing_payload["unsupported_additions"] = "PRESENT"
    unsupported_axes = cast(
        "list[dict[str, object]]",
        unsupported_crossing_payload["axis_reviews"],
    )
    context_axis = next(
        axis for axis in unsupported_axes if axis["axis"] == "CONTEXT_SCOPE"
    )
    context_axis["decision"] = "MATERIAL_ADDITION"
    unsupported_crossing = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        unsupported_crossing_payload
    )
    fail_closed_result = bind_v13_context_dimension_review(
        unsupported_crossing,
        unit=unit,
        original=original,
        normalized=normalized,
    )
    assert fail_closed_result.unsupported_context_dimension_count == 1
    assert fail_closed_result.unsupported_addition_count > 0

    not_applicable_payload = deepcopy(unsupported_crossing_payload)
    not_applicable_reviews = cast(
        "list[dict[str, object]]",
        not_applicable_payload["context_dimension_reviews"],
    )
    not_applicable_reviews[0]["factor_eligibility"] = "PARTICIPANT_ONLY"
    not_applicable_reviews[0]["crossing_validity"] = "NOT_APPLICABLE"
    not_applicable_reviews[0]["crossing_evidence_spans"] = []
    not_applicable = SourceUnitNormalizedReviewOutputV13V6.model_validate(
        not_applicable_payload
    )
    with pytest.raises(
        StructuredModelSemanticError,
        match="declared context crossing cannot be NOT_APPLICABLE",
    ):
        bind_v13_context_dimension_review(
            not_applicable,
            unit=unit,
            original=original,
            normalized=normalized,
        )

    abstain_payload = deepcopy(review_payload)
    abstain_reviews = cast(
        "list[dict[str, object]]",
        abstain_payload["context_dimension_reviews"],
    )
    abstain_reviews[0].update(
        {
            "factor_eligibility": "ABSTAIN",
            "level_set_validity": "ABSTAIN",
            "event_scope_validity": "ABSTAIN",
            "crossing_validity": "ABSTAIN",
            "decision": "ABSTAIN",
        }
    )
    abstain_level_reviews = cast(
        "list[dict[str, object]]",
        abstain_reviews[0]["level_reviews"],
    )
    for level_review in abstain_level_reviews:
        level_review["membership"] = "ABSTAIN"
    abstain_payload["unsupported_additions"] = "ABSTAIN"
    abstain_axes = cast("list[dict[str, object]]", abstain_payload["axis_reviews"])
    abstain_context_axis = next(
        axis for axis in abstain_axes if axis["axis"] == "CONTEXT_SCOPE"
    )
    abstain_context_axis["decision"] = "ABSTAIN"
    abstained = SourceUnitNormalizedReviewOutputV13V6.model_validate(abstain_payload)
    abstained_result = bind_v13_context_dimension_review(
        abstained,
        unit=unit,
        original=original,
        normalized=normalized,
    )
    assert abstained_result.unresolved_context_dimension_count == 1
    assert (
        abstained_result.local_review_disposition
        is LocalReviewDisposition.ABSTAIN
    )


def test_separate_factor_comparisons_cannot_be_rubber_stamped_as_crossed() -> None:
    fixture = _fixture()
    event_sentence = cast("str", fixture["source"])
    genotype_sentence = (
        " The reduction was compared between genotype groups MEK1-null and "
        "MEK1-wild-type."
    )
    treatment_sentence = (
        " Treatment groups trametinib and vehicle were evaluated separately."
    )
    source = event_sentence + genotype_sentence + treatment_sentence
    unit = _unit(source)
    original = _original(fixture=fixture, unit=unit)
    payload = deepcopy(_payload(fixture, "normalization"))
    payload["context_dimensions"] = [
        {
            "dimension_id": "genotype-groups",
            "dimension_type": "GENOTYPE",
            "operator": "ALTERNATIVE_LEVELS",
            "factor_span": "genotype groups",
            "level_spans": ["MEK1-null", "MEK1-wild-type"],
            "applies_to_local_event_ids": ["reduction-1"],
            "crossed_dimension_ids": ["treatment-groups"],
            "reasoning": "Adversarial fabricated crossing.",
            "falsification_condition": "The comparisons are separate.",
        },
        {
            "dimension_id": "treatment-groups",
            "dimension_type": "TREATMENT",
            "operator": "ALTERNATIVE_LEVELS",
            "factor_span": "Treatment groups",
            "level_spans": ["trametinib", "vehicle"],
            "applies_to_local_event_ids": ["reduction-1"],
            "crossed_dimension_ids": ["genotype-groups"],
            "reasoning": "Adversarial fabricated crossing.",
            "falsification_condition": "The comparisons are separate.",
        },
    ]
    normalized = bind_source_unit_normalization(
        SourceUnitNormalizationOutputV13.model_validate(payload),
        unit=unit,
        original=original,
    )
    review_payload = _review_payload(
        source=source,
        dimension_id="unused",
        factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
        level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
        event_scope_validity="SOURCE_EXPLICIT",
        crossing_validity="SOURCE_EXPLICIT",
        dimension_decision="SUPPORTED",
        context_axis_decision="PRESERVED",
        unsupported_additions="ABSENT",
    )
    review_payload["context_dimension_reviews"] = [
        _context_review(
            source=source,
            position=0,
            dimension_id="genotype-groups",
            factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
            level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
            event_scope_validity="SOURCE_EXPLICIT",
            crossing_validity="SOURCE_EXPLICIT",
            dimension_decision="SUPPORTED",
            factor_span="genotype groups",
            level_spans=("MEK1-null", "MEK1-wild-type"),
            contrast_evidence_span=genotype_sentence.strip(),
            event_scope_evidence_span=event_sentence,
            crossing_evidence_span=(genotype_sentence + treatment_sentence).strip(),
        ),
        _context_review(
            source=source,
            position=1,
            dimension_id="treatment-groups",
            factor_eligibility="EXPLICIT_MULTI_LEVEL_FACTOR",
            level_set_validity="SAME_FACTOR_MUTUALLY_EXCLUSIVE",
            event_scope_validity="SOURCE_EXPLICIT",
            crossing_validity="SOURCE_EXPLICIT",
            dimension_decision="SUPPORTED",
            factor_span="Treatment groups",
            level_spans=("trametinib", "vehicle"),
            contrast_evidence_span=treatment_sentence.strip(),
            event_scope_evidence_span=event_sentence,
            crossing_evidence_span=(genotype_sentence + treatment_sentence).strip(),
        ),
    ]
    review = SourceUnitNormalizedReviewOutputV13V6.model_validate(review_payload)

    result = bind_v13_context_dimension_review(
        review,
        unit=unit,
        original=original,
        normalized=normalized,
    )
    assert result.provisional_context_dimension_count == 2
    assert (
        result.local_review_disposition is LocalReviewDisposition.ABSTAIN
    )
