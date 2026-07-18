"""Deterministic stop/go gate for the single TG-04 procedure source unit."""

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
class ProcedureUnitGateInputs:
    """Machine evidence required before leaving the procedure-only step."""

    agent_execution_complete: bool
    extraction_category: SourceUnitEligibilityCategory | None
    verification_category: SourceUnitEligibilityCategory | None
    extraction_decision: SourceUnitDecision | None
    verification_coverage: SourceUnitCoverageDecision | None
    extracted_candidate_count: int
    verification_decision_count: int
    binding_rejection_count: int
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    extraction_provider_response_id_count: int
    verification_provider_response_id_count: int
    distinct_provider_response_id_count: int
    verified_provider_receipt_count: int
    provider_receipt_gate_passed: bool
    fallback_count: int


def procedure_unit_gate_requirements(
    inputs: ProcedureUnitGateInputs,
) -> dict[str, bool]:
    """Derive the pre-registered procedure-unit decision without model scores."""

    return {
        "agent_execution_complete": inputs.agent_execution_complete,
        "extractor_recognized_procedure": (
            inputs.extraction_category is SourceUnitEligibilityCategory.PROCEDURE
        ),
        "verifier_recognized_procedure": (
            inputs.verification_category is SourceUnitEligibilityCategory.PROCEDURE
        ),
        "independent_categories_agree": (
            inputs.extraction_category is inputs.verification_category
        ),
        "extractor_excluded_scientific_candidates": (
            inputs.extraction_decision is SourceUnitDecision.NO_EVENT
            and inputs.extracted_candidate_count == 0
        ),
        "verifier_confirmed_no_scientific_event": (
            inputs.verification_coverage
            is SourceUnitCoverageDecision.NO_EVENT_CONFIRMED
            and inputs.verification_decision_count == 0
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
            and inputs.verified_provider_receipt_count
            == _EXPECTED_PROVIDER_CALL_COUNT
        ),
        "fallback_zero": inputs.fallback_count == 0,
    }


__all__ = ["ProcedureUnitGateInputs", "procedure_unit_gate_requirements"]
