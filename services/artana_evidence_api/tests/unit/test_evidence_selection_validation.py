"""Tests for evidence-selection validation helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.evidence_selection.provenance import (
    EvidenceSelectionExpertStudySourceManifest,
)
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


def test_evidence_selection_review_input_rejects_blank_record_ids() -> None:
    with pytest.raises(ValidationError, match="record IDs must not be blank"):
        EvidenceSelectionReviewInput(
            run_id=uuid4(),
            goal="Find MED13 evidence.",
            harness_selected_record_ids=("   ",),
            human_selected_record_ids=("record-a",),
        )


def test_evidence_selection_review_input_accepts_documented_audit_notes() -> None:
    review = EvidenceSelectionReviewInput(
        run_id=uuid4(),
        goal="Find MED13 evidence.",
        harness_selected_record_ids=("record-a",),
        human_selected_record_ids=("record-a",),
        false_positive_notes={},
        false_negative_notes={"record-b": "Relevant record was omitted."},
    )

    assert review.false_positive_notes == {}
    assert review.false_negative_notes == {
        "record-b": "Relevant record was omitted."
    }


@pytest.mark.parametrize(
    ("field_name", "notes", "message"),
    [
        ("false_positive_notes", {" ": "Unsupported."}, "record IDs"),
        ("false_negative_notes", {"record-a": "  "}, "must not be blank"),
    ],
)
def test_evidence_selection_review_input_rejects_invalid_audit_notes(
    field_name: str,
    notes: dict[str, str],
    message: str,
) -> None:
    payload: dict[str, object] = {
        "run_id": uuid4(),
        "goal": "Find MED13 evidence.",
        "harness_selected_record_ids": (),
        "human_selected_record_ids": (),
        field_name: notes,
    }

    with pytest.raises(ValidationError, match=message):
        EvidenceSelectionReviewInput.model_validate(payload)


def test_expert_study_ids_are_normalized_before_binding() -> None:
    study = EvidenceSelectionExpertStudyInput(
        schema_version="evidence_selection_expert_study.v1",
        study_id="  balanced-shadow-study  ",
        study_evidence_kind="real_shadow_review",
        selection_reviews=_selection_reviews(),
        review_ranking=_review_ranking_study("balanced-shadow-study"),
    )

    assert study.study_id == "balanced-shadow-study"
    assert study.review_ranking.study_id == "balanced-shadow-study"


@pytest.mark.parametrize("study_id", ["", " ", "\t\n"])
def test_review_ranking_study_rejects_blank_study_ids(study_id: str) -> None:
    with pytest.raises(ValidationError, match="study_id must not be blank"):
        _review_ranking_study(study_id)


def test_expert_study_rejects_blank_outer_study_id() -> None:
    with pytest.raises(ValidationError, match="study_id must not be blank"):
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="  ",
            study_evidence_kind="real_shadow_review",
            selection_reviews=_selection_reviews(),
            review_ranking=_review_ranking_study("balanced-shadow-study"),
        )


def test_evidence_selection_expert_study_gate_passes_balanced_study() -> None:
    selection_reviews = _selection_reviews()
    review_ranking = _review_ranking_study("balanced-shadow-study")
    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="balanced-shadow-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews=selection_reviews,
            review_ranking=review_ranking,
            source_manifest=_source_manifest(selection_reviews=selection_reviews),
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
    assert report.provenance_summary["source_manifest_present"] is True
    assert report.provenance_summary["artifact_count"] == 3
    assert report.provenance_summary["missing_selection_run_id_count"] == 0
    assert report.provenance_summary["missing_review_ranking_decision_key_count"] == 0
    assert report.provenance_summary["unknown_reviewer_id_count"] == 0
    assert report.review_ranking_gate.passed is True


def test_evidence_selection_expert_study_gate_blocks_missing_source_manifest() -> None:
    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="missing-source-manifest",
            study_evidence_kind="real_shadow_review",
            selection_reviews=_selection_reviews(),
            review_ranking=_review_ranking_study("missing-source-manifest"),
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
    assert report.provenance_summary["source_manifest_present"] is False
    assert any(
        "source manifest" in reason for reason in report.blocking_reasons
    )


def test_evidence_selection_expert_study_gate_blocks_incomplete_source_manifest() -> None:
    selection_reviews = _selection_reviews()
    review_ranking = _review_ranking_study("incomplete-source-manifest")
    manifest = _source_manifest_payload(selection_reviews=selection_reviews)
    manifest["source_artifacts"] = manifest["source_artifacts"][:1]
    manifest["selection_review_run_ids"] = manifest["selection_review_run_ids"][:2]
    manifest["review_ranking_decision_keys"] = (
        manifest["review_ranking_decision_keys"][:9]
        + ["review_item:unexpected-ranking-item"]
    )
    manifest["reviewer_roster"] = ["other-reviewer"]

    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput.model_validate(
            {
                "schema_version": "evidence_selection_expert_study.v1",
                    "study_id": "incomplete-source-manifest",
                    "study_evidence_kind": "real_shadow_review",
                    "selection_reviews": [
                        review.model_dump(mode="json")
                        for review in selection_reviews
                    ],
                    "review_ranking": review_ranking.model_dump(mode="json"),
                    "source_manifest": manifest,
                },
        ),
        thresholds=EvidenceSelectionExpertStudyGateThresholds(
            min_selection_review_count=3,
            min_distinct_selection_goals=3,
            min_selection_reviewer_count=1,
            min_mean_precision=0.8,
            min_mean_recall=0.8,
            min_mean_explanation_quality=3.0,
            min_source_artifact_count=3,
        ),
    )

    assert report.passed is False
    assert report.provenance_summary["artifact_count"] == 1
    assert report.provenance_summary["missing_selection_run_id_count"] == 1
    assert report.provenance_summary["extra_review_ranking_decision_key_count"] == 1
    assert report.provenance_summary["unknown_reviewer_id_count"] == 1
    assert any("source artifacts" in reason for reason in report.blocking_reasons)
    assert any("selection review run IDs" in reason for reason in report.blocking_reasons)
    assert any("review-ranking decision keys" in reason for reason in report.blocking_reasons)
    assert any("reviewer roster" in reason for reason in report.blocking_reasons)


def test_evidence_selection_expert_study_gate_blocks_duplicate_selection_run_ids() -> None:
    shared_run_id = uuid4()
    reviews = tuple(
        EvidenceSelectionReviewInput(
            run_id=shared_run_id,
            goal=goal,
            reviewer_id="reviewer-a",
            harness_selected_record_ids=(f"record-{index}",),
            human_selected_record_ids=(f"record-{index}",),
            explanation_quality_score=4,
            high_severity_overclaim_count=0,
        )
        for index, goal in enumerate(
            (
                "Find MED13 congenital heart disease evidence.",
                "Find EGFR inhibitor response evidence.",
                "Find NTRK fusion treatment evidence.",
            ),
        )
    )

    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="duplicate-selection-run-ids",
            study_evidence_kind="real_shadow_review",
            selection_reviews=reviews,
            review_ranking=_review_ranking_study("duplicate-selection-run-ids"),
            source_manifest=_source_manifest(selection_reviews=reviews),
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
    assert report.provenance_summary["duplicate_selection_run_id_count"] == 1
    assert any("Selection review run IDs must be unique" in reason for reason in report.blocking_reasons)


def test_evidence_selection_expert_study_gate_requires_source_export_artifacts() -> None:
    selection_reviews = _selection_reviews()
    manifest = _source_manifest_payload(selection_reviews=selection_reviews)
    manifest["source_artifacts"] = [
        {
            "artifact_id": f"adjudication-log-{index}",
            "artifact_kind": "adjudication_log",
            "uri": f"s3://artana-validation/adjudication-log-{index}.json",
            "sha256": f"{index}" * 64,
        }
        for index in range(1, 4)
    ]

    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput.model_validate(
            {
                "schema_version": "evidence_selection_expert_study.v1",
                "study_id": "missing-source-export-artifacts",
                "study_evidence_kind": "real_shadow_review",
                "selection_reviews": [
                    review.model_dump(mode="json")
                    for review in selection_reviews
                ],
                "review_ranking": _review_ranking_study(
                    "missing-source-export-artifacts",
                ).model_dump(mode="json"),
                "source_manifest": manifest,
            },
        ),
        thresholds=EvidenceSelectionExpertStudyGateThresholds(
            min_selection_review_count=3,
            min_distinct_selection_goals=3,
            min_selection_reviewer_count=1,
            min_mean_precision=0.8,
            min_mean_recall=0.8,
            min_mean_explanation_quality=3.0,
            min_source_artifact_count=3,
        ),
    )

    assert report.passed is False
    assert report.provenance_summary["source_artifact_kind_counts"] == {
        "adjudication_log": 3,
        "review_ranking_export": 0,
        "selection_review_export": 0,
    }
    assert any("selection_review_export" in reason for reason in report.blocking_reasons)
    assert any("review_ranking_export" in reason for reason in report.blocking_reasons)


def test_evidence_selection_expert_study_input_rejects_blank_source_identity() -> None:
    manifest = _source_manifest_payload()
    manifest["source_system"] = "   "
    manifest["export_id"] = "\t"
    manifest["exporter_id"] = " "
    manifest["redaction_statement"] = " "
    payload = {
        "schema_version": "evidence_selection_expert_study.v1",
        "study_id": "blank-source-identity",
        "study_evidence_kind": "real_shadow_review",
        "selection_reviews": [
            review.model_dump(mode="json")
            for review in _selection_reviews()
        ],
        "review_ranking": _review_ranking_study(
            "blank-source-identity",
        ).model_dump(mode="json"),
        "source_manifest": manifest,
    }

    with pytest.raises(ValidationError, match="source_system"):
        EvidenceSelectionExpertStudyInput.model_validate(payload)


@pytest.mark.parametrize(
    "field_name",
    ["source_system", "export_id", "exporter_id", "redaction_statement"],
)
def test_source_manifest_rejects_padded_identity_fields(field_name: str) -> None:
    manifest = _source_manifest_payload()
    manifest[field_name] = f" {manifest[field_name]} "

    with pytest.raises(ValidationError, match="leading or trailing whitespace"):
        EvidenceSelectionExpertStudySourceManifest.model_validate(manifest)


def test_evidence_selection_expert_study_input_rejects_invalid_source_hash() -> None:
    manifest = _source_manifest_payload()
    manifest["source_artifacts"][0]["sha256"] = "not-a-sha"

    payload = {
        "schema_version": "evidence_selection_expert_study.v1",
        "study_id": "invalid-source-hash",
        "study_evidence_kind": "real_shadow_review",
        "selection_reviews": [
            review.model_dump(mode="json")
            for review in _selection_reviews()
        ],
        "review_ranking": _review_ranking_study(
            "invalid-source-hash",
        ).model_dump(mode="json"),
        "source_manifest": manifest,
    }

    with pytest.raises(ValidationError, match="sha256"):
        EvidenceSelectionExpertStudyInput.model_validate(payload)


def test_source_manifest_rejects_padded_artifact_uri() -> None:
    manifest = _source_manifest_payload()
    source_artifacts = manifest["source_artifacts"]
    assert isinstance(source_artifacts, list)
    first_artifact = source_artifacts[0]
    assert isinstance(first_artifact, dict)
    first_artifact["uri"] = " s3://example/source.json "

    with pytest.raises(ValidationError, match="source artifact uri"):
        EvidenceSelectionExpertStudySourceManifest.model_validate(manifest)


def test_source_manifest_rejects_padded_reviewer_roster_entry() -> None:
    manifest = _source_manifest_payload()
    manifest["reviewer_roster"] = [" reviewer-a "]

    with pytest.raises(ValidationError, match="reviewer roster entries"):
        EvidenceSelectionExpertStudySourceManifest.model_validate(manifest)


@pytest.mark.parametrize(
    "exported_at",
    [
        "2026-07-07T07:00:00",
        "2026-07-07T07:00:00+00:00",
        "2026-07-07T08:00:00+01:00",
        "2026-07-07 07:00:00Z",
        "2026-07-07T07:00:00.123456Z",
    ],
)
def test_source_manifest_rejects_noncanonical_export_timestamps(
    exported_at: str,
) -> None:
    payload = _source_manifest_payload()
    payload["exported_at"] = exported_at

    with pytest.raises(ValidationError, match="UTC"):
        EvidenceSelectionExpertStudySourceManifest.model_validate(payload)


def test_evidence_selection_expert_study_gate_blocks_synthetic_studies() -> None:
    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="synthetic-shadow-study",
            study_evidence_kind="synthetic_fixture",
            selection_reviews=_selection_reviews(),
            review_ranking=_review_ranking_study("synthetic-shadow-study"),
            source_manifest=_source_manifest(),
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
            review_ranking=_review_ranking_study("partially-unlabeled-shadow-study"),
            source_manifest=_source_manifest(selection_reviews=tuple(reviews)),
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
            review_ranking=_review_ranking_study("unmeasurable-shadow-study"),
            source_manifest=_source_manifest(selection_reviews=tuple(reviews)),
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


def test_evidence_selection_expert_study_gate_blocks_missing_overclaim_labels() -> None:
    reviews = list(_selection_reviews())
    first_review = reviews[0]
    reviews[0] = EvidenceSelectionReviewInput(
        run_id=first_review.run_id,
        goal=first_review.goal,
        reviewer_id=first_review.reviewer_id,
        harness_selected_record_ids=first_review.harness_selected_record_ids,
        human_selected_record_ids=first_review.human_selected_record_ids,
        harness_skipped_record_ids=first_review.harness_skipped_record_ids,
        explanation_quality_score=first_review.explanation_quality_score,
    )

    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="missing-overclaim-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews=tuple(reviews),
            review_ranking=_review_ranking_study("missing-overclaim-study"),
        ),
    )

    assert report.passed is False
    assert report.selection_summary["missing_high_severity_overclaim_count"] == 1
    assert any("overclaim count" in reason for reason in report.blocking_reasons)


def test_evidence_selection_expert_study_gate_blocks_duplicate_run_ids() -> None:
    reviews = list(_selection_reviews())
    reviews[1] = reviews[1].model_copy(update={"run_id": reviews[0].run_id})

    report = evaluate_evidence_selection_expert_study_gate(
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="duplicate-runs-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews=tuple(reviews),
            review_ranking=_review_ranking_study("duplicate-runs-study"),
        ),
    )

    assert report.passed is False
    assert report.selection_summary["duplicate_run_id_count"] == 1
    assert any("run IDs must be unique" in reason for reason in report.blocking_reasons)


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
                study_id="weak-shadow-study",
                decisions=_review_ranking_decisions()[:2],
                adjudication_note=None,
            ),
            source_manifest=_source_manifest(
                selection_reviews=weak_reviews,
                review_ranking_decisions=_review_ranking_decisions()[:2],
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


def test_evidence_selection_expert_study_input_binds_ranking_study_id() -> None:
    with pytest.raises(ValidationError, match="review_ranking study_id must match"):
        EvidenceSelectionExpertStudyInput(
            schema_version="evidence_selection_expert_study.v1",
            study_id="selection-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews=_selection_reviews(),
            review_ranking=_review_ranking_study("different-ranking-study"),
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


def _review_ranking_study(study_id: str) -> ReviewRankingCalibrationStudyInput:
    return ReviewRankingCalibrationStudyInput(
        schema_version="evidence_selection_review_ranking_calibration.v1",
        study_id=study_id,
        decisions=_review_ranking_decisions(),
        adjudication_note="No reviewer disagreements in this calibration sample.",
    )


def _source_manifest(
    *,
    selection_reviews: tuple[EvidenceSelectionReviewInput, ...] | None = None,
    review_ranking_decisions: tuple[ReviewRankingCalibrationDecision, ...] | None = None,
) -> object:
    return _source_manifest_payload(
        selection_reviews=selection_reviews,
        review_ranking_decisions=review_ranking_decisions,
    )


def _source_manifest_payload(
    *,
    selection_reviews: tuple[EvidenceSelectionReviewInput, ...] | None = None,
    review_ranking_decisions: tuple[ReviewRankingCalibrationDecision, ...] | None = None,
) -> dict[str, object]:
    active_selection_reviews = selection_reviews or _selection_reviews()
    active_ranking_decisions = review_ranking_decisions or _review_ranking_decisions()
    return {
        "source_system": "artana-shadow-review",
        "export_id": "shadow-export-2026-07-07",
        "exported_at": "2026-07-07T07:00:00Z",
        "exporter_id": "review-ops-a",
        "redaction_statement": "No PHI or raw patient text included.",
        "source_artifacts": [
            {
                "artifact_id": "selection-review-export",
                "artifact_kind": "selection_review_export",
                "uri": "s3://artana-validation/selection-review-export.json",
                "sha256": "a" * 64,
            },
            {
                "artifact_id": "review-ranking-export",
                "artifact_kind": "review_ranking_export",
                "uri": "s3://artana-validation/review-ranking-export.json",
                "sha256": "b" * 64,
            },
            {
                "artifact_id": "adjudication-log",
                "artifact_kind": "adjudication_log",
                "uri": "s3://artana-validation/adjudication-log.json",
                "sha256": "c" * 64,
            },
        ],
        "selection_review_run_ids": [
            str(review.run_id) for review in active_selection_reviews
        ],
        "review_ranking_decision_keys": [
            f"{decision.source_kind}:{decision.item_id}"
            for decision in active_ranking_decisions
        ],
        "reviewer_roster": ["reviewer-a"],
    }


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
