"""Tests for the evidence-selection expert/shadow study gate runner."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_evidence_selection_expert_study_gate import (
    EvidenceSelectionExpertStudyRunnerThresholds,
    build_evidence_selection_expert_study_gate_report,
    main,
    render_evidence_selection_expert_study_gate_markdown,
)


def test_evidence_selection_expert_study_gate_runner_passes_balanced_study(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "balanced-study.json"
    input_path.write_text(json.dumps(_balanced_study_payload()) + "\n")

    report = build_evidence_selection_expert_study_gate_report(
        input_path=input_path,
        thresholds=EvidenceSelectionExpertStudyRunnerThresholds(
            min_review_ranking_sample_count=10,
            max_expected_calibration_error=0.05,
        ),
    )
    markdown = render_evidence_selection_expert_study_gate_markdown(report)

    assert report["gate"]["passed"] is True
    assert report["gate"]["status"] == "passed"
    assert report["gate"]["selection_summary"]["review_count"] == 3
    assert report["gate"]["selection_summary"]["distinct_goal_count"] == 3
    assert report["gate"]["selection_summary"]["mean_precision"] == 1.0
    assert report["gate"]["selection_summary"]["mean_recall"] == 1.0
    assert report["gate"]["selection_reports"][0]["reviewer_id"] == "reviewer-a"
    assert report["gate"]["selection_reports"][0]["precision"] == 1.0
    assert report["gate"]["review_ranking_gate"]["passed"] is True
    assert report["gate"]["blocking_reasons"] == []
    assert "Evidence-selection expert study gate: **PASSED**" in markdown
    assert "## Selection Review" in markdown
    assert "## Review-Ranking Calibration" in markdown


def test_evidence_selection_expert_study_gate_accepts_documented_note_objects(
    tmp_path: Path,
) -> None:
    payload = _balanced_study_payload()
    first_review = payload["selection_reviews"][0]
    first_review["false_positive_notes"] = {}
    first_review["false_negative_notes"] = {
        "record-missed": "Reviewer expected this record."
    }
    input_path = tmp_path / "documented-notes-study.json"
    input_path.write_text(json.dumps(payload) + "\n")

    report = build_evidence_selection_expert_study_gate_report(input_path=input_path)

    first_report = report["gate"]["selection_reports"][0]
    assert first_report["false_positive_notes"] == {}
    assert first_report["false_negative_notes"] == {
        "record-missed": "Reviewer expected this record."
    }


def test_evidence_selection_expert_study_gate_runner_fails_closed(
    tmp_path: Path,
) -> None:
    payload = _balanced_study_payload()
    payload["selection_reviews"] = payload["selection_reviews"][:1]
    first_review = payload["selection_reviews"][0]
    first_review["reviewer_id"] = ""
    first_review["harness_selected_record_ids"] = ["record-fp"]
    first_review["human_selected_record_ids"] = ["record-tp"]
    first_review["explanation_quality_score"] = 2
    first_review["high_severity_overclaim_count"] = 1
    payload["review_ranking"]["decisions"] = payload["review_ranking"]["decisions"][:2]
    payload["review_ranking"].pop("adjudication_note")
    input_path = tmp_path / "weak-study.json"
    input_path.write_text(json.dumps(payload) + "\n")

    report = build_evidence_selection_expert_study_gate_report(
        input_path=input_path,
        thresholds=EvidenceSelectionExpertStudyRunnerThresholds(
            min_review_ranking_sample_count=10,
            max_expected_calibration_error=0.05,
        ),
    )
    markdown = render_evidence_selection_expert_study_gate_markdown(report)

    assert report["gate"]["passed"] is False
    assert report["gate"]["status"] == "failed"
    assert any(
        "selection review runs" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )
    assert any(
        "Review-ranking gate failed" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )
    assert "Evidence-selection expert study gate: **FAILED**" in markdown


def test_evidence_selection_expert_study_gate_runner_blocks_synthetic_fixture(
    tmp_path: Path,
) -> None:
    payload = _balanced_study_payload()
    payload["study_evidence_kind"] = "synthetic_fixture"
    input_path = tmp_path / "synthetic-study.json"
    input_path.write_text(json.dumps(payload) + "\n")

    report = build_evidence_selection_expert_study_gate_report(input_path=input_path)

    assert report["gate"]["passed"] is False
    assert any(
        "real shadow-review evidence" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )


def test_evidence_selection_expert_study_gate_cli_returns_nonzero_when_failed(
    tmp_path: Path,
) -> None:
    payload = _balanced_study_payload()
    payload["selection_reviews"] = []
    input_path = tmp_path / "empty-study.json"
    input_path.write_text(json.dumps(payload) + "\n")

    exit_code = main(
        (
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
        ),
    )

    assert exit_code == 1
    assert (tmp_path / "out" / "evidence_selection_expert_study_gate.json").exists()
    assert (tmp_path / "out" / "evidence_selection_expert_study_gate.md").exists()


def _balanced_study_payload() -> dict[str, object]:
    goals = [
        "Find MED13 congenital heart disease evidence.",
        "Find EGFR inhibitor response evidence.",
        "Find NTRK fusion treatment evidence.",
    ]
    return {
        "schema_version": "evidence_selection_expert_study.v1",
        "study_id": "balanced-shadow-study",
        "study_evidence_kind": "real_shadow_review",
        "description": "Multi-goal expert shadow-review study fixture.",
        "selection_reviews": [
            {
                "run_id": f"00000000-0000-0000-0000-00000000000{index}",
                "goal": goal,
                "reviewer_id": "reviewer-a",
                "harness_selected_record_ids": [
                    f"record-{index}-a",
                    f"record-{index}-b",
                ],
                "human_selected_record_ids": [
                    f"record-{index}-a",
                    f"record-{index}-b",
                ],
                "harness_skipped_record_ids": [f"record-{index}-c"],
                "explanation_quality_score": 4,
                "high_severity_overclaim_count": 0,
            }
            for index, goal in enumerate(goals)
        ],
        "review_ranking": {
            "schema_version": "evidence_selection_review_ranking_calibration.v1",
            "study_id": "balanced-shadow-study",
            "adjudication_note": (
                "No reviewer disagreements in this calibration sample."
            ),
            "decisions": _ranking_decisions(goals),
        },
    }


def _ranking_decisions(goals: list[str]) -> list[dict[str, object]]:
    evidence_shapes = [
        "variant_disease_relation",
        "drug_response_relation",
        "fusion_treatment_relation",
    ]
    positive_decisions = [
        {
            "source_kind": "proposal" if index % 2 == 0 else "review_item",
            "item_id": f"positive-{index}",
            "ranking_score": 1.0,
            "outcome": "positive",
            "reviewer_id": "reviewer-a",
            "goal": goals[index % len(goals)],
            "evidence_shape": evidence_shapes[index % len(evidence_shapes)],
        }
        for index in range(5)
    ]
    negative_decisions = [
        {
            "source_kind": "proposal" if index % 2 == 0 else "review_item",
            "item_id": f"negative-{index}",
            "ranking_score": 0.0,
            "outcome": "negative",
            "reviewer_id": "reviewer-a",
            "goal": goals[index % len(goals)],
            "evidence_shape": evidence_shapes[index % len(evidence_shapes)],
        }
        for index in range(5)
    ]
    return positive_decisions + negative_decisions
