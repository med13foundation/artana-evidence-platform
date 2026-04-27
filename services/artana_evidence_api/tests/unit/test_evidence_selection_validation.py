"""Tests for evidence-selection validation helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionReviewInput,
    compare_evidence_selection_review,
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
            explanation_quality_score=4,
            high_severity_overclaim_count=0,
            reviewer_notes="One useful record missed.",
        ),
    )

    assert report.true_positive_ids == ("clinvar:VCV1",)
    assert report.run_id == run_id
    assert report.goal == "Find MED13 congenital heart disease evidence."
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
