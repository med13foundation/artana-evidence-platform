"""Deterministic stop/go rules for one fresh controlled-event run."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)

_MAXIMUM_REPEAT_INDEX = 3
_PROVIDER_CALL_COUNT = 2


@dataclass(frozen=True, slots=True)
class ControlledEventTrialGateInputs:
    """Categorical findings and deterministic counts for one repeat."""

    authorization_verified: bool
    selection_verified: bool
    repeat_index: int
    hidden_expert_event_count: int
    agent_execution_complete: bool
    extraction_category: SourceUnitEligibilityCategory | None
    verification_category: SourceUnitEligibilityCategory | None
    extraction_decision: SourceUnitDecision | None
    verification_coverage: SourceUnitCoverageDecision | None
    extracted_candidate_count: int
    verification_decision_count: int
    entailed_candidate_count: int
    trusted_candidate_count: int
    expert_core_event_match_count: int
    predicted_trusted_event_count: int
    binding_rejection_count: int
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    extraction_provider_response_id_count: int
    verification_provider_response_id_count: int
    distinct_provider_response_id_count: int
    verified_provider_receipt_count: int
    provider_receipt_gate_passed: bool
    model_transport_identity_field_count: int
    audit_identity_mismatch_count: int
    fallback_count: int


def controlled_event_trial_gate_requirements(
    inputs: ControlledEventTrialGateInputs,
) -> dict[str, bool]:
    """Require exact expert recovery plus independent structural trust."""

    return {
        "authorization_verified": inputs.authorization_verified,
        "selection_verified": inputs.selection_verified,
        "repeat_index_pre_registered": (
            1 <= inputs.repeat_index <= _MAXIMUM_REPEAT_INDEX
        ),
        "one_hidden_expert_event": inputs.hidden_expert_event_count == 1,
        "agent_execution_complete": inputs.agent_execution_complete,
        "extractor_recognized_finding": (
            inputs.extraction_category is SourceUnitEligibilityCategory.FINDING
        ),
        "verifier_recognized_finding": (
            inputs.verification_category is SourceUnitEligibilityCategory.FINDING
        ),
        "independent_categories_agree": (
            inputs.extraction_category is inputs.verification_category
        ),
        "one_explicit_candidate": (
            inputs.extraction_decision is SourceUnitDecision.EXPLICIT_EVENT
            and inputs.extracted_candidate_count == 1
        ),
        "candidate_inventory_complete": (
            inputs.verification_coverage
            is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
            and inputs.verification_decision_count == 1
        ),
        "candidate_source_entailed": inputs.entailed_candidate_count == 1,
        "candidate_structure_trusted": inputs.trusted_candidate_count == 1,
        "sealed_expert_core_recovered": (
            inputs.expert_core_event_match_count == 1
            and inputs.predicted_trusted_event_count == 1
        ),
        "binding_rejection_zero": inputs.binding_rejection_count == 0,
        "invalid_agent_output_zero": inputs.invalid_agent_output_count == 0,
        "provider_lineage_complete": (
            inputs.unidentified_provider_attempt_count == 0
            and inputs.extraction_provider_response_id_count == 1
            and inputs.verification_provider_response_id_count == 1
            and inputs.distinct_provider_response_id_count == _PROVIDER_CALL_COUNT
        ),
        "provider_receipts_verified": (
            inputs.provider_receipt_gate_passed
            and inputs.verified_provider_receipt_count == _PROVIDER_CALL_COUNT
        ),
        "model_transport_identity_absent": (
            inputs.model_transport_identity_field_count == 0
        ),
        "audit_identity_bound": inputs.audit_identity_mismatch_count == 0,
        "fallback_zero": inputs.fallback_count == 0,
    }


__all__ = [
    "ControlledEventTrialGateInputs",
    "controlled_event_trial_gate_requirements",
]
