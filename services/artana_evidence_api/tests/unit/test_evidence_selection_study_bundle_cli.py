"""Tests for the expert-study bundle builder CLI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_evidence_selection_expert_study_bundle import main
from scripts.run_evidence_selection_expert_study_gate import (
    EvidenceSelectionExpertStudyRunnerThresholds,
    build_evidence_selection_expert_study_gate_report,
)

from .evidence_selection_review_fixtures import adequate_explanation_assessment


def test_expert_study_bundle_builder_cli_writes_gate_compatible_bundle(
    tmp_path: Path,
) -> None:
    selection_path, ranking_path, _adjudication_path = _write_source_exports(tmp_path)
    output_path = tmp_path / "expert-study-bundle.json"

    exit_code = main(
        _base_args(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=output_path,
        ),
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text())
    assert payload["schema_version"] == "evidence_selection_expert_study.v2"
    assert payload["study_evidence_kind"] == "synthetic_fixture"
    assert payload["source_manifest"]["source_artifacts"] == [
        {
            "artifact_id": "selection-review-export",
            "artifact_kind": "selection_review_export",
            "uri": str(selection_path),
            "sha256": _sha256(selection_path),
        },
        {
            "artifact_id": "review-ranking-export",
            "artifact_kind": "review_ranking_export",
            "uri": str(ranking_path),
            "sha256": _sha256(ranking_path),
        },
    ]
    assert payload["source_manifest"]["selection_review_run_ids"] == [
        review["run_id"] for review in _selection_reviews()
    ]
    assert payload["source_manifest"]["review_ranking_decision_keys"] == [
        f"{decision['source_kind']}:{decision['item_id']}"
        for decision in _review_ranking()["decisions"]
    ]

    gate_report = build_evidence_selection_expert_study_gate_report(
        input_path=output_path,
        thresholds=EvidenceSelectionExpertStudyRunnerThresholds(
            min_source_artifact_count=2,
            min_review_ranking_sample_count=10,
            max_expected_calibration_error=0.05,
        ),
    )

    assert gate_report["gate"]["passed"] is False
    assert any(
        "real shadow-review evidence" in reason
        for reason in gate_report["gate"]["blocking_reasons"]
    )


def test_cli_derives_manifest_identity_from_source_exports(
    tmp_path: Path,
) -> None:
    selection_path, ranking_path, _adjudication_path = _write_source_exports(tmp_path)
    output_path = tmp_path / "expert-study-bundle.json"

    exit_code = main(
        _base_args_without_source_identity(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=output_path,
        ),
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text())
    assert payload["source_manifest"]["source_system"] == "artana-shadow-review"
    assert payload["source_manifest"]["export_id"] == "shadow-export-2026-07-07"
    assert payload["source_manifest"]["exported_at"] == "2026-07-07T07:00:00Z"
    assert payload["source_manifest"]["exporter_id"] == "review-ops-a"
    assert (
        payload["source_manifest"]["redaction_statement"]
        == "No PHI or raw patient text included."
    )


@pytest.mark.parametrize(
    "collision_source",
    ["selection", "ranking", "adjudication"],
)
def test_cli_rejects_output_that_overwrites_source_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    collision_source: str,
) -> None:
    selection_path, ranking_path, adjudication_path = _write_source_exports(
        tmp_path,
        include_adjudication=True,
    )
    source_paths = {
        "selection": selection_path,
        "ranking": ranking_path,
        "adjudication": adjudication_path,
    }
    original_text = source_paths[collision_source].read_text()

    exit_code = main(
        _base_args(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=source_paths[collision_source],
            adjudication_path=adjudication_path,
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Output path must not overwrite source artifact" in captured.err
    assert source_paths[collision_source].read_text() == original_text


def test_cli_rejects_missing_source_with_concise_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _selection_path, ranking_path, _adjudication_path = _write_source_exports(tmp_path)

    exit_code = main(
        _base_args(
            selection_path=tmp_path / "missing-selection.json",
            ranking_path=ranking_path,
            output_path=tmp_path / "bundle.json",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unable to read source artifact" in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_malformed_json_with_concise_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selection_path, ranking_path, _adjudication_path = _write_source_exports(tmp_path)
    selection_path.write_text("{not-json")

    exit_code = main(
        _base_args(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=tmp_path / "bundle.json",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "is not valid JSON" in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_unwritable_output_with_concise_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selection_path, ranking_path, _adjudication_path = _write_source_exports(tmp_path)
    output_path = tmp_path / "output-directory"
    output_path.mkdir()

    exit_code = main(
        _base_args(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=output_path,
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unable to write expert-study bundle" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("exported_at", "expected_error"),
    [
        ("not-a-date", "--exported-at must be valid ISO-8601"),
        ("2026-07-07T07:00:00", "--exported-at must include a timezone"),
    ],
)
def test_cli_rejects_invalid_export_timestamps(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    exported_at: str,
    expected_error: str,
) -> None:
    selection_path, ranking_path, _adjudication_path = _write_source_exports(tmp_path)

    exit_code = main(
        _base_args(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=tmp_path / "bundle.json",
            exported_at=exported_at,
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert expected_error in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("export_kind", ["selection", "ranking"])
def test_cli_rejects_source_export_without_timezone(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    export_kind: str,
) -> None:
    selection_export = _selection_review_export()
    ranking_export = _review_ranking_export()
    if export_kind == "selection":
        selection_export["exported_at"] = "2026-07-07T07:00:00"
    else:
        ranking_export["exported_at"] = "2026-07-07T07:00:00"
    selection_path, ranking_path, _adjudication_path = _write_source_exports(
        tmp_path,
        selection_export=selection_export,
        ranking_export=ranking_export,
    )

    exit_code = main(
        _base_args_without_source_identity(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=tmp_path / "bundle.json",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "validation failed for fields: exported_at" in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_noncanonical_source_export_timestamp_offset(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ranking_export = _review_ranking_export()
    ranking_export["exported_at"] = "2026-07-07T08:00:00+01:00"
    selection_path, ranking_path, _adjudication_path = _write_source_exports(
        tmp_path,
        ranking_export=ranking_export,
    )

    exit_code = main(
        _base_args_without_source_identity(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=tmp_path / "bundle.json",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "validation failed for fields: exported_at" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "alternate_exported_at",
    [
        "2026-07-07T07:00:00.000Z",
        "2026-07-07T07:00:00+00:00",
        "2026-07-07 07:00:00Z",
        "2026-07-07T07:00Z",
    ],
)
def test_cli_rejects_alternate_utc_source_export_timestamp_spellings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    alternate_exported_at: str,
) -> None:
    ranking_export = _review_ranking_export()
    ranking_export["exported_at"] = alternate_exported_at
    selection_path, ranking_path, _adjudication_path = _write_source_exports(
        tmp_path,
        ranking_export=ranking_export,
    )

    exit_code = main(
        _base_args_without_source_identity(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=tmp_path / "bundle.json",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "validation failed for fields: exported_at" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "identity_field",
    ["source_system", "export_id", "exporter_id", "redaction_statement"],
)
def test_cli_rejects_source_export_identity_field_with_outer_whitespace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    identity_field: str,
) -> None:
    selection_export = _selection_review_export()
    selection_export[identity_field] = f" {selection_export[identity_field]} "
    selection_path, ranking_path, _adjudication_path = _write_source_exports(
        tmp_path,
        selection_export=selection_export,
    )

    exit_code = main(
        _base_args_without_source_identity(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=tmp_path / "bundle.json",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"validation failed for fields: {identity_field}" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("override_field", "override_value"),
    [
        ("source_system", "other-system"),
        ("export_id", "other-export"),
        ("exported_at", "2026-07-07T08:00:00Z"),
        ("exporter_id", "other-exporter"),
        ("redaction_statement", "Different redaction statement."),
    ],
)
def test_cli_rejects_source_identity_override_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    override_field: str,
    override_value: str,
) -> None:
    selection_path, ranking_path, _adjudication_path = _write_source_exports(tmp_path)

    exit_code = main(
        _base_args(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=tmp_path / "bundle.json",
            **{override_field: override_value},
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "source export identity" in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_noncanonical_source_identity_override_timestamp(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selection_path, ranking_path, _adjudication_path = _write_source_exports(tmp_path)

    exit_code = main(
        _base_args(
            selection_path=selection_path,
            ranking_path=ranking_path,
            output_path=tmp_path / "bundle.json",
            exported_at="2026-07-07T08:00:00+01:00",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "canonical UTC" in captured.err
    assert "Traceback" not in captured.err


def _base_args(
    *,
    selection_path: Path,
    ranking_path: Path,
    output_path: Path,
    source_system: str = "artana-shadow-review",
    export_id: str = "shadow-export-2026-07-07",
    exported_at: str = "2026-07-07T07:00:00Z",
    exporter_id: str = "review-ops-a",
    redaction_statement: str = "No PHI or raw patient text included.",
    adjudication_path: Path | None = None,
) -> tuple[str, ...]:
    args = [
        "--study-id",
        "shadow-study-2026-07-07",
        "--study-type",
        "selection_and_review_ranking",
        "--study-evidence-kind",
        "synthetic_fixture",
        "--selection-reviews",
        str(selection_path),
        "--review-ranking",
        str(ranking_path),
        "--source-system",
        source_system,
        "--export-id",
        export_id,
        "--exported-at",
        exported_at,
        "--exporter-id",
        exporter_id,
        "--redaction-statement",
        redaction_statement,
        "--output",
        str(output_path),
    ]
    if adjudication_path is not None:
        args.extend(("--adjudication-log", str(adjudication_path)))
    return tuple(args)


def _base_args_without_source_identity(
    *,
    selection_path: Path,
    ranking_path: Path,
    output_path: Path,
    adjudication_path: Path | None = None,
) -> tuple[str, ...]:
    args = [
        "--study-id",
        "shadow-study-2026-07-07",
        "--study-type",
        "selection_and_review_ranking",
        "--study-evidence-kind",
        "synthetic_fixture",
        "--selection-reviews",
        str(selection_path),
        "--review-ranking",
        str(ranking_path),
        "--output",
        str(output_path),
    ]
    if adjudication_path is not None:
        args.extend(("--adjudication-log", str(adjudication_path)))
    return tuple(args)


def _write_source_exports(
    tmp_path: Path,
    *,
    include_adjudication: bool = False,
    selection_export: dict[str, object] | None = None,
    ranking_export: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    adjudication_path = tmp_path / "adjudication-log.txt"
    selection_path.write_text(
        json.dumps(selection_export or _selection_review_export())
    )
    ranking_path.write_text(json.dumps(ranking_export or _review_ranking_export()))
    if include_adjudication:
        adjudication_path.write_text("reviewer-a accepted all calibration labels\n")
    return selection_path, ranking_path, adjudication_path


def _source_export_identity() -> dict[str, object]:
    return {
        "source_system": "artana-shadow-review",
        "export_id": "shadow-export-2026-07-07",
        "exported_at": "2026-07-07T07:00:00Z",
        "exporter_id": "review-ops-a",
        "redaction_statement": "No PHI or raw patient text included.",
    }


def _selection_review_export() -> dict[str, object]:
    return {
        "schema_version": "evidence_selection_review_export.v2",
        **_source_export_identity(),
        "selection_reviews": _selection_reviews(),
    }


def _review_ranking_export() -> dict[str, object]:
    return {
        "schema_version": "evidence_selection_review_ranking_export.v2",
        **_source_export_identity(),
        "review_ranking": _review_ranking(),
    }


def _selection_reviews() -> list[dict[str, object]]:
    goals = [
        "Find MED13 congenital heart disease evidence.",
        "Find EGFR inhibitor response evidence.",
        "Find NTRK fusion treatment evidence.",
    ]
    return [
        {
            "run_id": f"00000000-0000-0000-0000-00000000000{index + 1}",
            "goal": goal,
            "reviewer_id": "reviewer-a",
            "candidate_record_ids": [
                f"record-{index}-a",
                f"record-{index}-b",
                f"record-{index}-c",
            ],
            "harness_selected_record_ids": [
                f"record-{index}-a",
                f"record-{index}-b",
            ],
            "human_selected_record_ids": [
                f"record-{index}-a",
                f"record-{index}-b",
            ],
            "harness_skipped_record_ids": [f"record-{index}-c"],
            "explanation_assessment": (
                adequate_explanation_assessment(f"record-{index}-a").model_dump(
                    mode="json",
                )
            ),
            "high_severity_overclaim_findings": [],
        }
        for index, goal in enumerate(goals)
    ]


def _review_ranking() -> dict[str, object]:
    goals = [
        "Find MED13 congenital heart disease evidence.",
        "Find EGFR inhibitor response evidence.",
        "Find NTRK fusion treatment evidence.",
    ]
    evidence_shapes = [
        "variant_disease_relation",
        "drug_response_relation",
        "fusion_treatment_relation",
    ]
    decisions = [
        {
            "source_kind": "proposal" if index % 2 == 0 else "review_item",
            "item_id": f"positive-{index}",
            "research_question_id": f"question-{index % 3}",
            "operational_ranking": _operational_ranking(1.0),
            "outcome": "positive",
            "reviewer_id": "reviewer-a",
            "goal": goals[index % len(goals)],
            "evidence_shape": evidence_shapes[index % len(evidence_shapes)],
        }
        for index in range(5)
    ]
    decisions.extend(
        {
            "source_kind": "proposal" if index % 2 == 0 else "review_item",
            "item_id": f"negative-{index}",
            "research_question_id": f"question-{index % 3}",
            "operational_ranking": _operational_ranking(0.0),
            "outcome": "negative",
            "reviewer_id": "reviewer-a",
            "goal": goals[index % len(goals)],
            "evidence_shape": evidence_shapes[index % len(evidence_shapes)],
        }
        for index in range(5)
    )
    return {
        "schema_version": "evidence_selection_review_ranking_calibration.v2",
        "study_id": "shadow-study-2026-07-07",
        "adjudication_note": "No reviewer disagreements in this sample.",
        "decisions": decisions,
    }


def _operational_ranking(value: float) -> dict[str, object]:
    return {
        "origin": "deterministic_policy",
        "value": value,
        "policy_id": "test_review_ranking",
        "policy_version": "v1",
        "mapping_version": "v1",
        "categorical_inputs": [
            {"field": "evidence_state", "value": "supported"},
        ],
        "caps": [],
        "vetoes": [],
        "blocking_categories": [],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
