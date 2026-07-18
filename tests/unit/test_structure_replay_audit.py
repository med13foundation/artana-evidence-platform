from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.run_structure_replay_audit import structure_replay_exit_code
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.structure_review.gate import (
    StructureReplayGateInputs,
    structure_replay_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.structure_review.source import (
    _verify_sha256,
)


def _baseline_gate() -> StructureReplayGateInputs:
    return StructureReplayGateInputs(
        authorization_verified=True,
        frozen_artifact_verified=True,
        adaptive_replay_declared=True,
        review_execution_complete=True,
        verification_category=SourceUnitEligibilityCategory.FINDING,
        verification_coverage=SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        candidate_count=2,
        verification_decision_count=2,
        entailed_candidate_count=2,
        trusted_projection_count=0,
        structure_blocker_count=1,
        invalid_argument_type_count=1,
        model_transport_identity_field_count=0,
        audit_identity_mismatch_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        verification_provider_response_id_count=1,
        verified_provider_receipt_count=1,
        provider_receipt_gate_passed=True,
        fallback_count=0,
    )


def test_structure_replay_gate_fails_closed_on_every_boundary() -> None:
    baseline = _baseline_gate()
    assert all(structure_replay_gate_requirements(baseline).values())

    mutations = (
        {"authorization_verified": False},
        {"frozen_artifact_verified": False},
        {"adaptive_replay_declared": False},
        {"review_execution_complete": False},
        {"verification_category": SourceUnitEligibilityCategory.ABSTAIN},
        {"verification_coverage": SourceUnitCoverageDecision.MISSING_EVENT},
        {"candidate_count": 1},
        {"verification_decision_count": 1},
        {"entailed_candidate_count": 1},
        {"trusted_projection_count": 1},
        {"structure_blocker_count": 0},
        {"invalid_argument_type_count": 0},
        {"model_transport_identity_field_count": 1},
        {"audit_identity_mismatch_count": 1},
        {"invalid_agent_output_count": 1},
        {"unidentified_provider_attempt_count": 1},
        {"verification_provider_response_id_count": 0},
        {"verified_provider_receipt_count": 0},
        {"provider_receipt_gate_passed": False},
        {"fallback_count": 1},
    )
    for mutation in mutations:
        assert not all(
            structure_replay_gate_requirements(
                replace(baseline, **mutation),
            ).values(),
        )


def test_hash_verification_is_create_once_and_fail_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("frozen", encoding="utf-8")
    expected = hashlib.sha256(b"frozen").hexdigest()

    assert _verify_sha256(artifact, expected_sha256=expected, label="test") == expected

    artifact.write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="test changed"):
        _verify_sha256(artifact, expected_sha256=expected, label="test")


def test_structure_replay_cli_exit_status_follows_gate() -> None:
    assert structure_replay_exit_code({"gate": {"passed": True}}) == 0
    assert structure_replay_exit_code({"gate": {"passed": False}}) == 1
    assert structure_replay_exit_code({}) == 1
