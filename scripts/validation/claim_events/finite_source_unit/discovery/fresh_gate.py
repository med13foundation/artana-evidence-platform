"""Deterministic stop/go gate for one fresh scientific source unit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)

_EXPECTED_PROVIDER_CALL_COUNT: Final = 2
_MAXIMUM_SOURCE_ENTAILED_EVENTS: Final = 3


@dataclass(frozen=True, slots=True)
class FreshDiscoveryGateInputs:
    """Machine evidence required before independent literature review."""

    authorization_verified: bool
    exposure_registry_verified: bool
    hidden_expert_event_count: int
    agent_execution_complete: bool
    extraction_category: SourceUnitEligibilityCategory | None
    verification_category: SourceUnitEligibilityCategory | None
    extraction_decision: SourceUnitDecision | None
    verification_coverage: SourceUnitCoverageDecision | None
    extracted_candidate_count: int
    verification_decision_count: int
    entailed_candidate_count: int
    target_event_count: int
    target_direction_preserved: bool
    target_polarity_asserted: bool
    target_arguments_preserved: bool
    generic_event_role_count: int
    binding_rejection_count: int
    model_transport_identity_field_count: int
    audit_identity_mismatch_count: int
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    extraction_provider_response_id_count: int
    verification_provider_response_id_count: int
    distinct_provider_response_id_count: int
    verified_provider_receipt_count: int
    provider_receipt_gate_passed: bool
    fallback_count: int


def fresh_discovery_gate_requirements(
    inputs: FreshDiscoveryGateInputs,
) -> dict[str, bool]:
    """Require one specific target while preserving valid sibling events."""

    candidate_count_valid = (
        1 <= inputs.extracted_candidate_count <= _MAXIMUM_SOURCE_ENTAILED_EVENTS
    )
    return {
        "authorization_verified": inputs.authorization_verified,
        "fresh_exposure_registry_verified": inputs.exposure_registry_verified,
        "benchmark_event_hidden": inputs.hidden_expert_event_count == 0,
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
        "bounded_source_inventory": (
            inputs.extraction_decision is SourceUnitDecision.EXPLICIT_EVENT
            and candidate_count_valid
        ),
        "all_candidates_independently_entailed": (
            inputs.verification_coverage
            is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
            and inputs.verification_decision_count == inputs.extracted_candidate_count
            and inputs.entailed_candidate_count == inputs.extracted_candidate_count
        ),
        "one_specific_target_event": inputs.target_event_count == 1,
        "target_direction_preserved": inputs.target_direction_preserved,
        "target_polarity_asserted": inputs.target_polarity_asserted,
        "target_arguments_preserved": inputs.target_arguments_preserved,
        "generic_event_roles_zero": inputs.generic_event_role_count == 0,
        "binding_rejection_zero": inputs.binding_rejection_count == 0,
        "model_transport_identity_absent": (
            inputs.model_transport_identity_field_count == 0
        ),
        "audit_identity_bound": inputs.audit_identity_mismatch_count == 0,
        "invalid_agent_output_zero": inputs.invalid_agent_output_count == 0,
        "provider_lineage_complete": (
            inputs.unidentified_provider_attempt_count == 0
            and inputs.extraction_provider_response_id_count == 1
            and inputs.verification_provider_response_id_count == 1
            and inputs.distinct_provider_response_id_count
            == _EXPECTED_PROVIDER_CALL_COUNT
        ),
        "provider_receipts_verified": (
            inputs.provider_receipt_gate_passed
            and inputs.verified_provider_receipt_count == _EXPECTED_PROVIDER_CALL_COUNT
        ),
        "fallback_zero": inputs.fallback_count == 0,
    }


__all__ = ["FreshDiscoveryGateInputs", "fresh_discovery_gate_requirements"]
