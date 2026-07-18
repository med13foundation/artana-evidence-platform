"""Deterministic stop/go gate for one sealed expert-event source unit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)

_EXPECTED_PROVIDER_CALL_COUNT: Final = 2


@dataclass(frozen=True, slots=True)
class KnownExpertUnitGateInputs:
    """Machine evidence required before attempting an unannotated unit."""

    agent_execution_complete: bool
    extraction_category: SourceUnitEligibilityCategory | None
    verification_category: SourceUnitEligibilityCategory | None
    extraction_decision: SourceUnitDecision | None
    verification_coverage: SourceUnitCoverageDecision | None
    extracted_candidate_count: int
    entailed_candidate_count: int
    exact_whole_event_match_count: int
    predicted_event_count: int
    binding_rejection_count: int
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    extraction_provider_response_id_count: int
    verification_provider_response_id_count: int
    distinct_provider_response_id_count: int
    verified_provider_receipt_count: int
    provider_receipt_gate_passed: bool
    fallback_count: int
    epistemic_escalation_count: int


def known_expert_unit_gate_requirements(
    inputs: KnownExpertUnitGateInputs,
) -> dict[str, bool]:
    """Derive strict reconstruction eligibility without model-produced scores."""

    return {
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
        "exactly_one_complete_expert_event": (
            inputs.exact_whole_event_match_count == 1
            and inputs.predicted_event_count == 1
        ),
        "epistemic_escalation_zero": inputs.epistemic_escalation_count == 0,
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


__all__ = ["KnownExpertUnitGateInputs", "known_expert_unit_gate_requirements"]
