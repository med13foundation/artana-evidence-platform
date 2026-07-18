"""Deterministic stop/go gate for one representation adjudication."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.claim_events.finite_source_unit.representation_contracts import (
    RepresentationAxisDecision,
    RepresentationDecision,
    RepresentationSourceSupport,
)

_MATERIAL_AXIS_COUNT = 6


@dataclass(frozen=True, slots=True)
class RepresentationGateInputs:
    """Machine evidence required before one unannotated discovery unit."""

    prior_artifact_verified: bool
    prior_exact_match_count: int
    prior_predicted_event_count: int
    prior_non_exact_requirements_passed: bool
    adjudication_execution_complete: bool
    decision: RepresentationDecision | None
    expert_source_support: RepresentationSourceSupport | None
    candidate_source_support: RepresentationSourceSupport | None
    axes: tuple[RepresentationAxisDecision, ...]
    evidence_coverage_complete: bool
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    provider_response_id_count: int
    verified_provider_receipt_count: int
    provider_receipt_gate_passed: bool
    fallback_count: int


def representation_gate_requirements(
    inputs: RepresentationGateInputs,
) -> dict[str, bool]:
    """Keep exact scoring failed while evaluating alternate semantics."""

    acceptable_axes = {
        RepresentationAxisDecision.PRESERVED,
        RepresentationAxisDecision.COMPATIBLE_REFINEMENT,
    }
    return {
        "prior_artifact_verified": inputs.prior_artifact_verified,
        "exact_benchmark_failure_preserved": (
            inputs.prior_exact_match_count == 0
            and inputs.prior_predicted_event_count == 1
        ),
        "prior_safety_requirements_passed": inputs.prior_non_exact_requirements_passed,
        "adjudication_execution_complete": inputs.adjudication_execution_complete,
        "acceptable_alternate_decision": (
            inputs.decision is RepresentationDecision.ACCEPTABLE_ALTERNATE
        ),
        "both_representations_source_entailed": (
            inputs.expert_source_support is RepresentationSourceSupport.ENTAILED
            and inputs.candidate_source_support is RepresentationSourceSupport.ENTAILED
        ),
        "all_material_axes_compatible": (
            len(inputs.axes) == _MATERIAL_AXIS_COUNT
            and all(axis in acceptable_axes for axis in inputs.axes)
        ),
        "evidence_coverage_complete": inputs.evidence_coverage_complete,
        "invalid_agent_output_zero": inputs.invalid_agent_output_count == 0,
        "provider_lineage_complete": (
            inputs.unidentified_provider_attempt_count == 0
            and inputs.provider_response_id_count == 1
        ),
        "provider_receipt_verified": (
            inputs.provider_receipt_gate_passed
            and inputs.verified_provider_receipt_count == 1
        ),
        "fallback_zero": inputs.fallback_count == 0,
    }


__all__ = ["RepresentationGateInputs", "representation_gate_requirements"]
