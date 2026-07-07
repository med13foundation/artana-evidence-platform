"""Tests for the source-export writer CLI."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def test_source_export_writer_cli_writes_both_exports(tmp_path: Path) -> None:
    cli = _cli_module()
    selection_input_path, ranking_input_path = _write_inputs(tmp_path)
    selection_export_path = tmp_path / "selection-review-export.json"
    ranking_export_path = tmp_path / "review-ranking-export.json"

    exit_code = cli.main(
        (
            "--selection-reviews",
            str(selection_input_path),
            "--review-ranking",
            str(ranking_input_path),
            "--selection-export-output",
            str(selection_export_path),
            "--review-ranking-export-output",
            str(ranking_export_path),
            "--source-system",
            "artana-shadow-review",
            "--export-id",
            "shadow-export-2026-07-07",
            "--exported-at",
            "2026-07-07T07:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
        ),
    )

    assert exit_code == 0
    assert json.loads(selection_export_path.read_text())["selection_reviews"]
    assert json.loads(ranking_export_path.read_text())["review_ranking"]["decisions"]


def test_source_export_writer_cli_rejects_invalid_identity_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    selection_input_path, ranking_input_path = _write_inputs(tmp_path)

    exit_code = cli.main(
        (
            "--selection-reviews",
            str(selection_input_path),
            "--review-ranking",
            str(ranking_input_path),
            "--selection-export-output",
            str(tmp_path / "selection-review-export.json"),
            "--review-ranking-export-output",
            str(tmp_path / "review-ranking-export.json"),
            "--source-system",
            " artana-shadow-review ",
            "--export-id",
            "shadow-export-2026-07-07",
            "--exported-at",
            "2026-07-07T07:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "leading or trailing whitespace" in captured.err
    assert "Traceback" not in captured.err


def _cli_module() -> object:
    try:
        return importlib.import_module("scripts.build_evidence_selection_source_exports")
    except ModuleNotFoundError as exc:
        pytest.fail(f"source export writer CLI is missing: {exc}")


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    selection_input_path = tmp_path / "selection-review-labels.json"
    ranking_input_path = tmp_path / "review-ranking-study.json"
    selection_input_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_input_path.write_text(json.dumps(_review_ranking()))
    return selection_input_path, ranking_input_path


def _selection_reviews() -> list[dict[str, object]]:
    return [
        {
            "run_id": f"00000000-0000-0000-0000-00000000000{index + 1}",
            "goal": f"review goal {index}",
            "reviewer_id": "reviewer-a",
            "harness_selected_record_ids": [f"record-{index}-a"],
            "human_selected_record_ids": [f"record-{index}-a"],
            "harness_skipped_record_ids": [f"record-{index}-b"],
            "explanation_quality_score": 4,
            "high_severity_overclaim_count": 0,
        }
        for index in range(3)
    ]


def _review_ranking() -> dict[str, object]:
    decisions = [
        {
            "source_kind": "proposal" if index < 5 else "review_item",
            "item_id": f"ranking-item-{index}",
            "ranking_score": 0.9 if index % 2 == 0 else 0.1,
            "outcome": "positive" if index % 2 == 0 else "negative",
            "reviewer_id": "reviewer-a",
            "goal": f"review goal {index % 3}",
            "evidence_shape": f"shape-{index % 3}",
        }
        for index in range(10)
    ]
    return {
        "schema_version": "evidence_selection_review_ranking_calibration.v1",
        "study_id": "shadow-study-2026-07-07",
        "adjudication_note": "Reviewer adjudicated all ranking labels.",
        "decisions": decisions,
    }
