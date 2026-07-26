from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.run_hidden_discovery_unit_audit import (
    hidden_discovery_report_exit_code,
)
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.discovery.authorization import (
    load_discovery_authorization,
)
from scripts.validation.claim_events.finite_source_unit.discovery.gate import (
    HiddenDiscoveryGateInputs,
    hidden_discovery_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.discovery.runner import (
    select_hidden_discovery_unit,
)
from scripts.validation.claim_events.fixture import load_fixture
from scripts.validation.claim_events.corpus_text import (
    RESTRICTED_CORPUS_SKIP_REASON,
    corpus_is_available,
)


#: These checks read the corpus text itself, which this public repository does
#: not carry.  They are skipped, never deleted: the reason names the licence and
#: the exact command that restores them.
requires_corpus = pytest.mark.skipif(
    not corpus_is_available(),
    reason=RESTRICTED_CORPUS_SKIP_REASON,
)

_FIXTURE_PATH = Path(
    "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json",
)


def _baseline_gate() -> HiddenDiscoveryGateInputs:
    return HiddenDiscoveryGateInputs(
        authorization_verified=True,
        hidden_expert_event_count=0,
        agent_execution_complete=True,
        extraction_category=SourceUnitEligibilityCategory.FINDING,
        verification_category=SourceUnitEligibilityCategory.FINDING,
        extraction_decision=SourceUnitDecision.EXPLICIT_EVENT,
        verification_coverage=SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        extracted_candidate_count=1,
        entailed_candidate_count=1,
        predicted_event_count=1,
        predicted_event_type="NEGATIVE_REGULATION",
        predicted_polarity="SUPPORT",
        predicted_epistemic_status="ASSERTED",
        material_argument_count=2,
        generic_event_role_count=0,
        binding_rejection_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        extraction_provider_response_id_count=1,
        verification_provider_response_id_count=1,
        distinct_provider_response_id_count=2,
        verified_provider_receipt_count=2,
        provider_receipt_gate_passed=True,
        fallback_count=0,
    )


def test_hidden_discovery_gate_requires_specific_reviewable_event() -> None:
    baseline = _baseline_gate()
    assert all(hidden_discovery_gate_requirements(baseline).values())

    mutations = (
        {"authorization_verified": False},
        {"hidden_expert_event_count": 1},
        {"agent_execution_complete": False},
        {"extraction_category": SourceUnitEligibilityCategory.HYPOTHESIS},
        {"verification_category": SourceUnitEligibilityCategory.NULL_RESULT},
        {"extraction_decision": SourceUnitDecision.NO_EVENT},
        {"verification_coverage": SourceUnitCoverageDecision.MISSING_EVENT},
        {"extracted_candidate_count": 2},
        {"entailed_candidate_count": 0},
        {"predicted_event_count": 2},
        {"predicted_event_type": "REGULATION"},
        {"predicted_polarity": "UNCERTAIN"},
        {"predicted_epistemic_status": "HYPOTHESIS"},
        {"material_argument_count": 1},
        {"generic_event_role_count": 1},
        {"binding_rejection_count": 1},
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
            hidden_discovery_gate_requirements(replace(baseline, **mutation)).values(),
        )


@requires_corpus
def test_hidden_discovery_unit_is_identity_frozen_and_has_no_local_gold() -> None:
    fixture = load_fixture(_FIXTURE_PATH)

    unit, hidden_event_count = select_hidden_discovery_unit(fixture)

    assert hidden_event_count == 0
    assert unit.unit_id == (
        "source-unit-a1e6d72064289601fc6e82446a14036433e1b1bf32cd014de2c817bf7b4cfde9"
    )
    assert unit.input_sha256 == (
        "5461f6bf2aa1e22bd9d6e292ca3e6e21e896d898c4b194229aebe6ace6c3ad0a"
    )
    # The corpus sentence is licence-restricted, so it is pinned by digest
    # rather than quoted.  See scripts/validation/RESTRICTED_CORPORA.md.
    assert hashlib.sha256(unit.text.encode("utf-8")).hexdigest() == (
        "14f2c9cb89a1d4091b51c8b96e4fc3cf51bd83088003913da44f345a58fd9928"
    )


def test_discovery_authorization_loader_rejects_scope_widening(
    tmp_path: Path,
) -> None:
    report: dict[str, object] = {
        "schema_version": "tg04_representation_adjudication.v1",
        "run_id": "tg04-representation-adjudication-luna-01",
        "gate": {
            "passed": True,
            "decision": "PROCEED_TO_ONE_UNANNOTATED_DISCOVERY_UNIT",
            "requirements": {
                "acceptable_alternate_decision": True,
                "provider_receipt_verified": True,
            },
        },
        "conclusion_scope": {
            "exact_benchmark_score_changed": False,
            "exact_whole_event_match_count": 0,
            "scientific_readiness_proven": False,
            "persistence_authorized": False,
        },
    }
    report_sha256 = hashlib.sha256(
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode(),
    ).hexdigest()
    report["report_sha256"] = report_sha256
    artifact_bytes = (
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode()
    artifact_path = tmp_path / "authorization.json"
    artifact_path.write_bytes(artifact_bytes)
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()

    authorization = load_discovery_authorization(
        artifact_path,
        expected_artifact_sha256=artifact_sha256,
        expected_report_sha256=report_sha256,
    )
    assert authorization.report_sha256 == report_sha256

    widened = dict(report)
    widened["conclusion_scope"] = {
        **report["conclusion_scope"],  # type: ignore[dict-item]
        "persistence_authorized": True,
    }
    widened.pop("report_sha256")
    widened_report_sha256 = hashlib.sha256(
        json.dumps(
            widened,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode(),
    ).hexdigest()
    widened["report_sha256"] = widened_report_sha256
    widened_bytes = (
        json.dumps(widened, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode()
    artifact_path.write_bytes(widened_bytes)
    with pytest.raises(RuntimeError, match="scope widened"):
        load_discovery_authorization(
            artifact_path,
            expected_artifact_sha256=hashlib.sha256(widened_bytes).hexdigest(),
            expected_report_sha256=widened_report_sha256,
        )


def test_hidden_discovery_cli_exit_status_follows_gate() -> None:
    assert hidden_discovery_report_exit_code({"gate": {"passed": True}}) == 0
    assert hidden_discovery_report_exit_code({"gate": {"passed": False}}) == 1
    assert hidden_discovery_report_exit_code({}) == 1
