"""Tests for the review-ranking calibration gate runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_evidence_selection_review_calibration_gate import (
    build_review_ranking_calibration_gate_report,
    main,
    render_review_ranking_calibration_gate_markdown,
)


def test_review_ranking_calibration_gate_runner_blocks_seed_as_production_proof() -> None:
    report = build_review_ranking_calibration_gate_report(
        input_path=Path(
            "scripts/validation/evidence_selection/fixtures/"
            "review_ranking_shadow_seed_v1.json",
        ),
        min_sample_count=10,
        max_expected_calibration_error=0.15,
    )
    markdown = render_review_ranking_calibration_gate_markdown(report)

    assert report["gate"]["passed"] is False
    assert report["gate"]["status"] == "failed"
    assert report["gate"]["calibration"]["sample_count"] == 10
    assert report["gate"]["calibration"]["expected_calibration_error"] <= 0.15
    assert report["gate"]["study_design"]["distinct_goal_count"] == 1
    assert report["gate"]["study_design"]["distinct_evidence_shape_count"] == 1
    assert report["gate"]["study_design"]["missing_reviewer_id_count"] == 0
    assert any(
        "distinct research goals" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )
    assert any(
        "distinct evidence shapes" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )
    assert "Review-ranking calibration gate: **FAILED**" in markdown
    assert "review_ranking_shadow_seed_v1" in markdown


def test_review_ranking_calibration_gate_runner_can_render_seed_mechanics() -> None:
    report = build_review_ranking_calibration_gate_report(
        input_path=Path(
            "scripts/validation/evidence_selection/fixtures/"
            "review_ranking_shadow_seed_v1.json",
        ),
        min_sample_count=10,
        max_expected_calibration_error=0.15,
        min_distinct_goals=1,
        min_distinct_evidence_shapes=1,
    )
    markdown = render_review_ranking_calibration_gate_markdown(report)

    assert report["gate"]["passed"] is True
    assert report["gate"]["status"] == "passed"
    assert report["gate"]["blocking_reasons"] == []
    assert "Review-ranking calibration gate: **PASSED**" in markdown


def test_review_ranking_calibration_gate_runner_uses_strict_production_default() -> None:
    report = build_review_ranking_calibration_gate_report(
        input_path=Path(
            "scripts/validation/evidence_selection/fixtures/"
            "review_ranking_shadow_seed_v1.json",
        ),
    )

    assert report["gate"]["passed"] is False
    assert any(
        "ECE is above target" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )


def test_review_ranking_calibration_gate_runner_fails_closed_for_small_studies(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "small-study.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v1",
                "study_id": "small-study",
                "adjudication_note": "No disagreements in this seed study.",
                "decisions": [
                    {
                        "source_kind": "proposal",
                        "item_id": "proposal-1",
                        "ranking_score": 0.9,
                        "outcome": "positive",
                        "goal": "Find MED13 evidence.",
                        "reviewer_id": "reviewer-a",
                        "evidence_shape": "variant_relation",
                    },
                ],
            },
        )
        + "\n",
    )

    report = build_review_ranking_calibration_gate_report(
        input_path=input_path,
        min_sample_count=10,
        max_expected_calibration_error=0.15,
    )
    markdown = render_review_ranking_calibration_gate_markdown(report)

    assert report["gate"]["passed"] is False
    assert any(
        "At least 10" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )
    assert "Review-ranking calibration gate: **FAILED**" in markdown


def test_review_ranking_calibration_gate_runner_accepts_integer_json_scores(
    tmp_path: Path,
) -> None:
    decisions = _passing_diverse_decisions()
    for index, decision in enumerate(decisions):
        decision["ranking_score"] = 1 if index < 2 else 0
    input_path = tmp_path / "integer-scores.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v1",
                "study_id": "integer-scores",
                "adjudication_note": "No disagreements in this study.",
                "decisions": decisions,
            },
        )
        + "\n",
    )

    report = build_review_ranking_calibration_gate_report(
        input_path=input_path,
        min_sample_count=4,
        max_expected_calibration_error=0.15,
    )

    assert report["gate"]["passed"] is True
    assert report["gate"]["calibration"]["mean_score"] == 0.5


def test_review_ranking_calibration_gate_cli_returns_nonzero_by_default_when_failed(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "small-study.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v1",
                "study_id": "small-study",
                "adjudication_note": "No disagreements in this seed study.",
                "decisions": [
                    {
                        "source_kind": "proposal",
                        "item_id": "proposal-1",
                        "ranking_score": 0.9,
                        "outcome": "positive",
                        "goal": "Find MED13 evidence.",
                        "reviewer_id": "reviewer-a",
                        "evidence_shape": "variant_relation",
                    },
                ],
            },
        )
        + "\n",
    )

    exit_code = main(
        (
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
        ),
    )

    assert exit_code == 1


def test_review_ranking_calibration_gate_runner_rejects_schema_drift(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "wrong-schema.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "wrong.v0",
                "study_id": "wrong-schema",
                "decisions": _passing_decisions(),
            },
        )
        + "\n",
    )

    with pytest.raises(ValueError, match="schema_version"):
        build_review_ranking_calibration_gate_report(
            input_path=input_path,
            max_expected_calibration_error=0.15,
        )


def test_review_ranking_calibration_gate_runner_rejects_missing_schema(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "missing-schema.json"
    input_path.write_text(
        json.dumps(
            {
                "study_id": "missing-schema",
                "decisions": _passing_decisions(),
            },
        )
        + "\n",
    )

    with pytest.raises(ValueError, match="schema_version"):
        build_review_ranking_calibration_gate_report(
            input_path=input_path,
            max_expected_calibration_error=0.15,
        )


def test_review_ranking_calibration_gate_runner_rejects_extra_study_fields(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "extra-field.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v1",
                "study_id": "extra-field",
                "unexpected": "ignored would be unsafe",
                "decisions": _passing_decisions(),
            },
        )
        + "\n",
    )

    with pytest.raises(ValueError, match="unexpected"):
        build_review_ranking_calibration_gate_report(
            input_path=input_path,
            max_expected_calibration_error=0.15,
        )


def test_review_ranking_calibration_gate_runner_blocks_undercovered_study_design(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "undercovered-study.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v1",
                "study_id": "undercovered-study",
                "adjudication_note": "No disagreements in this seed study.",
                "decisions": [
                    {
                        **decision,
                        "goal": "Find MED13 evidence.",
                        "reviewer_id": "reviewer-a",
                        "evidence_shape": "variant_relation",
                    }
                    for decision in _passing_decisions()
                ],
            },
        )
        + "\n",
    )

    report = build_review_ranking_calibration_gate_report(
        input_path=input_path,
        min_sample_count=4,
        max_expected_calibration_error=0.15,
    )
    markdown = render_review_ranking_calibration_gate_markdown(report)

    assert report["gate"]["passed"] is False
    assert any(
        "distinct research goals" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )
    assert any(
        "distinct evidence shapes" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )
    assert "## Study Design" in markdown
    assert "Review-ranking calibration gate: **FAILED**" in markdown


def test_review_ranking_calibration_gate_runner_blocks_missing_adjudication_note(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "missing-adjudication.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v1",
                "study_id": "missing-adjudication",
                "decisions": _passing_diverse_decisions(),
            },
        )
        + "\n",
    )

    report = build_review_ranking_calibration_gate_report(
        input_path=input_path,
        min_sample_count=4,
        max_expected_calibration_error=0.15,
    )

    assert report["gate"]["passed"] is False
    assert report["gate"]["study_design"]["adjudication_note_present"] is False
    assert any(
        "adjudication note" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )


def test_review_ranking_calibration_gate_runner_blocks_blank_adjudication_note(
    tmp_path: Path,
) -> None:
    decisions = _passing_diverse_decisions()
    decisions[0]["reviewer_id"] = ""
    decisions[0]["goal"] = ""
    decisions[0]["evidence_shape"] = ""
    input_path = tmp_path / "blank-adjudication.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v1",
                "study_id": "blank-adjudication",
                "adjudication_note": "",
                "decisions": decisions,
            },
        )
        + "\n",
    )

    report = build_review_ranking_calibration_gate_report(
        input_path=input_path,
        min_sample_count=4,
        max_expected_calibration_error=0.15,
    )

    assert report["gate"]["passed"] is False
    assert report["gate"]["study_design"]["adjudication_note_present"] is False
    assert report["gate"]["study_design"]["missing_reviewer_id_count"] == 1
    assert report["gate"]["study_design"]["missing_goal_count"] == 1
    assert report["gate"]["study_design"]["missing_evidence_shape_count"] == 1
    assert any(
        "adjudication note" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )


def _passing_decisions() -> list[dict[str, object]]:
    return [
        {
            "source_kind": "proposal",
            "item_id": "proposal-1",
            "ranking_score": 0.95,
            "outcome": "positive",
        },
        {
            "source_kind": "review_item",
            "item_id": "review-item-1",
            "ranking_score": 0.9,
            "outcome": "positive",
        },
        {
            "source_kind": "proposal",
            "item_id": "proposal-2",
            "ranking_score": 0.05,
            "outcome": "negative",
        },
        {
            "source_kind": "review_item",
            "item_id": "review-item-2",
            "ranking_score": 0.1,
            "outcome": "negative",
        },
    ]


def _passing_diverse_decisions() -> list[dict[str, object]]:
    base_decisions = _passing_decisions()
    goals = (
        "Find MED13 congenital heart disease evidence.",
        "Find EGFR inhibitor response evidence.",
        "Find NTRK fusion treatment evidence.",
        "Find MED13 congenital heart disease evidence.",
    )
    shapes = (
        "variant_relation",
        "drug_response",
        "fusion_treatment",
        "variant_relation",
    )
    return [
        {
            **decision,
            "goal": goals[index],
            "reviewer_id": "reviewer-a",
            "evidence_shape": shapes[index],
        }
        for index, decision in enumerate(base_decisions)
    ]
