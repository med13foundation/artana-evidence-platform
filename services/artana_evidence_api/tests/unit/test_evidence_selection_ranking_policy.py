"""Adversarial tests for governed evidence-selection ranking and calibration."""

from __future__ import annotations

import math

import pytest
from artana_evidence_api.evidence_selection.ranking.calibration import (
    build_ranking_probability_calibration_summary,
)
from artana_evidence_api.evidence_selection.ranking.contracts import (
    CalibratedRankingProbability,
    DeterministicRankingWeight,
    RankingCalibrationIdentity,
    RankingCategoricalInput,
    ReviewRankingCalibrationDecision,
    ReviewRankingCalibrationGateThresholds,
    ReviewRankingCalibrationProtocol,
)
from artana_evidence_api.evidence_selection.ranking.fitter import (
    DiagnosticCalibrationTrainingSample,
    calibration_training_set_sha256,
    fit_diagnostic_monotonic_calibrator,
    predict_diagnostic_probability,
)
from artana_evidence_api.evidence_selection.ranking.protocol_integrity import (
    authenticate_calibration_protocol,
)
from artana_evidence_api.evidence_selection_validation import (
    evaluate_review_ranking_calibration_gate,
)
from pydantic import ValidationError

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_operational_ranking_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        _operational_ranking(value)


def test_operational_ranking_rejects_numeric_category_alias() -> None:
    with pytest.raises(ValidationError):
        DeterministicRankingWeight(
            value=1.0,
            policy_id="selection_policy",
            policy_version="v1",
            mapping_version="v1",
            categorical_inputs=(
                RankingCategoricalInput.model_validate(
                    {"field": "model_confidence", "value": "0.99"},
                ),
            ),
        )


def test_calibration_summary_is_explicitly_unavailable_without_probabilities() -> None:
    decisions = (
        _decision("proposal", "positive", 4.0, "positive"),
        _decision("review_item", "abstained", 2.0, "abstained"),
    )

    summary = build_ranking_probability_calibration_summary(decisions)

    assert summary.availability == "unavailable"
    assert summary.sample_count == 2
    assert summary.probability_count == 0
    assert summary.abstention_count == 1
    assert summary.abstention_rate == 0.5
    assert summary.expected_calibration_error is None
    assert summary.reliability_bins == ()


def test_diagnostic_calibrator_is_monotonic_and_saturates() -> None:
    identity = _identity()
    samples = (
        DiagnosticCalibrationTrainingSample(
            research_question_id="train-a",
            operational_ranking=_operational_ranking(0.0),
            outcome_positive=True,
        ),
        DiagnosticCalibrationTrainingSample(
            research_question_id="train-b",
            operational_ranking=_operational_ranking(1.0),
            outcome_positive=False,
        ),
        DiagnosticCalibrationTrainingSample(
            research_question_id="train-c",
            operational_ranking=_operational_ranking(2.0),
            outcome_positive=True,
        ),
    )
    protocol = _protocol(
        identity=identity,
        training_ids=("train-a", "train-b", "train-c"),
        training_set_sha256=calibration_training_set_sha256(samples),
    )
    artifact = fit_diagnostic_monotonic_calibrator(
        protocol=protocol,
        samples=samples,
    )

    assert artifact.calibration_status == "diagnostic"
    assert [point.probability for point in artifact.points] == [0.5, 1.0]
    assert artifact.training_set_sha256 != _HASH_A
    upper = predict_diagnostic_probability(
        artifact=artifact,
        operational_ranking=_operational_ranking(100.0),
    )
    assert upper.value == 1.0
    assert upper.calibration_status == "diagnostic"


def test_calibration_protocol_rejects_question_partition_overlap() -> None:
    with pytest.raises(ValidationError, match="must be disjoint"):
        ReviewRankingCalibrationProtocol(
            identity=_identity(),
            partition_manifest_sha256=_HASH_A,
            training_set_sha256=_HASH_B,
            held_out_set_sha256=_HASH_C,
            training_research_question_ids=("question-overlap",),
            held_out_research_question_ids=("question-overlap",),
            independent_expert_labels=True,
            held_out_protocol="research-question-disjoint-v1",
        )


def test_calibrated_probability_rejects_self_asserted_validated_status() -> None:
    with pytest.raises(ValidationError):
        _probability(identity=_identity(), value=0.9, status="validated")


def test_review_ranking_gate_derives_validation_from_authenticated_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY",
        "ranking-policy-test-key-at-least-32-bytes",
    )
    identity = _identity()
    decision = _decision(
        "proposal",
        "diagnostic",
        4.0,
        "positive",
        probability=_probability(identity=identity, value=0.9, status="diagnostic"),
    )
    protocol = authenticate_calibration_protocol(_protocol(identity=identity))

    report = evaluate_review_ranking_calibration_gate(
        decisions=(decision,),
        calibration_protocol=protocol,
        adjudication_note="Independent reviewer outcome retained.",
        thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=1,
            max_expected_calibration_error=1.0,
            min_roc_auc=0.0,
            min_mean_operational_weight_separation=0.0,
            min_distinct_goals=0,
            min_distinct_evidence_shapes=0,
            min_training_research_questions=1,
            min_held_out_research_questions=1,
            min_observed_held_out_research_questions=1,
            require_proposal_and_review_item_sources=False,
            require_positive_and_negative_outcomes=False,
            require_positive_and_negative_per_source=False,
        ),
    )

    assert report.passed is True
    assert report.calibration.availability == "diagnostic"
    assert report.blocking_reasons == ()


def test_calibrator_rejects_held_out_training_leakage() -> None:
    identity = _identity()
    leaked_samples = (
        DiagnosticCalibrationTrainingSample(
            research_question_id="held-out-a",
            operational_ranking=_operational_ranking(4.0),
            outcome_positive=True,
        ),
    )
    protocol = _protocol(
        identity=identity,
        training_set_sha256=calibration_training_set_sha256(leaked_samples),
    )

    with pytest.raises(ValueError, match="held-out research questions"):
        fit_diagnostic_monotonic_calibrator(
            samples=leaked_samples,
            protocol=protocol,
        )


def test_review_ranking_gate_rejects_tampered_protocol_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY",
        "ranking-policy-test-key-at-least-32-bytes",
    )
    protocol = authenticate_calibration_protocol(_protocol(identity=_identity()))
    tampered = protocol.model_copy(update={"held_out_protocol": "tampered-v2"})

    report = evaluate_review_ranking_calibration_gate(
        decisions=(_decision("proposal", "tampered", 4.0, "positive"),),
        calibration_protocol=tampered,
        thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=1,
            min_roc_auc=0.0,
            min_mean_operational_weight_separation=0.0,
            min_distinct_goals=0,
            min_distinct_evidence_shapes=0,
            min_training_research_questions=1,
            min_held_out_research_questions=1,
            min_observed_held_out_research_questions=1,
            require_calibrated_probabilities=False,
            require_reviewer_ids=False,
            require_adjudication_note=False,
            require_proposal_and_review_item_sources=False,
            require_positive_and_negative_outcomes=False,
            require_positive_and_negative_per_source=False,
        ),
    )

    assert report.passed is False
    assert any("signature does not match" in reason for reason in report.blocking_reasons)


def test_calibration_protocol_rejects_weak_producer_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY",
        "too-short",
    )

    with pytest.raises(ValueError, match="at least 32 bytes"):
        authenticate_calibration_protocol(_protocol(identity=_identity()))


def test_review_ranking_gate_blocks_missing_ece_for_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY",
        "ranking-policy-test-key-at-least-32-bytes",
    )
    protocol = authenticate_calibration_protocol(_protocol(identity=_identity()))

    report = evaluate_review_ranking_calibration_gate(
        decisions=(_decision("proposal", "missing-probability", 4.0, "positive"),),
        calibration_protocol=protocol,
        thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=1,
            min_roc_auc=0.0,
            min_mean_operational_weight_separation=0.0,
            min_distinct_goals=0,
            min_distinct_evidence_shapes=0,
            min_training_research_questions=1,
            min_held_out_research_questions=1,
            min_observed_held_out_research_questions=1,
            require_reviewer_ids=False,
            require_adjudication_note=False,
            require_proposal_and_review_item_sources=False,
            require_positive_and_negative_outcomes=False,
            require_positive_and_negative_per_source=False,
        ),
    )

    assert report.passed is False
    assert any("ECE is unavailable" in reason for reason in report.blocking_reasons)


def test_review_ranking_gate_rejects_policy_version_drift() -> None:
    identity = _identity()
    protocol = _protocol(identity=identity)
    drifted = _decision("proposal", "drifted", 4.0, "positive")
    drifted = drifted.model_copy(
        update={
            "operational_ranking": drifted.operational_ranking.model_copy(
                update={"policy_version": "v2"},
            ),
        },
    )

    report = evaluate_review_ranking_calibration_gate(
        decisions=(drifted,),
        calibration_protocol=protocol,
        thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=1,
            min_roc_auc=0.0,
            min_mean_operational_weight_separation=0.0,
            min_distinct_goals=0,
            min_distinct_evidence_shapes=0,
            min_training_research_questions=1,
            min_held_out_research_questions=1,
            min_observed_held_out_research_questions=1,
            require_calibrated_probabilities=False,
            require_authenticated_protocol=False,
            require_independent_expert_labels=False,
            require_reviewer_ids=False,
            require_adjudication_note=False,
            require_proposal_and_review_item_sources=False,
            require_positive_and_negative_outcomes=False,
            require_positive_and_negative_per_source=False,
        ),
    )

    assert report.passed is False
    assert any("policy identity drifted" in reason for reason in report.blocking_reasons)


def test_review_ranking_gate_counts_observed_held_out_questions() -> None:
    identity = _identity()
    protocol = _protocol(identity=identity).model_copy(
        update={"held_out_research_question_ids": ("held-out-a", "held-out-b")},
    )

    report = evaluate_review_ranking_calibration_gate(
        decisions=(_decision("proposal", "observed-once", 4.0, "positive"),),
        calibration_protocol=protocol,
        thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=1,
            min_roc_auc=0.0,
            min_mean_operational_weight_separation=0.0,
            min_distinct_goals=0,
            min_distinct_evidence_shapes=0,
            min_training_research_questions=1,
            min_held_out_research_questions=2,
            min_observed_held_out_research_questions=2,
            require_calibrated_probabilities=False,
            require_authenticated_protocol=False,
            require_independent_expert_labels=False,
            require_reviewer_ids=False,
            require_adjudication_note=False,
            require_proposal_and_review_item_sources=False,
            require_positive_and_negative_outcomes=False,
            require_positive_and_negative_per_source=False,
        ),
    )

    assert report.passed is False
    assert any("got 1" in reason for reason in report.blocking_reasons)


def _decision(
    source_kind: str,
    item_id: str,
    value: float,
    outcome: str,
    *,
    probability: CalibratedRankingProbability | None = None,
) -> ReviewRankingCalibrationDecision:
    return ReviewRankingCalibrationDecision.model_validate(
        {
            "source_kind": source_kind,
            "item_id": item_id,
            "research_question_id": "held-out-a",
            "operational_ranking": _operational_ranking(value).model_dump(mode="json"),
            "calibrated_probability": (
                probability.model_dump(mode="json")
                if probability is not None
                else None
            ),
            "outcome": outcome,
            "reviewer_id": "reviewer-a",
        },
    )


def _operational_ranking(value: float) -> DeterministicRankingWeight:
    return DeterministicRankingWeight(
        value=value,
        policy_id="test_review_ranking",
        policy_version="v1",
        mapping_version="v1",
        categorical_inputs=(
            RankingCategoricalInput(field="evidence_state", value="supported"),
        ),
    )


def _identity() -> RankingCalibrationIdentity:
    return RankingCalibrationIdentity(
        input_policy_id="test_review_ranking",
        input_policy_version="v1",
        input_mapping_version="v1",
        categorical_schema_version="evidence_categories.v1",
        selector_model_id="openai:test-model",
        selector_prompt_version="v1",
        objective_schema_version="v1",
        corpus_version="expert-pilot-v1",
        calibration_algorithm="isotonic",
        calibration_version="v1",
    )


def _probability(
    *,
    identity: RankingCalibrationIdentity,
    value: float,
    status: str,
) -> CalibratedRankingProbability:
    return CalibratedRankingProbability.model_validate(
        {
            "value": value,
            "calibration_status": status,
            "identity": identity.model_dump(mode="json"),
            "training_set_sha256": _HASH_B,
            "partition_manifest_sha256": _HASH_A,
            "held_out_protocol": "research-question-disjoint-v1",
        },
    )


def _protocol(
    *,
    identity: RankingCalibrationIdentity,
    training_ids: tuple[str, ...] = ("training-a",),
    training_set_sha256: str = _HASH_B,
) -> ReviewRankingCalibrationProtocol:
    return ReviewRankingCalibrationProtocol(
        identity=identity,
        partition_manifest_sha256=_HASH_A,
        training_set_sha256=training_set_sha256,
        held_out_set_sha256=_HASH_C,
        training_research_question_ids=training_ids,
        held_out_research_question_ids=("held-out-a",),
        independent_expert_labels=True,
        held_out_protocol="research-question-disjoint-v1",
    )
