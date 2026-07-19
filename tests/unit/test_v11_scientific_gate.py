"""Deterministic stop/go tests for the V11 scientific diagnostic."""

from __future__ import annotations

from dataclasses import replace

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.gate import (
    V11GateDecision,
    V11GateInputs,
    v11_gate_decision,
    v11_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    CueAlignmentDecision,
    FamilyValidityDecision,
    InventoryCoverageDecision,
    NormalizationFamily,
    PresenceDecision,
)


def _passing_inputs() -> V11GateInputs:
    return V11GateInputs(
        repeat_index=1,
        agent_execution_complete=True,
        expected_category=SourceUnitEligibilityCategory.NULL_RESULT,
        extraction_category=SourceUnitEligibilityCategory.NULL_RESULT,
        normalization_category=SourceUnitEligibilityCategory.NULL_RESULT,
        review_category=SourceUnitEligibilityCategory.NULL_RESULT,
        normalization_family=NormalizationFamily.DIRECT,
        normalization_mapping_complete=True,
        context_dimensions_match=True,
        original_raw_payload_preserved=True,
        normalized_raw_payload_preserved=True,
        original_event_count=1,
        normalized_candidate_count=2,
        candidate_review_count=2,
        entailed_normalized_candidate_count=2,
        inventory_coverage=InventoryCoverageDecision.COMPLETE,
        unsupported_additions=PresenceDecision.ABSENT,
        family_validity=FamilyValidityDecision.VALID,
        cue_alignment=CueAlignmentDecision.SURFACE_EQUIVALENT,
        scientific_loss_count=0,
        unsupported_addition_count=0,
        unresolved_axis_count=0,
        fully_recovered_projection_count=1,
        best_projection_matched_event_count=1,
        best_projection_expected_event_count=1,
        unmatched_normalized_candidate_count=0,
        primary_attempt_count=1,
        normalization_attempt_count=1,
        normalized_review_attempt_count=1,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        distinct_provider_response_id_count=3,
        verified_provider_receipt_count=3,
        provider_receipt_gate_passed=True,
        model_transport_identity_field_count=0,
        audit_identity_mismatch_count=0,
        attempt_model_id_mismatch_count=0,
    )


def _decision(inputs: V11GateInputs) -> V11GateDecision:
    requirements = v11_gate_requirements(inputs)
    return v11_gate_decision(inputs, requirements)


def test_v11_clean_categorical_evidence_authorizes_only_small_replication() -> None:
    inputs = _passing_inputs()

    requirements = v11_gate_requirements(inputs)

    assert all(requirements.values())
    assert v11_gate_decision(inputs, requirements) is (
        V11GateDecision.GO_TO_SMALL_REPLICATION
    )


def test_v11_topology_or_receipt_failure_precedes_scientific_interpretation() -> None:
    assert (
        _decision(replace(_passing_inputs(), normalized_review_attempt_count=0))
        is V11GateDecision.STOP_WORKFLOW_INVALID
    )
    assert (
        _decision(replace(_passing_inputs(), verified_provider_receipt_count=2))
        is V11GateDecision.STOP_WORKFLOW_INVALID
    )


def test_v11_material_loss_falsifies_remedy() -> None:
    assert (
        _decision(replace(_passing_inputs(), scientific_loss_count=1))
        is V11GateDecision.STOP_REMEDY_FALSIFIED
    )


def test_v11_flat_context_bag_cannot_qualify() -> None:
    assert (
        _decision(replace(_passing_inputs(), context_dimensions_match=False))
        is V11GateDecision.STOP_REMEDY_FALSIFIED
    )


def test_v11_source_entailed_extension_requires_external_adjudication() -> None:
    assert (
        _decision(replace(_passing_inputs(), unmatched_normalized_candidate_count=1))
        is V11GateDecision.STOP_EXTERNAL_ADJUDICATION_REQUIRED
    )


def test_v11_abstention_is_unresolved_not_scientific_failure() -> None:
    inputs = replace(
        _passing_inputs(),
        normalization_family=NormalizationFamily.ABSTAIN,
        normalized_candidate_count=0,
        candidate_review_count=0,
        entailed_normalized_candidate_count=0,
    )

    assert _decision(inputs) is V11GateDecision.STOP_UNRESOLVED


def test_v11_clean_nonmatching_representation_requires_external_adjudication() -> None:
    inputs = replace(
        _passing_inputs(),
        fully_recovered_projection_count=0,
        unmatched_normalized_candidate_count=2,
    )

    assert _decision(inputs) is V11GateDecision.STOP_EXTERNAL_ADJUDICATION_REQUIRED
