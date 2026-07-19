"""Deterministic stop/go gate for the V12 three-agent diagnostic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    CueAlignmentDecision,
    FamilyValidityDecision,
    InventoryCoverageDecision,
    NormalizationFamily,
    PresenceDecision,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.contracts import (
        SourceUnitEligibilityCategory,
    )

_EXPECTED_PROVIDER_CALL_COUNT = 3


class V12GateDecision(StrEnum):
    """Ordered V12 outcomes; only GO authorizes a small replication."""

    STOP_WORKFLOW_INVALID = "STOP_WORKFLOW_INVALID"
    STOP_REMEDY_FALSIFIED = "STOP_REMEDY_FALSIFIED"
    STOP_UNRESOLVED = "STOP_UNRESOLVED"
    STOP_EXTERNAL_ADJUDICATION_REQUIRED = "STOP_EXTERNAL_ADJUDICATION_REQUIRED"
    GO_TO_SMALL_REPLICATION = "GO_TO_SMALL_REPLICATION"


@dataclass(frozen=True, slots=True)
class V12GateInputs:
    """Agent categories and deterministic counts used by the V12 gate."""

    repeat_index: int
    agent_execution_complete: bool
    expected_category: SourceUnitEligibilityCategory
    extraction_category: SourceUnitEligibilityCategory | None
    normalization_category: SourceUnitEligibilityCategory | None
    review_category: SourceUnitEligibilityCategory | None
    normalization_family: NormalizationFamily | None
    normalization_mapping_complete: bool
    context_dimensions_match: bool
    original_raw_payload_preserved: bool
    normalized_raw_payload_preserved: bool
    review_raw_payload_preserved: bool
    original_event_count: int
    normalized_candidate_count: int
    candidate_review_count: int
    entailed_normalized_candidate_count: int
    inventory_coverage: InventoryCoverageDecision | None
    unsupported_additions: PresenceDecision | None
    family_validity: FamilyValidityDecision | None
    cue_alignment: CueAlignmentDecision | None
    scientific_loss_count: int
    unsupported_addition_count: int
    unresolved_axis_count: int
    fully_recovered_projection_count: int
    best_projection_matched_event_count: int
    best_projection_expected_event_count: int
    unmatched_normalized_candidate_count: int
    primary_attempt_count: int
    normalization_attempt_count: int
    normalized_review_attempt_count: int
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    distinct_provider_response_id_count: int
    verified_provider_receipt_count: int
    provider_receipt_gate_passed: bool
    model_transport_identity_field_count: int
    audit_identity_mismatch_count: int
    attempt_model_id_mismatch_count: int


def v12_gate_requirements(inputs: V12GateInputs) -> dict[str, bool]:
    """Calculate exact scientific, topology, and custody requirements."""

    categories = (
        inputs.extraction_category,
        inputs.normalization_category,
        inputs.review_category,
    )
    return {
        "repeat_index_pre_registered": inputs.repeat_index == 1,
        "agent_execution_complete": inputs.agent_execution_complete,
        "expected_category_is_scientific": inputs.expected_category.scientific,
        "all_agents_recognized_expected_science": all(
            category is inputs.expected_category for category in categories
        ),
        "one_representation_family_selected": inputs.normalization_family
        in {NormalizationFamily.DIRECT, NormalizationFamily.NESTED},
        "normalization_mapping_complete": inputs.normalization_mapping_complete,
        "context_dimensions_preserved": inputs.context_dimensions_match,
        "raw_agent_outputs_preserved": (
            inputs.original_raw_payload_preserved
            and inputs.normalized_raw_payload_preserved
            and inputs.review_raw_payload_preserved
        ),
        "source_inventory_nonempty": inputs.original_event_count > 0,
        "normalized_inventory_nonempty": inputs.normalized_candidate_count > 0,
        "normalized_review_coverage_exact": (
            inputs.candidate_review_count == inputs.normalized_candidate_count
        ),
        "all_normalized_candidates_source_entailed": (
            inputs.entailed_normalized_candidate_count
            == inputs.normalized_candidate_count
        ),
        "inventory_coverage_complete": inputs.inventory_coverage
        is InventoryCoverageDecision.COMPLETE,
        "unsupported_additions_absent": inputs.unsupported_additions
        is PresenceDecision.ABSENT,
        "declared_family_valid": inputs.family_validity is FamilyValidityDecision.VALID,
        "scientific_loss_zero": inputs.scientific_loss_count == 0,
        "unsupported_addition_axis_zero": inputs.unsupported_addition_count == 0,
        "unresolved_axis_zero": inputs.unresolved_axis_count == 0,
        "cue_material_mismatch_absent": inputs.cue_alignment
        in {CueAlignmentDecision.EXACT, CueAlignmentDecision.SURFACE_EQUIVALENT},
        "complete_acceptable_projection_recovered": (
            inputs.fully_recovered_projection_count > 0
        ),
        "single_representation_family_recovered": (
            inputs.fully_recovered_projection_count == 1
        ),
        "best_projection_event_inventory_complete": (
            inputs.best_projection_expected_event_count > 0
            and inputs.best_projection_matched_event_count
            == inputs.best_projection_expected_event_count
        ),
        "unmatched_normalized_candidate_zero": (
            inputs.unmatched_normalized_candidate_count == 0
        ),
        "audit_attempt_topology_exact": (
            inputs.primary_attempt_count == 1
            and inputs.normalization_attempt_count == 1
            and inputs.normalized_review_attempt_count == 1
        ),
        "invalid_agent_output_zero": inputs.invalid_agent_output_count == 0,
        "provider_lineage_complete": (
            inputs.unidentified_provider_attempt_count == 0
            and inputs.distinct_provider_response_id_count
            == _EXPECTED_PROVIDER_CALL_COUNT
        ),
        "provider_receipts_verified": (
            inputs.provider_receipt_gate_passed
            and inputs.verified_provider_receipt_count == _EXPECTED_PROVIDER_CALL_COUNT
        ),
        "model_transport_identity_absent": (
            inputs.model_transport_identity_field_count == 0
        ),
        "audit_identity_bound": inputs.audit_identity_mismatch_count == 0,
        "attempt_model_identity_bound": inputs.attempt_model_id_mismatch_count == 0,
    }


def v12_gate_decision(
    inputs: V12GateInputs,
    requirements: dict[str, bool],
) -> V12GateDecision:
    """Classify failure from workflow to scientific meaning in fixed order."""

    workflow_requirements = {
        "repeat_index_pre_registered",
        "agent_execution_complete",
        "normalization_mapping_complete",
        "raw_agent_outputs_preserved",
        "audit_attempt_topology_exact",
        "invalid_agent_output_zero",
        "provider_lineage_complete",
        "provider_receipts_verified",
        "model_transport_identity_absent",
        "audit_identity_bound",
        "attempt_model_identity_bound",
    }
    if any(not requirements[name] for name in workflow_requirements):
        return V12GateDecision.STOP_WORKFLOW_INVALID
    unresolved = (
        inputs.normalization_family is NormalizationFamily.ABSTAIN
        or inputs.inventory_coverage is InventoryCoverageDecision.ABSTAIN
        or inputs.unsupported_additions is PresenceDecision.ABSTAIN
        or inputs.family_validity is FamilyValidityDecision.ABSTAIN
        or inputs.cue_alignment is CueAlignmentDecision.ABSTAIN
        or inputs.unresolved_axis_count > 0
    )
    if unresolved:
        return V12GateDecision.STOP_UNRESOLVED
    scientific_requirements = {
        "all_agents_recognized_expected_science",
        "one_representation_family_selected",
        "source_inventory_nonempty",
        "normalized_inventory_nonempty",
        "context_dimensions_preserved",
        "normalized_review_coverage_exact",
        "all_normalized_candidates_source_entailed",
        "inventory_coverage_complete",
        "unsupported_additions_absent",
        "declared_family_valid",
        "scientific_loss_zero",
        "unsupported_addition_axis_zero",
        "cue_material_mismatch_absent",
    }
    if any(not requirements[name] for name in scientific_requirements):
        return V12GateDecision.STOP_REMEDY_FALSIFIED
    if not (
        requirements["complete_acceptable_projection_recovered"]
        and requirements["single_representation_family_recovered"]
    ):
        return V12GateDecision.STOP_EXTERNAL_ADJUDICATION_REQUIRED
    if not requirements["unmatched_normalized_candidate_zero"]:
        return V12GateDecision.STOP_EXTERNAL_ADJUDICATION_REQUIRED
    return V12GateDecision.GO_TO_SMALL_REPLICATION


__all__ = [
    "V12GateDecision",
    "V12GateInputs",
    "v12_gate_decision",
    "v12_gate_requirements",
]
