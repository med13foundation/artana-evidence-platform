"""Deterministic gate for the non-qualifying transport-identity smoke."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

_EXPECTED_PROVIDER_CALL_COUNT: Final = 2


@dataclass(frozen=True, slots=True)
class TransportIdentityGateInputs:
    """Machine evidence that transport identity remained deterministic."""

    prior_failure_report_verified: bool
    adaptive_replay_declared: bool
    agent_execution_complete: bool
    extracted_candidate_count: int
    verification_decision_count: int
    entailed_candidate_count: int
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


def transport_identity_gate_requirements(
    inputs: TransportIdentityGateInputs,
) -> dict[str, bool]:
    """Require complete transport proof without awarding scientific credit."""

    return {
        "prior_failure_report_verified": inputs.prior_failure_report_verified,
        "adaptive_replay_declared": inputs.adaptive_replay_declared,
        "agent_execution_complete": inputs.agent_execution_complete,
        "candidate_path_exercised": (
            inputs.extracted_candidate_count == 1
            and inputs.verification_decision_count == 1
            and inputs.entailed_candidate_count == 1
        ),
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


__all__ = ["TransportIdentityGateInputs", "transport_identity_gate_requirements"]
