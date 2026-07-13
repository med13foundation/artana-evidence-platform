"""Tests for the review-ranking calibration gate runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.ranking.contracts import (
    ReviewRankingCalibrationProtocol,
)
from artana_evidence_api.evidence_selection.ranking.protocol_integrity import (
    authenticate_calibration_protocol,
)

from scripts.run_evidence_selection_review_calibration_gate import (
    build_review_ranking_calibration_gate_report,
    main,
    render_review_ranking_calibration_gate_markdown,
)


@pytest.fixture(autouse=True)
def _calibration_protocol_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY",
        "review-calibration-runner-test-key-at-least-32-bytes",
    )


def test_review_ranking_calibration_gate_runner_blocks_seed_as_production_proof() -> None:
    report = build_review_ranking_calibration_gate_report(
        input_path=Path(
            "scripts/validation/evidence_selection/fixtures/"
            "review_ranking_shadow_seed_v2.json",
        ),
        min_sample_count=10,
        max_expected_calibration_error=0.15,
    )
    markdown = render_review_ranking_calibration_gate_markdown(report)

    assert report["gate"]["passed"] is False
    assert report["gate"]["status"] == "failed"
    assert report["gate"]["calibration"]["sample_count"] == 4
    assert report["gate"]["calibration"]["availability"] == "unavailable"
    assert report["gate"]["calibration"]["expected_calibration_error"] is None
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
    assert "review_ranking_shadow_seed_v2" in markdown


def test_review_ranking_calibration_gate_seed_cannot_pass_relaxed_quality() -> None:
    report = build_review_ranking_calibration_gate_report(
        input_path=Path(
            "scripts/validation/evidence_selection/fixtures/"
            "review_ranking_shadow_seed_v2.json",
        ),
        min_sample_count=4,
        max_expected_calibration_error=0.15,
        min_distinct_goals=1,
        min_distinct_evidence_shapes=1,
    )
    markdown = render_review_ranking_calibration_gate_markdown(report)

    assert report["gate"]["passed"] is False
    assert report["gate"]["calibration"]["availability"] == "unavailable"
    assert any(
        "Complete candidate calibrated probabilities are required" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )
    assert "Review-ranking calibration gate: **FAILED**" in markdown


def test_review_ranking_calibration_gate_runner_uses_strict_production_default() -> None:
    report = build_review_ranking_calibration_gate_report(
        input_path=Path(
            "scripts/validation/evidence_selection/fixtures/"
            "review_ranking_shadow_seed_v2.json",
        ),
    )

    assert report["gate"]["passed"] is False
    assert any(
        "Complete candidate calibrated probabilities are required" in reason
        for reason in report["gate"]["blocking_reasons"]
        if isinstance(reason, str)
    )


def test_review_ranking_calibration_gate_accepts_validated_held_out_study(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "validated-held-out-study.json"
    input_path.write_text(json.dumps(_validated_study_payload()) + "\n")

    report = build_review_ranking_calibration_gate_report(
        input_path=input_path,
        min_sample_count=8,
        max_expected_calibration_error=0.05,
    )

    assert report["gate"]["passed"] is True
    assert report["gate"]["calibration"]["availability"] == "diagnostic"
    assert report["gate"]["calibration"]["expected_calibration_error"] == 0.0
    assert report["gate"]["blocking_reasons"] == []


def test_review_ranking_calibration_gate_runner_fails_closed_for_small_studies(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "small-study.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v2",
                "study_id": "small-study",
                "adjudication_note": "No disagreements in this seed study.",
                "decisions": [
                    {
                        "source_kind": "proposal",
                        "item_id": "proposal-1",
                        "research_question_id": "small-study-question",
                        "operational_ranking": _operational_ranking(6.0),
                        "calibrated_probability": None,
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


def test_review_ranking_calibration_gate_integer_weights_are_not_probabilities(
    tmp_path: Path,
) -> None:
    decisions = _passing_diverse_decisions()
    for index, decision in enumerate(decisions):
        decision["operational_ranking"]["value"] = 1 if index < 2 else 0
    input_path = tmp_path / "integer-scores.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v2",
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

    assert report["gate"]["passed"] is False
    assert report["gate"]["calibration"]["availability"] == "unavailable"
    assert report["gate"]["calibration"]["mean_probability"] is None


def test_review_ranking_calibration_gate_cli_returns_nonzero_by_default_when_failed(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "small-study.json"
    input_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_review_ranking_calibration.v2",
                "study_id": "small-study",
                "adjudication_note": "No disagreements in this seed study.",
                "decisions": [
                    {
                        "source_kind": "proposal",
                        "item_id": "proposal-1",
                        "research_question_id": "small-study-question",
                        "operational_ranking": _operational_ranking(6.0),
                        "calibrated_probability": None,
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
                "schema_version": "evidence_selection_review_ranking_calibration.v2",
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
                "schema_version": "evidence_selection_review_ranking_calibration.v2",
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
                "schema_version": "evidence_selection_review_ranking_calibration.v2",
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
                "schema_version": "evidence_selection_review_ranking_calibration.v2",
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
            "research_question_id": "heldout-rq-01",
            "operational_ranking": _operational_ranking(6.0),
            "calibrated_probability": None,
            "outcome": "positive",
        },
        {
            "source_kind": "review_item",
            "item_id": "review-item-1",
            "research_question_id": "heldout-rq-02",
            "operational_ranking": _operational_ranking(6.0),
            "calibrated_probability": None,
            "outcome": "positive",
        },
        {
            "source_kind": "proposal",
            "item_id": "proposal-2",
            "research_question_id": "heldout-rq-03",
            "operational_ranking": _operational_ranking(0.0),
            "calibrated_probability": None,
            "outcome": "negative",
        },
        {
            "source_kind": "review_item",
            "item_id": "review-item-2",
            "research_question_id": "heldout-rq-04",
            "operational_ranking": _operational_ranking(0.0),
            "calibrated_probability": None,
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


def _validated_study_payload() -> dict[str, object]:
    goals = (
        "Find MED13 congenital heart disease evidence.",
        "Find EGFR inhibitor response evidence.",
        "Find NTRK fusion treatment evidence.",
    )
    shapes = ("variant_relation", "drug_response", "fusion_treatment")
    decisions: list[dict[str, object]] = []
    for index in range(8):
        positive = index % 4 in (0, 3)
        value = 6.0 if positive else 0.0
        decisions.append(
            {
                "source_kind": "proposal" if index % 2 == 0 else "review_item",
                "item_id": f"validated-{index}",
                "research_question_id": f"heldout-rq-{index + 1:02d}",
                "operational_ranking": _operational_ranking(value),
                "calibrated_probability": _calibrated_probability(
                    1.0 if positive else 0.0,
                ),
                "outcome": "positive" if positive else "negative",
                "reviewer_id": "expert-reviewer-a",
                "goal": goals[index % len(goals)],
                "evidence_shape": shapes[index % len(shapes)],
            },
        )
    return {
        "schema_version": "evidence_selection_review_ranking_calibration.v2",
        "study_id": "validated-held-out-study",
        "adjudication_note": "Independent expert labels were adjudicated.",
        "decisions": decisions,
        "calibration_protocol": _calibration_protocol(),
    }


def _operational_ranking(value: float) -> dict[str, object]:
    return {
        "origin": "deterministic_policy",
        "value": value,
        "policy_id": "test_agent_semantic_ranking",
        "policy_version": "v1",
        "mapping_version": "v1",
        "categorical_inputs": [
            {"field": "objective_match", "value": "direct"},
        ],
        "caps": [],
        "vetoes": [],
        "blocking_categories": [],
    }


def _calibration_identity() -> dict[str, object]:
    return {
        "input_policy_id": "test_agent_semantic_ranking",
        "input_policy_version": "v1",
        "input_mapping_version": "v1",
        "categorical_schema_version": "v1",
        "selector_model_id": "test-selector-model",
        "selector_prompt_version": "v1",
        "objective_schema_version": "v1",
        "corpus_version": "v1",
        "calibration_algorithm": "isotonic",
        "calibration_version": "v1",
    }


def _calibrated_probability(value: float) -> dict[str, object]:
    return {
        "origin": "calibration_model",
        "value": value,
        "calibration_status": "diagnostic",
        "identity": _calibration_identity(),
        "training_set_sha256": "1" * 64,
        "partition_manifest_sha256": "2" * 64,
        "held_out_protocol": "frozen_question_partition_v1",
    }


def _calibration_protocol() -> dict[str, object]:
    payload = {
        "identity": _calibration_identity(),
        "partition_manifest_sha256": "2" * 64,
        "training_set_sha256": "1" * 64,
        "held_out_set_sha256": "3" * 64,
        "training_research_question_ids": [
            f"training-rq-{index:02d}" for index in range(1, 13)
        ],
        "held_out_research_question_ids": [
            f"heldout-rq-{index:02d}" for index in range(1, 9)
        ],
        "independent_expert_labels": True,
        "held_out_protocol": "frozen_question_partition_v1",
    }
    protocol = ReviewRankingCalibrationProtocol.model_validate(payload)
    return authenticate_calibration_protocol(protocol).model_dump(mode="json")
