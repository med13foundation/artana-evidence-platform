"""Deterministic extraction gate for one hidden discovery unit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)

_EXPECTED_PROVIDER_CALL_COUNT: Final = 2
_MINIMUM_MATERIAL_ARGUMENT_COUNT: Final = 2
_ALLOWED_EVENT_TYPES: Final = frozenset({"DECREASE", "NEGATIVE_REGULATION"})


@dataclass(frozen=True, slots=True)
class HiddenDiscoveryGateInputs:
    """Machine evidence required before external literature review."""

    authorization_verified: bool
    hidden_expert_event_count: int
    agent_execution_complete: bool
    extraction_category: SourceUnitEligibilityCategory | None
    verification_category: SourceUnitEligibilityCategory | None
    extraction_decision: SourceUnitDecision | None
    verification_coverage: SourceUnitCoverageDecision | None
    extracted_candidate_count: int
    entailed_candidate_count: int
    predicted_event_count: int
    predicted_event_type: str | None
    predicted_polarity: str | None
    predicted_epistemic_status: str | None
    material_argument_count: int
    generic_event_role_count: int
    binding_rejection_count: int
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    extraction_provider_response_id_count: int
    verification_provider_response_id_count: int
    distinct_provider_response_id_count: int
    verified_provider_receipt_count: int
    provider_receipt_gate_passed: bool
    fallback_count: int


def hidden_discovery_gate_requirements(
    inputs: HiddenDiscoveryGateInputs,
) -> dict[str, bool]:
    """Require one specific, source-entailed, review-only discovery."""

    return {
        "authorization_verified": inputs.authorization_verified,
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
        "extractor_returned_one_candidate": (
            inputs.extraction_decision is SourceUnitDecision.EXPLICIT_EVENT
            and inputs.extracted_candidate_count == 1
        ),
        "verifier_confirmed_complete_candidate": (
            inputs.verification_coverage
            is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
            and inputs.entailed_candidate_count == 1
        ),
        "one_specific_event": (
            inputs.predicted_event_count == 1
            and inputs.predicted_event_type in _ALLOWED_EVENT_TYPES
        ),
        "asserted_supported_direction": (
            inputs.predicted_polarity == "SUPPORT"
            and inputs.predicted_epistemic_status == "ASSERTED"
        ),
        "material_roles_preserved": (
            inputs.material_argument_count >= _MINIMUM_MATERIAL_ARGUMENT_COUNT
            and inputs.generic_event_role_count == 0
        ),
        "binding_rejection_zero": inputs.binding_rejection_count == 0,
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


__all__ = ["HiddenDiscoveryGateInputs", "hidden_discovery_gate_requirements"]
