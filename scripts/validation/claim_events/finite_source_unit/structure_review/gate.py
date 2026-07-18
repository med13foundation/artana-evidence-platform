"""Deterministic gate for the post-#177 structure-review replay."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitEligibilityCategory,
)

_EXPECTED_CANDIDATE_COUNT = 2


@dataclass(frozen=True, slots=True)
class StructureReplayGateInputs:
    """Machine evidence required before another fresh extraction is allowed."""

    authorization_verified: bool
    frozen_artifact_verified: bool
    adaptive_replay_declared: bool
    review_execution_complete: bool
    verification_category: SourceUnitEligibilityCategory | None
    verification_coverage: SourceUnitCoverageDecision | None
    candidate_count: int
    verification_decision_count: int
    entailed_candidate_count: int
    trusted_projection_count: int
    structure_blocker_count: int
    invalid_argument_type_count: int
    model_transport_identity_field_count: int
    audit_identity_mismatch_count: int
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    verification_provider_response_id_count: int
    verified_provider_receipt_count: int
    provider_receipt_gate_passed: bool
    fallback_count: int


def structure_replay_gate_requirements(
    inputs: StructureReplayGateInputs,
) -> dict[str, bool]:
    """Require the reviewer to catch both known #177 trust defects."""

    return {
        "authorization_verified": inputs.authorization_verified,
        "frozen_artifact_verified": inputs.frozen_artifact_verified,
        "adaptive_replay_declared": inputs.adaptive_replay_declared,
        "review_execution_complete": inputs.review_execution_complete,
        "verifier_recognized_finding": (
            inputs.verification_category is SourceUnitEligibilityCategory.FINDING
        ),
        "candidate_inventory_preserved": (
            inputs.candidate_count == _EXPECTED_CANDIDATE_COUNT
            and inputs.verification_decision_count == inputs.candidate_count
        ),
        "source_entailment_preserved": (
            inputs.verification_coverage
            is SourceUnitCoverageDecision.CANDIDATES_COMPLETE
            and inputs.entailed_candidate_count == inputs.candidate_count
        ),
        "known_candidates_not_trusted": inputs.trusted_projection_count == 0,
        "lossy_structure_detected": inputs.structure_blocker_count >= 1,
        "invalid_argument_type_detected": inputs.invalid_argument_type_count >= 1,
        "model_transport_identity_absent": (
            inputs.model_transport_identity_field_count == 0
        ),
        "audit_identity_bound": inputs.audit_identity_mismatch_count == 0,
        "invalid_agent_output_zero": inputs.invalid_agent_output_count == 0,
        "provider_lineage_complete": (
            inputs.unidentified_provider_attempt_count == 0
            and inputs.verification_provider_response_id_count == 1
        ),
        "provider_receipt_verified": (
            inputs.provider_receipt_gate_passed
            and inputs.verified_provider_receipt_count == 1
        ),
        "fallback_zero": inputs.fallback_count == 0,
    }


__all__ = ["StructureReplayGateInputs", "structure_replay_gate_requirements"]
