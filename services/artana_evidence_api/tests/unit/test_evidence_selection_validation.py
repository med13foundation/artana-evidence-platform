"""Tests for evidence-selection validation helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyGateThresholds,
    EvidenceSelectionExpertStudyInput,
    EvidenceSelectionReviewInput,
    ReviewRankingCalibrationDecision,
    ReviewRankingCalibrationStudyInput,
    compare_evidence_selection_review,
    evaluate_evidence_selection_expert_study_gate,
)
from pydantic import ValidationError


def test_compare_evidence_selection_review_records_shadow_review_metrics() -> None:
    run_id = uuid4()

    report = compare_evidence_selection_review(
        EvidenceSelectionReviewInput(
            run_id=run_id,
            goal="Find MED13 congenital heart disease evidence.",
            harness_selected_record_ids=("clinvar:VCV1", "clinvar:VCV2"),
            human_selected_record_ids=("clinvar:VCV1", "pubmed:PMID1"),
            harness_skipped_record_ids=("clinvar:VCV3",),
            duplicate_suggestion_ids=("clinvar:VCV2", "clinvar:VCV2"),
            reviewer_id="reviewer-a",
            explanation_quality_score=4,
            high_severity_overclaim_count=0,
            reviewer_notes="One useful record missed.",
        ),
    )

    assert report.true_positive_ids == ("clinvar:VCV1",)
    assert report.run_id == run_id
    assert report.goal == "Find MED13 congenital heart disease evidence."
    assert report.reviewer_id == "reviewer-a"
    assert report.false_positive_ids == ("clinvar:VCV2",)
    assert report.false_negative_ids == ("pubmed:PMID1",)
    assert report.confirmed_skip_ids == ("clinvar:VCV3",)
    assert report.duplicate_suggestion_ids == ("clinvar:VCV2",)
    assert report.precision == 0.5
    assert report.recall == 0.5
    assert report.explanation_quality_score == 4
    assert report.overclaim_gate_passed is True


def test_compare_evidence_selection_review_flags_overclaim_gate_failure() -> None:
    report = compare_evidence_selection_review(
        EvidenceSelectionReviewInput(
            run_id=uuid4(),
            goal="Find MED13 treatment evidence.",
            harness_selected_record_ids=("pubmed:PMID1",),
            human_selected_record_ids=("pubmed:PMID1",),
            high_severity_overclaim_count=1,
        ),
    )

    assert report.overclaim_gate_passed is False
    assert report.high_severity_overclaim_count == 1


def test_evidence_selection_review_input_rejects_invalid_scores() -> None:
    with pytest.raises(ValidationError):
        EvidenceSelectionReviewInput(
            run_id=uuid4(),
            goal="Find MED13 evidence.",
            harness_selected_record_ids=(),
            human_selected_record_ids=(),
            explanation_quality_score=6,
        )


def test_evidence_selection_review_input_rejects_selected_skipped_overlap() -> None:
    with pytest.raises(ValidationError):
        EvidenceSelectionReviewInput(
            run_id=uuid4(),
            goal="Find MED13 evidence.",
            harness_selected_record_ids=("clinvar:VCV1",),
            human_selected_record_ids=(),
            harness_skipped_record_ids=("clinvar:VCV1",),
        )


def test_evidence_selection_expert_study_gate_passes_balanced_study() -> None:
    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="balanced-shadow-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews=_selection_reviews(),
            review_ranking=_review_ranking_study(),
            description="Multi-goal expert shadow-review study.",
        ),
        thresholds=EvidenceSelectionExpertStudyGateThresholds(
            min_selection_review_count=3,
            min_distinct_selection_goals=3,
            min_selection_reviewer_count=1,
            min_mean_precision=0.8,
            min_mean_recall=0.8,
            min_mean_explanation_quality=3.0,
        ),
    )

    assert report.passed is True
    assert report.status == "passed"
    assert report.blocking_reasons == ()
    assert report.selection_summary["review_count"] == 3
    assert report.selection_summary["distinct_goal_count"] == 3
    assert report.selection_summary["reviewer_count"] == 1
    assert report.selection_summary["mean_precision"] == 1.0
    assert report.selection_summary["mean_recall"] == 1.0
    assert report.selection_summary["high_severity_overclaim_count"] == 0
    assert report.selection_summary["study_evidence_kind"] == "real_shadow_review"
    assert report.review_ranking_gate.passed is True


def test_evidence_selection_expert_study_gate_blocks_synthetic_studies() -> None:
    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="synthetic-shadow-study",
            study_evidence_kind="synthetic_fixture",
            selection_reviews=_selection_reviews(),
            review_ranking=_review_ranking_study(),
            description="Synthetic mechanics proof for the study gate.",
        ),
        thresholds=EvidenceSelectionExpertStudyGateThresholds(
            min_selection_review_count=3,
            min_distinct_selection_goals=3,
            min_selection_reviewer_count=1,
            min_mean_precision=0.8,
            min_mean_recall=0.8,
            min_mean_explanation_quality=3.0,
        ),
    )

    assert report.passed is False
    assert any("real shadow-review evidence" in reason for reason in report.blocking_reasons)


def test_evidence_selection_expert_study_gate_blocks_partially_unlabeled_reviews() -> None:
    reviews = list(_selection_reviews())
    first_review = reviews[0]
    reviews[0] = EvidenceSelectionReviewInput(
        run_id=first_review.run_id,
        goal=first_review.goal,
        reviewer_id=None,
        harness_selected_record_ids=first_review.harness_selected_record_ids,
        human_selected_record_ids=first_review.human_selected_record_ids,
        harness_skipped_record_ids=first_review.harness_skipped_record_ids,
        explanation_quality_score=first_review.explanation_quality_score,
        high_severity_overclaim_count=first_review.high_severity_overclaim_count,
    )
    second_review = reviews[1]
    reviews[1] = EvidenceSelectionReviewInput(
        run_id=second_review.run_id,
        goal="   ",
        reviewer_id=second_review.reviewer_id,
        harness_selected_record_ids=second_review.harness_selected_record_ids,
        human_selected_record_ids=second_review.human_selected_record_ids,
        harness_skipped_record_ids=second_review.harness_skipped_record_ids,
        explanation_quality_score=second_review.explanation_quality_score,
        high_severity_overclaim_count=second_review.high_severity_overclaim_count,
    )

    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="partially-unlabeled-shadow-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews=tuple(reviews),
            review_ranking=_review_ranking_study(),
        ),
        thresholds=EvidenceSelectionExpertStudyGateThresholds(
            min_selection_review_count=3,
            min_distinct_selection_goals=2,
            min_selection_reviewer_count=1,
            min_mean_precision=0.8,
            min_mean_recall=0.8,
            min_mean_explanation_quality=3.0,
        ),
    )

    assert report.passed is False
    assert report.selection_summary["missing_reviewer_id_count"] == 1
    assert report.selection_summary["missing_goal_count"] == 1
    assert any("Every selection review must include a reviewer ID" in reason for reason in report.blocking_reasons)
    assert any("Every selection review must include a research goal" in reason for reason in report.blocking_reasons)


def test_evidence_selection_expert_study_gate_blocks_unmeasurable_selection_metrics() -> None:
    reviews = list(_selection_reviews())
    for index in (0, 1):
        review = reviews[index]
        reviews[index] = EvidenceSelectionReviewInput(
            run_id=review.run_id,
            goal=review.goal,
            reviewer_id=review.reviewer_id,
            harness_selected_record_ids=(),
            human_selected_record_ids=(),
            harness_skipped_record_ids=review.harness_skipped_record_ids,
            explanation_quality_score=None,
            high_severity_overclaim_count=0,
        )

    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="unmeasurable-shadow-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews=tuple(reviews),
            review_ranking=_review_ranking_study(),
        ),
        thresholds=EvidenceSelectionExpertStudyGateThresholds(
            min_selection_review_count=3,
            min_distinct_selection_goals=3,
            min_selection_reviewer_count=1,
            min_mean_precision=0.8,
            min_mean_recall=0.8,
            min_mean_explanation_quality=3.0,
        ),
    )

    assert report.passed is False
    assert report.selection_summary["unmeasurable_precision_count"] == 2
    assert report.selection_summary["unmeasurable_recall_count"] == 2
    assert report.selection_summary["missing_explanation_quality_count"] == 2
    assert any("measurable precision" in reason for reason in report.blocking_reasons)
    assert any("measurable recall" in reason for reason in report.blocking_reasons)
    assert any("explanation-quality score" in reason for reason in report.blocking_reasons)


def test_evidence_selection_expert_study_gate_blocks_weak_or_underreviewed_study() -> None:
    weak_reviews = (
        EvidenceSelectionReviewInput(
            run_id=uuid4(),
            goal="Find MED13 congenital heart disease evidence.",
            reviewer_id=None,
            harness_selected_record_ids=("record-fp",),
            human_selected_record_ids=("record-tp",),
            explanation_quality_score=2,
            high_severity_overclaim_count=1,
        ),
    )

    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="weak-shadow-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews=weak_reviews,
            review_ranking=ReviewRankingCalibrationStudyInput(
                schema_version="evidence_selection_review_ranking_calibration.v1",
                study_id="undercovered-ranking",
                decisions=_review_ranking_decisions()[:2],
                adjudication_note=None,
            ),
        ),
        thresholds=EvidenceSelectionExpertStudyGateThresholds(
            min_selection_review_count=3,
            min_distinct_selection_goals=3,
            min_selection_reviewer_count=1,
            min_mean_precision=0.8,
            min_mean_recall=0.8,
            min_mean_explanation_quality=3.0,
        ),
    )

    assert report.passed is False
    assert report.status == "failed"
    assert any("selection review runs" in reason for reason in report.blocking_reasons)
    assert any("distinct selection goals" in reason for reason in report.blocking_reasons)
    assert any("selection reviewer" in reason for reason in report.blocking_reasons)
    assert any("mean selection precision" in reason for reason in report.blocking_reasons)
    assert any("mean selection recall" in reason for reason in report.blocking_reasons)
    assert any("explanation quality" in reason for reason in report.blocking_reasons)
    assert any("overclaim" in reason for reason in report.blocking_reasons)
    assert any("Review-ranking gate failed" in reason for reason in report.blocking_reasons)


def test_evidence_selection_expert_study_input_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EvidenceSelectionExpertStudyInput.model_validate(
            {
                "schema_version": "evidence_selection_expert_study.v1",
                "study_id": "extra-field",
                "study_evidence_kind": "real_shadow_review",
                "selection_reviews": [],
                "review_ranking": {
                    "schema_version": (
                        "evidence_selection_review_ranking_calibration.v1"
                    ),
                    "study_id": "ranking",
                    "decisions": [],
                },
                "unexpected": "ignored would make study evidence unsafe",
            },
        )


def test_evidence_selection_expert_study_input_rejects_extra_selection_fields() -> None:
    payload = {
        "schema_version": "evidence_selection_expert_study.v1",
        "study_id": "extra-selection-field",
        "study_evidence_kind": "real_shadow_review",
        "selection_reviews": [
            {
                "run_id": "00000000-0000-0000-0000-000000000001",
                "goal": "Find MED13 evidence.",
                "reviewer_id": "reviewer-a",
                "harness_selected_record_ids": ["record-a"],
                "human_selected_record_ids": ["record-a"],
                "unexpected_selection_field": "hidden typo",
            },
        ],
        "review_ranking": {
            "schema_version": "evidence_selection_review_ranking_calibration.v1",
            "study_id": "ranking",
            "decisions": [],
        },
    }

    with pytest.raises(ValidationError, match="unexpected_selection_field"):
        EvidenceSelectionExpertStudyInput.model_validate(payload)


def _selection_reviews() -> tuple[EvidenceSelectionReviewInput, ...]:
    goals = (
        "Find MED13 congenital heart disease evidence.",
        "Find EGFR inhibitor response evidence.",
        "Find NTRK fusion treatment evidence.",
    )
    return tuple(
        EvidenceSelectionReviewInput(
            run_id=uuid4(),
            goal=goal,
            reviewer_id="reviewer-a",
            harness_selected_record_ids=(f"record-{index}-a", f"record-{index}-b"),
            human_selected_record_ids=(f"record-{index}-a", f"record-{index}-b"),
            harness_skipped_record_ids=(f"record-{index}-c",),
            explanation_quality_score=4,
            high_severity_overclaim_count=0,
        )
        for index, goal in enumerate(goals)
    )


def _review_ranking_study() -> ReviewRankingCalibrationStudyInput:
    return ReviewRankingCalibrationStudyInput(
        schema_version="evidence_selection_review_ranking_calibration.v1",
        study_id="balanced-ranking",
        decisions=_review_ranking_decisions(),
        adjudication_note="No reviewer disagreements in this calibration sample.",
    )


def _review_ranking_decisions() -> tuple[ReviewRankingCalibrationDecision, ...]:
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
        _review_ranking_decision(
            source_kind="proposal" if index % 2 == 0 else "review_item",
            item_id=f"positive-{index}",
            ranking_score=1.0,
            outcome="positive",
            goal=goals[index % len(goals)],
            evidence_shape=evidence_shapes[index % len(evidence_shapes)],
        )
        for index in range(5)
    )
    negative_decisions = tuple(
        _review_ranking_decision(
            source_kind="proposal" if index % 2 == 0 else "review_item",
            item_id=f"negative-{index}",
            ranking_score=0.0,
            outcome="negative",
            goal=goals[index % len(goals)],
            evidence_shape=evidence_shapes[index % len(evidence_shapes)],
        )
        for index in range(5)
    )
    return positive_decisions + negative_decisions


def _review_ranking_decision(
    *,
    source_kind: str,
    item_id: str,
    ranking_score: float,
    outcome: str,
    goal: str,
    evidence_shape: str,
) -> ReviewRankingCalibrationDecision:
    return ReviewRankingCalibrationDecision.model_validate(
        {
            "source_kind": source_kind,
            "item_id": item_id,
            "ranking_score": ranking_score,
            "outcome": outcome,
            "goal": goal,
            "reviewer_id": "reviewer-a",
            "evidence_shape": evidence_shape,
        },
    )
