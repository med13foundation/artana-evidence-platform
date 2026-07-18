from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.run_controlled_event_trial import controlled_event_trial_exit_code
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
)
from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.authorization import (
    _verify_authorization_payload,
)
from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.gate import (
    ControlledEventTrialGateInputs,
    controlled_event_trial_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.matching import (
    expert_core_event_match_count,
)
from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.selection import (
    select_controlled_event_trial,
)
from scripts.validation.claim_events.fixture import (
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    load_fixture,
)


def _baseline_gate() -> ControlledEventTrialGateInputs:
    return ControlledEventTrialGateInputs(
        authorization_verified=True,
        selection_verified=True,
        repeat_index=1,
        hidden_expert_event_count=1,
        agent_execution_complete=True,
        extraction_category=SourceUnitEligibilityCategory.FINDING,
        verification_category=SourceUnitEligibilityCategory.FINDING,
        extraction_decision=SourceUnitDecision.EXPLICIT_EVENT,
        verification_coverage=SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        extracted_candidate_count=1,
        verification_decision_count=1,
        entailed_candidate_count=1,
        trusted_candidate_count=1,
        expert_core_event_match_count=1,
        predicted_trusted_event_count=1,
        binding_rejection_count=0,
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


def test_controlled_event_trial_selection_is_frozen_and_fresh() -> None:
    selection = select_controlled_event_trial(
        load_fixture(DEFAULT_DEVELOPMENT_FIXTURE_PATH),
    )

    assert selection.case_id == "bionlp-ge-2011:PMC-2222968-06-Results-05"
    assert selection.unit.index == 11
    assert selection.unit.text == (
        "As described for the human cells, TGF-beta dramatically up-regulated "
        "Foxp3 in the DO11.10 littermate control mice."
    )
    assert len(selection.expert_events) == 1
    assert selection.expert_events[0].trigger_span == "up-regulated"
    assert selection.expert_events[0].event_type.value == "POSITIVE_REGULATION"


def test_controlled_event_trial_gate_fails_closed_on_every_boundary() -> None:
    baseline = _baseline_gate()
    assert all(controlled_event_trial_gate_requirements(baseline).values())

    mutations = (
        {"authorization_verified": False},
        {"selection_verified": False},
        {"repeat_index": 0},
        {"repeat_index": 4},
        {"hidden_expert_event_count": 0},
        {"agent_execution_complete": False},
        {"extraction_category": SourceUnitEligibilityCategory.ABSTAIN},
        {"verification_category": SourceUnitEligibilityCategory.ABSTAIN},
        {"extraction_decision": SourceUnitDecision.ABSTAIN},
        {"verification_coverage": SourceUnitCoverageDecision.MISSING_EVENT},
        {"extracted_candidate_count": 2},
        {"verification_decision_count": 0},
        {"entailed_candidate_count": 0},
        {"trusted_candidate_count": 0},
        {"expert_core_event_match_count": 0},
        {"predicted_trusted_event_count": 2},
        {"binding_rejection_count": 1},
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
            controlled_event_trial_gate_requirements(
                replace(baseline, **mutation),
            ).values(),
        )


def test_structure_replay_authorization_requires_successful_exact_report() -> None:
    payload: dict[str, object] = {
        "schema_version": "tg04_structure_replay.v1",
        "report_sha256": (
            "238b99c275f2c489ac83416363a5ca3cea43e94ea110a75006923f4d7540869e"
        ),
        "gate": {
            "passed": True,
            "decision": "PROCEED_TO_ONE_NEW_HIDDEN_UNIT",
        },
    }
    _verify_authorization_payload(payload)

    failed_gate = dict(payload)
    failed_gate["gate"] = {
        "passed": False,
        "decision": "STOP_AND_RECALIBRATE_STRUCTURE_REVIEW",
    }
    with pytest.raises(RuntimeError, match="did not authorize"):
        _verify_authorization_payload(failed_gate)


def test_expert_core_matching_preserves_valid_additional_arguments() -> None:
    selection = select_controlled_event_trial(
        load_fixture(DEFAULT_DEVELOPMENT_FIXTURE_PATH),
    )
    expert = selection.expert_events[0]
    predicted = {
        "trigger_span": expert.trigger_span,
        "trigger_source_start": expert.trigger_source_start,
        "event_type": expert.event_type.value,
        "polarity": expert.polarity.value,
        "epistemic_status": expert.epistemic_status.value,
        "arguments": [
            *[
                {
                    "event_role": argument.event_role.value,
                    "role": argument.participant_role.value,
                    "exact_span": argument.exact_span,
                    "source_start": argument.source_start,
                }
                for argument in expert.arguments
            ],
            {
                "event_role": "CONTEXT",
                "role": "POPULATION",
                "exact_span": "DO11.10 littermate control mice",
                "source_start": selection.unit.source_start
                + selection.unit.text.index("DO11.10"),
            },
        ],
    }

    assert expert_core_event_match_count((expert,), [predicted]) == 1

    arguments = predicted["arguments"]
    assert isinstance(arguments, list)
    first_argument = arguments[0]
    assert isinstance(first_argument, dict)
    first_argument["event_role"] = "CONTEXT"
    assert expert_core_event_match_count((expert,), [predicted]) == 0


def test_controlled_event_trial_cli_exit_status_follows_gate() -> None:
    assert controlled_event_trial_exit_code({"gate": {"passed": True}}) == 0
    assert controlled_event_trial_exit_code({"gate": {"passed": False}}) == 1
    assert controlled_event_trial_exit_code({}) == 1
