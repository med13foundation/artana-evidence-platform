from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.run_generalization_event_final_replay import final_replay_exit_code
from scripts.run_generalization_event_replay import generalization_replay_exit_code
from scripts.run_generalization_event_second_replay import second_replay_exit_code
from scripts.run_generalization_event_trial import generalization_trial_exit_code
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.adaptive_replay_authorization import (
    _verify_failed_adaptive_replay_payload,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.authorization import (
    _verify_authorization_payload,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.final_replay_authorization import (
    _verify_final_replay_payload,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.gate import (
    GeneralizationGateInputs,
    generalization_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.replay_authorization import (
    _verify_failed_generalization_payload,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.selection import (
    select_generalization_trial,
)
from scripts.validation.claim_events.fixture import (
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    load_fixture,
)


def _baseline_gate() -> GeneralizationGateInputs:
    return GeneralizationGateInputs(
        authorization_verified=True,
        selection_verified=True,
        fresh_unit_declared=True,
        adaptive_replay_declared=False,
        repeat_index=1,
        hidden_expert_event_count=1,
        agent_execution_complete=True,
        extraction_category=SourceUnitEligibilityCategory.FINDING,
        verification_category=SourceUnitEligibilityCategory.FINDING,
        extraction_decision=SourceUnitDecision.EXPLICIT_EVENT,
        verification_coverage=SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        extracted_candidate_count=2,
        verification_decision_count=2,
        entailed_candidate_count=2,
        trusted_candidate_count=2,
        expert_core_event_match_count=1,
        binding_rejection_count=0,
        required_controlled_event_link_count=1,
        controlled_event_link_count=1,
        controlled_event_link_ambiguity_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        extraction_provider_response_id_count=1,
        verification_provider_response_id_count=1,
        distinct_provider_response_id_count=2,
        verified_provider_receipt_count=2,
        provider_receipt_gate_passed=True,
        model_transport_identity_field_count=0,
        audit_identity_mismatch_count=0,
        fallback_count=0,
    )


def test_generalization_selection_is_frozen_and_excludes_prior_unit() -> None:
    selection = select_generalization_trial(
        load_fixture(DEFAULT_DEVELOPMENT_FIXTURE_PATH),
    )

    assert selection.case_id == "bionlp-ge-2011:PMC-2806624-05-RESULTS-04"
    assert selection.unit.index == 7
    assert selection.unit.text == (
        "The induction of Foxp3 was again significantly lower in CbfbF/F CD4-cre "
        "CD4+ T cells even in the presence of retinoic acid, demonstrating that "
        "deficiency in Runx binding to DNA affects the TGF-beta induction of Foxp3 "
        "in T reg cells (Fig. 5 A)."
    )
    assert len(selection.expert_events) == 1
    assert selection.expert_events[0].event_type.value == "POSITIVE_REGULATION"
    assert selection.expert_events[0].trigger_span == "induction"
    assert selection.unit.unit_id != (
        "source-unit-02c41780fd8d83965debdc337f89adce6283552fa76ac7d36ee12c56060ef21b"
    )


def test_generalization_gate_allows_only_source_valid_additional_claims() -> None:
    baseline = _baseline_gate()

    assert all(generalization_gate_requirements(baseline).values())

    one_valid_claim = replace(
        baseline,
        extracted_candidate_count=1,
        verification_decision_count=1,
        entailed_candidate_count=1,
        trusted_candidate_count=1,
    )
    assert all(generalization_gate_requirements(one_valid_claim).values())

    unsupported_extra = replace(baseline, entailed_candidate_count=1)
    assert not generalization_gate_requirements(unsupported_extra)[
        "all_candidates_source_entailed"
    ]

    structurally_invalid_extra = replace(baseline, trusted_candidate_count=1)
    assert not generalization_gate_requirements(structurally_invalid_extra)[
        "all_candidates_structure_trusted"
    ]


def test_generalization_gate_fails_closed_on_every_boundary() -> None:
    baseline = _baseline_gate()
    mutations = (
        {"authorization_verified": False},
        {"selection_verified": False},
        {"fresh_unit_declared": False},
        {"adaptive_replay_declared": True},
        {"repeat_index": 0},
        {"repeat_index": 4},
        {"hidden_expert_event_count": 0},
        {"agent_execution_complete": False},
        {"extraction_category": SourceUnitEligibilityCategory.ABSTAIN},
        {"verification_category": SourceUnitEligibilityCategory.ABSTAIN},
        {"extraction_decision": SourceUnitDecision.ABSTAIN},
        {"verification_coverage": SourceUnitCoverageDecision.MISSING_EVENT},
        {"extracted_candidate_count": 0},
        {"verification_decision_count": 1},
        {"entailed_candidate_count": 1},
        {"trusted_candidate_count": 1},
        {"expert_core_event_match_count": 0},
        {"binding_rejection_count": 1},
        {"required_controlled_event_link_count": 0},
        {"controlled_event_link_count": 0},
        {"controlled_event_link_ambiguity_count": 1},
        {"invalid_agent_output_count": 1},
        {"unidentified_provider_attempt_count": 1},
        {"extraction_provider_response_id_count": 0},
        {"verification_provider_response_id_count": 0},
        {"distinct_provider_response_id_count": 1},
        {"verified_provider_receipt_count": 1},
        {"provider_receipt_gate_passed": False},
        {"model_transport_identity_field_count": 1},
        {"audit_identity_mismatch_count": 1},
        {"fallback_count": 1},
    )
    for mutation in mutations:
        assert not all(
            generalization_gate_requirements(
                replace(baseline, **mutation),
            ).values(),
        )


def test_reassessment_authorization_requires_zero_call_success() -> None:
    payload: dict[str, object] = {
        "schema_version": "tg04_controlled_event_reassessment.v1",
        "report_sha256": (
            "7a97214a6540f4de7cfeefc8d556cbdc69e4f08e9f24a4410016bd902ef38435"
        ),
        "gate": {
            "passed": True,
            "decision": "PROCEED_TO_NEW_FRESH_UNIT",
        },
        "conclusion_scope": {
            "model_call_count": 0,
            "qualification_eligible": False,
        },
    }
    _verify_authorization_payload(payload)

    called_again = dict(payload)
    called_again["conclusion_scope"] = {
        "model_call_count": 1,
        "qualification_eligible": False,
    }
    with pytest.raises(RuntimeError, match="did not authorize"):
        _verify_authorization_payload(called_again)


def test_generalization_replay_requires_exact_failed_boundary() -> None:
    requirements = dict.fromkeys(
        generalization_gate_requirements(_baseline_gate()),
        True,
    )
    for failed in (
        "all_candidates_source_entailed",
        "all_candidates_structure_trusted",
        "sealed_expert_core_recovered",
    ):
        requirements[failed] = False
    payload: dict[str, object] = {
        "schema_version": "tg04_generalization_trial.v1",
        "experiment_mode": "fresh",
        "repeat_index": 1,
        "report_sha256": (
            "7b742b487c0fd38674c257b1bafa319cc9a2f6c4dc1cb21b55d061001261f383"
        ),
        "unit": {
            "unit_id": (
                "source-unit-6508d78fe2bb4886b606f91f2c990c36b55f54b2ac9886448e5251693222b3fe"
            ),
        },
        "gate": {
            "passed": False,
            "decision": "STOP_AND_RECALIBRATE_GENERALIZATION",
            "requirements": requirements,
        },
    }
    _verify_failed_generalization_payload(payload)

    requirements["candidate_inventory_complete"] = False
    with pytest.raises(RuntimeError, match="boundary changed"):
        _verify_failed_generalization_payload(payload)


def test_second_replay_requires_exact_schema_and_binding_failure() -> None:
    requirements = dict.fromkeys(
        generalization_gate_requirements(_baseline_gate()),
        True,
    )
    for failed in (
        "agent_execution_complete",
        "all_candidates_source_entailed",
        "all_candidates_structure_trusted",
        "binding_rejection_zero",
        "candidate_inventory_complete",
        "independent_categories_agree",
        "invalid_agent_output_zero",
        "sealed_expert_core_recovered",
        "verifier_recognized_finding",
    ):
        requirements[failed] = False
    payload: dict[str, object] = {
        "schema_version": "tg04_generalization_replay.v1",
        "experiment_mode": "adaptive_replay",
        "report_sha256": (
            "9ef7bb42b224610ffc8c5fa04588b5058f877f09431a9013e3fd13150d5f3201"
        ),
        "agent_outputs": {"error_type": "StructuredModelSchemaError"},
        "gate": {
            "passed": False,
            "decision": "STOP_AND_RECALIBRATE_GENERALIZATION",
            "requirements": requirements,
        },
    }
    _verify_failed_adaptive_replay_payload(payload)

    payload["agent_outputs"] = {"error_type": None}
    with pytest.raises(RuntimeError, match="does not authorize"):
        _verify_failed_adaptive_replay_payload(payload)


def test_final_replay_requires_only_binding_and_core_failures() -> None:
    requirements = dict.fromkeys(
        generalization_gate_requirements(_baseline_gate()),
        True,
    )
    requirements["binding_rejection_zero"] = False
    requirements["sealed_expert_core_recovered"] = False
    payload: dict[str, object] = {
        "schema_version": "tg04_generalization_replay.v1",
        "experiment_mode": "adaptive_replay",
        "report_sha256": (
            "41c35bb8bbeb1e416a481001724b592cf32b786ab54ed4c877574b186feca955"
        ),
        "gate_inputs": {
            "binding_rejection_count": 1,
            "trusted_candidate_count": 2,
            "invalid_agent_output_count": 0,
        },
        "gate": {
            "passed": False,
            "decision": "STOP_AND_RECALIBRATE_GENERALIZATION",
            "requirements": requirements,
        },
    }
    _verify_final_replay_payload(payload)

    requirements["all_candidates_structure_trusted"] = False
    with pytest.raises(RuntimeError, match="boundary changed"):
        _verify_final_replay_payload(payload)


def test_generalization_trial_cli_exit_status_follows_gate() -> None:
    assert generalization_trial_exit_code({"gate": {"passed": True}}) == 0
    assert generalization_trial_exit_code({"gate": {"passed": False}}) == 1
    assert generalization_trial_exit_code({}) == 1
    assert generalization_replay_exit_code({"gate": {"passed": True}}) == 0
    assert generalization_replay_exit_code({"gate": {"passed": False}}) == 1
    assert second_replay_exit_code({"gate": {"passed": True}}) == 0
    assert second_replay_exit_code({"gate": {"passed": False}}) == 1
    assert final_replay_exit_code({"gate": {"passed": True}}) == 0
    assert final_replay_exit_code({"gate": {"passed": False}}) == 1
