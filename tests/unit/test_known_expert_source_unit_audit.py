from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.run_known_expert_source_unit_audit import known_expert_report_exit_code
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.known_expert_gate import (
    KnownExpertUnitGateInputs,
    known_expert_unit_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.known_expert_runner import (
    select_known_expert_unit,
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


def _baseline() -> KnownExpertUnitGateInputs:
    return KnownExpertUnitGateInputs(
        agent_execution_complete=True,
        extraction_category=SourceUnitEligibilityCategory.FINDING,
        verification_category=SourceUnitEligibilityCategory.FINDING,
        extraction_decision=SourceUnitDecision.EXPLICIT_EVENT,
        verification_coverage=SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        extracted_candidate_count=1,
        entailed_candidate_count=1,
        exact_whole_event_match_count=1,
        predicted_event_count=1,
        binding_rejection_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        extraction_provider_response_id_count=1,
        verification_provider_response_id_count=1,
        distinct_provider_response_id_count=2,
        verified_provider_receipt_count=2,
        provider_receipt_gate_passed=True,
        fallback_count=0,
        epistemic_escalation_count=0,
    )


def test_known_expert_gate_requires_one_complete_expert_event() -> None:
    baseline = _baseline()

    assert all(known_expert_unit_gate_requirements(baseline).values())

    partial = replace(baseline, exact_whole_event_match_count=0)
    extra = replace(baseline, predicted_event_count=2)
    requirements = known_expert_unit_gate_requirements(partial)
    assert requirements["exactly_one_complete_expert_event"] is False
    assert not all(requirements.values())
    assert not all(known_expert_unit_gate_requirements(extra).values())


def test_known_expert_gate_fails_closed_on_all_safety_boundaries() -> None:
    baseline = _baseline()
    mutations = (
        {"agent_execution_complete": False},
        {"extraction_category": SourceUnitEligibilityCategory.HYPOTHESIS},
        {"verification_category": SourceUnitEligibilityCategory.HYPOTHESIS},
        {"extraction_decision": SourceUnitDecision.NO_EVENT},
        {"verification_coverage": SourceUnitCoverageDecision.MISSING_EVENT},
        {"extracted_candidate_count": 2},
        {"entailed_candidate_count": 0},
        {"binding_rejection_count": 1},
        {"invalid_agent_output_count": 1},
        {"unidentified_provider_attempt_count": 1},
        {"extraction_provider_response_id_count": 0},
        {"verification_provider_response_id_count": 0},
        {"distinct_provider_response_id_count": 1},
        {"verified_provider_receipt_count": 1},
        {"provider_receipt_gate_passed": False},
        {"fallback_count": 1},
        {"epistemic_escalation_count": 1},
    )

    for mutation in mutations:
        assert not all(
            known_expert_unit_gate_requirements(replace(baseline, **mutation)).values(),
        )


@requires_corpus
def test_known_expert_runner_freezes_event_and_source_unit_identity() -> None:
    fixture = load_fixture(
        Path(
            "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"
        ),
    )

    unit, event = select_known_expert_unit(fixture)

    assert event.event_id == "PMC-1134658-06-Results-05:E9"
    assert event.trigger_span == "upregulation"
    assert unit.unit_id == (
        "source-unit-e14e44064324af2f721a3d02d2caf44c00218a0ab6c4afc58e9bace413c9d46c"
    )
    assert unit.input_sha256 == (
        "14aec6614afd9d47d4cbafe7298b0e6b77b7a3d324048635d3fb98f463b9a0fd"
    )
    # The corpus sentence is licence-restricted, so it is pinned by digest
    # rather than quoted.  See scripts/validation/RESTRICTED_CORPORA.md.
    assert hashlib.sha256(unit.text.encode("utf-8")).hexdigest() == (
        "193eb99d4d17d23d990650553f3189dc7523392e2c119dad6895528d475a8065"
    )


def test_known_expert_cli_exit_status_follows_deterministic_gate() -> None:
    assert known_expert_report_exit_code({"gate": {"passed": True}}) == 0
    assert known_expert_report_exit_code({"gate": {"passed": False}}) == 1
    assert known_expert_report_exit_code({}) == 1
