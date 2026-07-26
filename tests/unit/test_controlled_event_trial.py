from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
from artana_evidence_api.document_extraction import normalize_text_document

from scripts.run_controlled_event_replay import controlled_event_replay_exit_code
from scripts.run_controlled_event_trial import controlled_event_trial_exit_code
from scripts.validation.claim_events.corpus_text import (
    RESTRICTED_CORPUS_SKIP_REASON,
    corpus_is_available,
)
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
from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.reassessment_gate import (
    ReassessmentGateInputs,
    reassessment_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.replay_authorization import (
    _verify_failed_trial_payload,
)
from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.selection import (
    select_controlled_event_trial,
)
from scripts.validation.claim_events.fixture import (
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    load_fixture,
)

#: These checks read the corpus text itself, which this public repository does
#: not carry.  They are skipped, never deleted: the reason names the licence and
#: the exact command that restores them.
requires_corpus = pytest.mark.skipif(
    not corpus_is_available(),
    reason=RESTRICTED_CORPUS_SKIP_REASON,
)


def _baseline_gate() -> ControlledEventTrialGateInputs:
    return ControlledEventTrialGateInputs(
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


@requires_corpus
def test_controlled_event_trial_selection_is_frozen_and_fresh() -> None:
    selection = select_controlled_event_trial(
        load_fixture(DEFAULT_DEVELOPMENT_FIXTURE_PATH),
    )

    assert selection.case_id == "bionlp-ge-2011:PMC-2222968-06-Results-05"
    assert selection.unit.index == 11
    # The corpus sentence is licence-restricted, so it is pinned by digest
    # rather than quoted.  See scripts/validation/RESTRICTED_CORPORA.md.
    assert hashlib.sha256(selection.unit.text.encode("utf-8")).hexdigest() == (
        "e305c7e19ea6e6e2a7014b3a3a021623b5e5ec756477c81cf5716e8861e0dc04"
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


@requires_corpus
def test_expert_core_matching_preserves_valid_additional_arguments() -> None:
    """A *valid* extra argument, and the validity is checked rather than assumed.

    The matcher accepts a prediction whose arguments are a superset of the
    expert's, so the additional argument here is the whole subject: it has to
    be one a trusted extractor could actually have produced, which means its
    span has to occur in the source at the offset it declares.

    The 2026-07-25 redaction broke exactly that and nothing noticed.  The
    corpus wording was replaced with a paraphrase while `source_start` kept
    pointing at the offset of `DO11.10`, so the declared span no longer
    occurred at the declared offset -- and the test still passed, because a
    superset check ignores extra arguments whether they are well formed or
    not.  What survived was a demonstration that the matcher tolerates a
    *malformed* extra argument, under the name of one about a valid one.

    So the binding is now asserted, against the case document rather than
    against the substring search that produced the offset.  `DO11.10` is a
    strain name, which `scripts/validation/RESTRICTED_CORPORA.md` commits, and
    it occurs where it says it does.
    """

    fixture = load_fixture(DEFAULT_DEVELOPMENT_FIXTURE_PATH)
    selection = select_controlled_event_trial(fixture)
    expert = selection.expert_events[0]

    case = next(item for item in fixture.cases if item.case_id == selection.case_id)
    document = normalize_text_document(case.source_text)
    additional_span = "DO11.10"
    additional_start = selection.unit.source_start + selection.unit.text.index(
        additional_span,
    )
    assert document[additional_start : additional_start + len(additional_span)] == (
        additional_span
    ), "the additional argument must be source-bound, or it tests nothing"

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
                "exact_span": additional_span,
                "source_start": additional_start,
            },
        ],
    }

    assert expert_core_event_match_count((expert,), [predicted]) == 1

    predicted["trigger_span"] = f"dramatically {expert.trigger_span}"
    predicted["trigger_source_start"] = expert.trigger_source_start - len(
        "dramatically "
    )
    assert expert_core_event_match_count((expert,), [predicted]) == 1

    predicted["trigger_source_start"] = expert.trigger_source_start
    assert expert_core_event_match_count((expert,), [predicted]) == 0
    predicted["trigger_source_start"] = expert.trigger_source_start - len(
        "dramatically "
    )

    arguments = predicted["arguments"]
    assert isinstance(arguments, list)
    first_argument = arguments[0]
    assert isinstance(first_argument, dict)
    first_argument["event_role"] = "CONTEXT"
    assert expert_core_event_match_count((expert,), [predicted]) == 0


def test_adaptive_replay_requires_exact_failed_gate() -> None:
    payload: dict[str, object] = {
        "schema_version": "tg04_controlled_event_trial.v1",
        "report_sha256": (
            "1503f4f1de58ab8156d960c4d4f9c888d2716bcb39255bc1b03ab95ee24464cc"
        ),
        "repeat_index": 1,
        "unit": {
            "unit_id": (
                "source-unit-02c41780fd8d83965debdc337f89adce6283552fa76ac7d36ee12c56060ef21b"
            ),
        },
        "gate": {
            "passed": False,
            "decision": "STOP_AND_RECALIBRATE_CONTROLLED_EVENT_EXTRACTION",
            "requirements": {
                "sealed_expert_core_recovered": False,
                "provider_receipts_verified": False,
            },
        },
    }
    _verify_failed_trial_payload(payload)

    passed = dict(payload)
    passed["gate"] = {
        "passed": True,
        "decision": "PROCEED_TO_NEXT_REPEAT_OR_SOURCE_REVIEW",
        "requirements": {
            "sealed_expert_core_recovered": True,
            "provider_receipts_verified": True,
        },
    }
    with pytest.raises(RuntimeError, match="does not authorize"):
        _verify_failed_trial_payload(passed)


def test_offline_reassessment_gate_fails_closed_on_every_boundary() -> None:
    baseline = ReassessmentGateInputs(
        artifact_verified=True,
        adaptive_replay_declared=True,
        offline_reassessment_declared=True,
        model_call_count=0,
        source_identity_verified=True,
        prior_only_failed_requirement_was_matcher=True,
        prior_provider_receipts_verified=True,
        trusted_event_count=1,
        expert_core_event_match_count=1,
    )
    assert all(reassessment_gate_requirements(baseline).values())

    mutations = (
        {"artifact_verified": False},
        {"adaptive_replay_declared": False},
        {"offline_reassessment_declared": False},
        {"model_call_count": 1},
        {"source_identity_verified": False},
        {"prior_only_failed_requirement_was_matcher": False},
        {"prior_provider_receipts_verified": False},
        {"trusted_event_count": 0},
        {"expert_core_event_match_count": 0},
    )
    for mutation in mutations:
        assert not all(
            reassessment_gate_requirements(
                replace(baseline, **mutation),
            ).values(),
        )


def test_controlled_event_trial_cli_exit_status_follows_gate() -> None:
    assert controlled_event_trial_exit_code({"gate": {"passed": True}}) == 0
    assert controlled_event_trial_exit_code({"gate": {"passed": False}}) == 1
    assert controlled_event_trial_exit_code({}) == 1
    assert controlled_event_replay_exit_code({"gate": {"passed": True}}) == 0
    assert controlled_event_replay_exit_code({"gate": {"passed": False}}) == 1
