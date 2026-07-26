from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.run_source_unit_transport_smoke import transport_smoke_exit_code
from scripts.validation.claim_events.finite_source_unit.discovery.identity_evidence import (
    count_model_identity_fields,
)
from scripts.validation.claim_events.finite_source_unit.discovery.transport_gate import (
    TransportIdentityGateInputs,
    transport_identity_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.discovery.transport_smoke import (
    verify_prior_failure_report,
)


def _baseline_gate() -> TransportIdentityGateInputs:
    return TransportIdentityGateInputs(
        prior_failure_report_verified=True,
        adaptive_replay_declared=True,
        agent_execution_complete=True,
        extracted_candidate_count=1,
        verification_decision_count=1,
        entailed_candidate_count=1,
        binding_rejection_count=0,
        model_transport_identity_field_count=0,
        audit_identity_mismatch_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        extraction_provider_response_id_count=1,
        verification_provider_response_id_count=1,
        distinct_provider_response_id_count=2,
        verified_provider_receipt_count=2,
        provider_receipt_gate_passed=True,
        fallback_count=0,
    )


def test_transport_identity_gate_requires_complete_nonqualifying_replay() -> None:
    baseline = _baseline_gate()
    assert all(transport_identity_gate_requirements(baseline).values())

    mutations = (
        {"prior_failure_report_verified": False},
        {"adaptive_replay_declared": False},
        {"agent_execution_complete": False},
        {"extracted_candidate_count": 0},
        {"verification_decision_count": 0},
        {"entailed_candidate_count": 0},
        {"binding_rejection_count": 1},
        {"model_transport_identity_field_count": 1},
        {"audit_identity_mismatch_count": 1},
        {"invalid_agent_output_count": 1},
        {"unidentified_provider_attempt_count": 1},
        {"extraction_provider_response_id_count": 0},
        {"verification_provider_response_id_count": 0},
        {"distinct_provider_response_id_count": 1},
        {"verified_provider_receipt_count": 1},
        {"provider_receipt_gate_passed": False},
        {"fallback_count": 1},
    )
    for mutation in mutations:
        assert not all(
            transport_identity_gate_requirements(
                replace(baseline, **mutation),
            ).values(),
        )


def test_prior_failure_report_is_hash_pinned(tmp_path: Path) -> None:
    """The pin moved when the report was redacted; see `transport_smoke`.

    Same report, same authorization: a quoted source sentence became a locator
    and a digest, and no finding, count or verdict in it changed.  The reason
    and the superseded digest are recorded beside the constant, because a pin
    that can be bumped without explanation pins nothing.
    """

    report_sha256 = verify_prior_failure_report()
    assert report_sha256 == (
        "0f9792b8d11ae9a86bc57c8ea8e3c4522f081b7810bab705c5238ce81a8c508b"
    )

    changed = tmp_path / "changed.md"
    changed.write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stop report changed"):
        verify_prior_failure_report(changed)


def test_model_identity_field_count_is_recursive_and_key_specific() -> None:
    assert (
        count_model_identity_fields(
            {
                "unit_id": "forbidden",
                "events": [
                    {
                        "candidate_id": "forbidden",
                        "reasoning": "The prose may mention unit_id safely.",
                    },
                ],
                "error_type": None,
            },
        )
        == 2
    )
    assert (
        count_model_identity_fields(
            {"reasoning": "unit_id is transport metadata"},
        )
        == 0
    )


def test_transport_smoke_cli_exit_status_follows_gate() -> None:
    assert transport_smoke_exit_code({"gate": {"passed": True}}) == 0
    assert transport_smoke_exit_code({"gate": {"passed": False}}) == 1
    assert transport_smoke_exit_code({}) == 1
