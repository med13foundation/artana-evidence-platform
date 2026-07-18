"""Deterministic stop/go gate for the pre-registered nested-event holdout."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)

_PRE_REGISTERED_REPEAT_INDICES = frozenset({1, 2, 3})
_BASE_PROVIDER_CALL_COUNT = 2
_MAX_SCHEMA_RETRY_COUNT = 1


@dataclass(frozen=True, slots=True)
class NestedHoldoutGateInputs:
    """Categorical decisions and deterministic counts for one sealed repeat."""

    repeat_index: int
    hidden_expert_event_count: int
    hidden_expert_link_count: int
    expected_eligibility_category: SourceUnitEligibilityCategory
    agent_execution_complete: bool
    extraction_category: SourceUnitEligibilityCategory | None
    verification_category: SourceUnitEligibilityCategory | None
    extraction_decision: SourceUnitDecision | None
    verification_coverage: SourceUnitCoverageDecision | None
    extracted_candidate_count: int
    verification_decision_count: int
    entailed_candidate_count: int
    trusted_candidate_count: int
    review_only_candidate_count: int
    rejected_candidate_count: int
    acceptable_projection_count: int
    fully_recovered_projection_count: int
    minimum_acceptable_projection_link_count: int
    observed_binding_rejection_count: int
    binding_rejection_count: int
    schema_retry_count: int
    reported_schema_retry_count: int
    primary_extraction_attempt_count: int
    schema_retry_attempt_count: int
    weak_review_attempt_count: int
    controlled_event_link_count: int
    controlled_event_link_ambiguity_count: int
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    extraction_provider_response_id_count: int
    verification_provider_response_id_count: int
    distinct_provider_response_id_count: int
    verified_provider_receipt_count: int
    provider_receipt_gate_passed: bool
    model_transport_identity_field_count: int
    audit_identity_mismatch_count: int
    attempt_model_id_mismatch_count: int


def nested_holdout_gate_requirements(
    inputs: NestedHoldoutGateInputs,
) -> dict[str, bool]:
    """Require the complete nested graph without rejecting valid discoveries."""

    candidate_count = inputs.extracted_candidate_count
    expected_provider_call_count = _BASE_PROVIDER_CALL_COUNT + inputs.schema_retry_count
    return {
        "repeat_index_pre_registered": inputs.repeat_index in _PRE_REGISTERED_REPEAT_INDICES,
        "sealed_graph_shape_verified": (
            inputs.hidden_expert_event_count > 0
            and inputs.hidden_expert_link_count >= 0
        ),
        "agent_execution_complete": inputs.agent_execution_complete,
        "expected_category_is_scientific": (
            inputs.expected_eligibility_category.scientific
        ),
        "extractor_recognized_expected_science": (
            inputs.extraction_category is inputs.expected_eligibility_category
        ),
        "verifier_recognized_expected_science": (
            inputs.verification_category is inputs.expected_eligibility_category
        ),
        "independent_categories_agree": (
            inputs.extraction_category is inputs.verification_category
        ),
        "explicit_candidate_inventory_nonempty": (
            inputs.extraction_decision is SourceUnitDecision.EXPLICIT_EVENT
            and candidate_count > 0
        ),
        "candidate_inventory_complete": (
            inputs.verification_coverage is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
            and inputs.verification_decision_count == candidate_count
        ),
        "all_candidates_source_entailed": inputs.entailed_candidate_count == candidate_count,
        "rejected_candidate_zero": inputs.rejected_candidate_count == 0,
        "review_only_candidates_preserved": (
            inputs.trusted_candidate_count + inputs.review_only_candidate_count
            == candidate_count
        ),
        "acceptable_projection_set_nonempty": inputs.acceptable_projection_count > 0,
        "complete_acceptable_projection_recovered": (
            inputs.fully_recovered_projection_count > 0
        ),
        "binding_repair_accounted": (
            (
                inputs.observed_binding_rejection_count == 0
                and inputs.schema_retry_count == 0
            )
            or (
                inputs.observed_binding_rejection_count > 0
                and inputs.schema_retry_count == 1
            )
        )
        and inputs.reported_schema_retry_count == inputs.schema_retry_count,
        "schema_retry_bounded": 0 <= inputs.schema_retry_count <= _MAX_SCHEMA_RETRY_COUNT,
        "audit_attempt_topology_exact": (
            inputs.primary_extraction_attempt_count == 1
            and inputs.schema_retry_attempt_count == inputs.schema_retry_count
            and inputs.weak_review_attempt_count == 1
        ),
        "binding_rejection_zero": inputs.binding_rejection_count == 0,
        "required_controlled_event_links_present": (
            inputs.controlled_event_link_count
            >= inputs.minimum_acceptable_projection_link_count
        ),
        "controlled_event_link_ambiguity_zero": (
            inputs.controlled_event_link_ambiguity_count == 0
        ),
        "invalid_agent_output_zero": inputs.invalid_agent_output_count == 0,
        "provider_lineage_complete": (
            inputs.unidentified_provider_attempt_count == 0
            and inputs.extraction_provider_response_id_count
            == inputs.primary_extraction_attempt_count + inputs.schema_retry_count
            and inputs.verification_provider_response_id_count == 1
            and inputs.distinct_provider_response_id_count
            == expected_provider_call_count
        ),
        "provider_receipts_verified": (
            inputs.provider_receipt_gate_passed
            and inputs.verified_provider_receipt_count == expected_provider_call_count
        ),
        "model_transport_identity_absent": inputs.model_transport_identity_field_count == 0,
        "audit_identity_bound": inputs.audit_identity_mismatch_count == 0,
        "attempt_model_identity_bound": inputs.attempt_model_id_mismatch_count == 0,
    }


__all__ = ["NestedHoldoutGateInputs", "nested_holdout_gate_requirements"]
