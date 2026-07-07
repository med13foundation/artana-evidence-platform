"""Tests for expert/shadow review-ranking calibration gates."""

from __future__ import annotations

import pytest
from artana_evidence_api.evidence_selection_validation import (
    ReviewRankingCalibrationDecision,
    ReviewRankingCalibrationGateThresholds,
    evaluate_review_ranking_calibration_gate,
)
from pydantic import ValidationError


def test_review_ranking_calibration_gate_passes_balanced_shadow_set() -> None:
    report = evaluate_review_ranking_calibration_gate(
        decisions=(
            _decision(
                "proposal",
                "proposal-1",
                0.95,
                "positive",
                goal="Find MED13 congenital heart disease evidence.",
                reviewer_id="reviewer-a",
                evidence_shape="variant_disease_relation",
            ),
            _decision(
                "review_item",
                "review-item-1",
                0.9,
                "positive",
                goal="Find EGFR inhibitor response evidence.",
                reviewer_id="reviewer-a",
                evidence_shape="drug_response_relation",
            ),
            _decision(
                "proposal",
                "proposal-2",
                0.05,
                "negative",
                goal="Find NTRK fusion treatment evidence.",
                reviewer_id="reviewer-a",
                evidence_shape="fusion_treatment_relation",
            ),
            _decision(
                "review_item",
                "review-item-2",
                0.1,
                "negative",
                goal="Find MED13 congenital heart disease evidence.",
                reviewer_id="reviewer-a",
                evidence_shape="variant_disease_relation",
            ),
        ),
        adjudication_note="No reviewer disagreements in this calibration sample.",
        thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=4,
            max_expected_calibration_error=0.08,
        ),
    )

    assert report.passed is True
    assert report.status == "passed"
    assert report.blocking_reasons == ()
    assert report.calibration.sample_count == 4
    assert report.calibration.mean_score == 0.5
    assert report.calibration.observed_positive_rate == 0.5
    assert report.calibration.expected_calibration_error == 0.075
    assert report.roc_auc == 1.0
    assert report.mean_score_separation == 0.85
    assert report.source_counts == {"proposal": 2, "review_item": 2}
    assert report.outcome_counts == {"negative": 2, "positive": 2}


def test_review_ranking_calibration_gate_defaults_block_metadata_bypass() -> None:
    report = evaluate_review_ranking_calibration_gate(
        decisions=_strict_score_decisions_without_study_metadata(),
    )

    assert report.passed is False
    assert report.calibration.expected_calibration_error == 0.0
    assert report.roc_auc == 1.0
    assert any("distinct research goals" in reason for reason in report.blocking_reasons)
    assert any("distinct evidence shapes" in reason for reason in report.blocking_reasons)
    assert any("reviewer ID" in reason for reason in report.blocking_reasons)
    assert any("adjudication note" in reason for reason in report.blocking_reasons)


def test_review_ranking_calibration_gate_fails_closed_for_weak_review_sets() -> None:
    report = evaluate_review_ranking_calibration_gate(
        decisions=(
            _decision("proposal", "duplicate", 0.9, "positive"),
            _decision("proposal", "duplicate", 0.8, "positive"),
            _decision("proposal", "proposal-3", 0.7, "positive"),
        ),
        thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=4,
            max_expected_calibration_error=0.01,
        ),
    )

    assert report.passed is False
    assert report.status == "failed"
    assert any("At least 4" in reason for reason in report.blocking_reasons)
    assert any("negative reviewer outcome" in reason for reason in report.blocking_reasons)
    assert any("review_item source" in reason for reason in report.blocking_reasons)
    assert any("Duplicate" in reason for reason in report.blocking_reasons)
    assert any("ECE is above target" in reason for reason in report.blocking_reasons)


def test_review_ranking_calibration_gate_blocks_missing_reviewer_ids() -> None:
    decisions = list(_strict_passing_decisions())
    first_decision = decisions[0]
    decisions[0] = _decision(
        first_decision.source_kind,
        first_decision.item_id,
        first_decision.ranking_score,
        first_decision.outcome,
        goal=first_decision.goal,
        reviewer_id=None,
        evidence_shape=first_decision.evidence_shape,
    )

    report = evaluate_review_ranking_calibration_gate(
        decisions=tuple(decisions),
        adjudication_note="No reviewer disagreements in this calibration sample.",
    )

    assert report.passed is False
    assert report.study_design["missing_reviewer_id_count"] == 1
    assert any("reviewer ID" in reason for reason in report.blocking_reasons)


def test_review_ranking_calibration_gate_blocks_blank_adjudication_notes() -> None:
    report = evaluate_review_ranking_calibration_gate(
        decisions=_strict_passing_decisions(),
        adjudication_note="   ",
    )

    assert report.passed is False
    assert report.study_design["adjudication_note_present"] is False
    assert any("adjudication note" in reason for reason in report.blocking_reasons)


def test_review_ranking_calibration_gate_counts_normalized_study_labels() -> None:
    decisions = tuple(
        _decision(
            decision.source_kind,
            decision.item_id,
            decision.ranking_score,
            decision.outcome,
            goal=goal,
            reviewer_id=decision.reviewer_id,
            evidence_shape=evidence_shape,
        )
        for decision, goal, evidence_shape in zip(
            _strict_passing_decisions(),
            (
                "Find MED13 evidence",
                " find   med13 evidence ",
                "FIND MED13 EVIDENCE",
                "Find MED13 evidence",
                " find   med13 evidence ",
                "FIND MED13 EVIDENCE",
                "Find MED13 evidence",
                " find   med13 evidence ",
                "FIND MED13 EVIDENCE",
                "Find MED13 evidence",
            ),
            (
                "variant_disease_relation",
                "Variant Disease Relation",
                "variant-disease-relation",
                "variant_disease_relation",
                "Variant Disease Relation",
                "variant-disease-relation",
                "variant_disease_relation",
                "Variant Disease Relation",
                "variant-disease-relation",
                "variant_disease_relation",
            ),
            strict=True,
        )
    )

    report = evaluate_review_ranking_calibration_gate(
        decisions=decisions,
        adjudication_note="No reviewer disagreements in this calibration sample.",
    )

    assert report.passed is False
    assert report.study_design["distinct_goal_count"] == 1
    assert report.study_design["distinct_evidence_shape_count"] == 1
    assert any("distinct research goals" in reason for reason in report.blocking_reasons)
    assert any("distinct evidence shapes" in reason for reason in report.blocking_reasons)


def test_review_ranking_calibration_gate_blocks_constant_base_rate_scores() -> None:
    report = evaluate_review_ranking_calibration_gate(
        decisions=(
            _decision("proposal", "positive-1", 0.7, "positive"),
            _decision("review_item", "positive-2", 0.7, "positive"),
            _decision("proposal", "positive-3", 0.7, "positive"),
            _decision("review_item", "positive-4", 0.7, "positive"),
            _decision("proposal", "positive-5", 0.7, "positive"),
            _decision("review_item", "positive-6", 0.7, "positive"),
            _decision("proposal", "positive-7", 0.7, "positive"),
            _decision("review_item", "negative-1", 0.7, "negative"),
            _decision("proposal", "negative-2", 0.7, "negative"),
            _decision("review_item", "negative-3", 0.7, "negative"),
        ),
    )

    assert report.passed is False
    assert report.calibration.expected_calibration_error == 0.0
    assert report.roc_auc == 0.5
    assert report.mean_score_separation == 0.0
    assert any("ROC AUC" in reason for reason in report.blocking_reasons)
    assert any("score separation" in reason for reason in report.blocking_reasons)


def test_review_ranking_calibration_gate_blocks_undercovered_study_design() -> None:
    report = evaluate_review_ranking_calibration_gate(
        decisions=(
            _decision(
                "proposal",
                "positive-1",
                0.95,
                "positive",
                goal="Find MED13 evidence.",
                reviewer_id="reviewer-a",
                evidence_shape="variant_relation",
            ),
            _decision(
                "review_item",
                "positive-2",
                0.9,
                "positive",
                goal="Find MED13 evidence.",
                reviewer_id="reviewer-a",
                evidence_shape="variant_relation",
            ),
            _decision(
                "proposal",
                "negative-1",
                0.05,
                "negative",
                goal="Find MED13 evidence.",
                reviewer_id="reviewer-a",
                evidence_shape="variant_relation",
            ),
            _decision(
                "review_item",
                "negative-2",
                0.1,
                "negative",
                goal="Find MED13 evidence.",
                reviewer_id="reviewer-a",
                evidence_shape="variant_relation",
            ),
        ),
        adjudication_note=None,
        thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=4,
            max_expected_calibration_error=0.15,
            min_distinct_goals=3,
            min_distinct_evidence_shapes=3,
            require_reviewer_ids=True,
            require_adjudication_note=True,
        ),
    )

    assert report.passed is False
    assert report.study_design["distinct_goal_count"] == 1
    assert report.study_design["distinct_evidence_shape_count"] == 1
    assert any("distinct research goals" in reason for reason in report.blocking_reasons)
    assert any("distinct evidence shapes" in reason for reason in report.blocking_reasons)
    assert any("adjudication note" in reason for reason in report.blocking_reasons)


def test_review_ranking_calibration_decision_rejects_invalid_labels() -> None:
    with pytest.raises(ValidationError):
        ReviewRankingCalibrationDecision.model_validate(
            {
                "source_kind": "document",
                "item_id": "item-1",
                "ranking_score": 0.5,
                "outcome": "positive",
            },
        )

    with pytest.raises(ValidationError):
        ReviewRankingCalibrationDecision.model_validate(
            {
                "source_kind": "proposal",
                "item_id": "item-1",
                "ranking_score": 1.2,
                "outcome": "positive",
            },
        )

    with pytest.raises(ValidationError):
        ReviewRankingCalibrationDecision.model_validate(
            {
                "source_kind": "proposal",
                "item_id": "item-1",
                "ranking_score": 0.5,
                "outcome": "maybe",
            },
        )

    with pytest.raises(ValidationError):
        ReviewRankingCalibrationDecision.model_validate(
            {
                "source_kind": "proposal",
                "item_id": "item-1",
                "ranking_score": 0.5,
                "outcome": "positive",
                "unexpected": "ignored would be unsafe",
            },
        )


def _decision(
    source_kind: str,
    item_id: str,
    ranking_score: float,
    outcome: str,
    *,
    goal: str | None = None,
    reviewer_id: str | None = None,
    evidence_shape: str | None = None,
) -> ReviewRankingCalibrationDecision:
    return ReviewRankingCalibrationDecision.model_validate(
        {
            "source_kind": source_kind,
            "item_id": item_id,
            "ranking_score": ranking_score,
            "outcome": outcome,
            "goal": goal,
            "reviewer_id": reviewer_id,
            "evidence_shape": evidence_shape,
        },
    )


def _strict_score_decisions_without_study_metadata() -> tuple[
    ReviewRankingCalibrationDecision,
    ...,
]:
    return tuple(
        _decision(
            "proposal" if index % 2 == 0 else "review_item",
            f"positive-{index}",
            1.0,
            "positive",
        )
        for index in range(5)
    ) + tuple(
        _decision(
            "proposal" if index % 2 == 0 else "review_item",
            f"negative-{index}",
            0.0,
            "negative",
        )
        for index in range(5)
    )


def _strict_passing_decisions() -> tuple[ReviewRankingCalibrationDecision, ...]:
    goals = (
        "Find MED13 congenital heart disease evidence.",
        "Find EGFR inhibitor response evidence.",
        "Find NTRK fusion treatment evidence.",
    )
    evidence_shapes = (
        "variant_disease_relation",
        "drug_response_relation",
        "fusion_treatment_relation",
    )
    positive_decisions = tuple(
        _decision(
            "proposal" if index % 2 == 0 else "review_item",
            f"positive-{index}",
            1.0,
            "positive",
            goal=goals[index % len(goals)],
            reviewer_id="reviewer-a",
            evidence_shape=evidence_shapes[index % len(evidence_shapes)],
        )
        for index in range(5)
    )
    negative_decisions = tuple(
        _decision(
            "proposal" if index % 2 == 0 else "review_item",
            f"negative-{index}",
            0.0,
            "negative",
            goal=goals[index % len(goals)],
            reviewer_id="reviewer-a",
            evidence_shape=evidence_shapes[index % len(evidence_shapes)],
        )
        for index in range(5)
    )
    return positive_decisions + negative_decisions
