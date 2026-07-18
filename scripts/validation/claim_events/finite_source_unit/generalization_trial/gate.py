"""Deterministic scientific gate for the fresh generalization trial."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)

_PRE_REGISTERED_REPEAT_INDICES = frozenset({1, 2, 3})
_PROVIDER_CALL_COUNT = 2


@dataclass(frozen=True, slots=True)
class GeneralizationGateInputs:
    """Categorical findings and deterministic counts for one fresh repeat."""

    authorization_verified: bool
    selection_verified: bool
    fresh_unit_declared: bool
    adaptive_replay_declared: bool
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


def generalization_gate_requirements(
    inputs: GeneralizationGateInputs,
) -> dict[str, bool]:
    """Require complete source support while allowing valid extra discoveries."""

    candidate_count = inputs.extracted_candidate_count
    return {
        "authorization_verified": inputs.authorization_verified,
        "selection_verified": inputs.selection_verified,
        "execution_mode_declared": (
            inputs.fresh_unit_declared != inputs.adaptive_replay_declared
        ),
        "repeat_index_pre_registered": (
            inputs.repeat_index in _PRE_REGISTERED_REPEAT_INDICES
        ),
        "one_hidden_minimum_expert_event": inputs.hidden_expert_event_count == 1,
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
        "explicit_candidate_inventory_nonempty": (
            inputs.extraction_decision is SourceUnitDecision.EXPLICIT_EVENT
            and candidate_count > 0
        ),
        "candidate_inventory_complete": (
            inputs.verification_coverage
            is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
            and inputs.verification_decision_count == candidate_count
        ),
        "all_candidates_source_entailed": (
            inputs.entailed_candidate_count == candidate_count
        ),
        "all_candidates_structure_trusted": (
            inputs.trusted_candidate_count == candidate_count
        ),
        "sealed_expert_core_recovered": inputs.expert_core_event_match_count == 1,
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


__all__ = ["GeneralizationGateInputs", "generalization_gate_requirements"]
