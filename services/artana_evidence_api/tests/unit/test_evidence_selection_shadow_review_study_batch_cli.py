"""Tests for the completed shadow-review study batch CLI."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

from services.artana_evidence_api.tests.unit.test_evidence_selection_shadow_review_study_pipeline import (  # noqa: E501
    _completed_packet,
)


def test_shadow_review_study_batch_cli_writes_reports_and_fails_on_failed_entry(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    manifest_path = _write_manifest(tmp_path)
    output_dir = tmp_path / "batch-output"

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
        ),
    )

    assert exit_code == 1
    batch_report = json.loads(
        (output_dir / "shadow-review-study-batch.json").read_text(),
    )
    assert batch_report["passed"] is False
    assert batch_report["entry_count"] == 2
    assert batch_report["passed_entry_count"] == 1
    assert batch_report["failed_entry_count"] == 1
    assert (output_dir / "shadow-review-study-batch.md").exists()
    assert (
        output_dir
        / "good-study"
        / "gate"
        / "evidence_selection_expert_study_gate.json"
    ).exists()
    weak_gate_report = json.loads(
        (
            output_dir
            / "weak-study"
            / "gate"
            / "evidence_selection_expert_study_gate.json"
        ).read_text(),
    )
    assert weak_gate_report["gate"]["passed"] is False
    assert weak_gate_report["gate"]["blocking_reasons"]
    assert (
        output_dir
        / "weak-study"
        / "gate"
        / "evidence_selection_expert_study_gate.md"
    ).exists()


def test_shadow_review_study_batch_cli_allows_failed_gate_when_requested(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    manifest_path = _write_manifest(tmp_path)
    output_dir = tmp_path / "batch-output"

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--allow-failed-gate",
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
        ),
    )

    assert exit_code == 0
    batch_report = json.loads(
        (output_dir / "shadow-review-study-batch.json").read_text(),
    )
    assert batch_report["passed"] is False
    assert batch_report["failed_entry_count"] == 1


def test_shadow_review_study_batch_cli_rejects_report_manifest_collision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    output_dir = tmp_path / "batch-output"
    output_dir.mkdir()
    manifest_path = output_dir / "shadow-review-study-batch.json"
    manifest_payload = _manifest_payload(tmp_path)
    manifest_path.write_text(json.dumps(manifest_payload))
    original_manifest_text = manifest_path.read_text()

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must not overwrite manifest" in captured.err
    assert "Traceback" not in captured.err
    assert manifest_path.read_text() == original_manifest_text


def test_shadow_review_study_batch_cli_rejects_report_packet_collision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    output_dir = tmp_path / "batch-output"
    output_dir.mkdir()
    packet_path = output_dir / "shadow-review-study-batch.json"
    packet_path.write_text(json.dumps(_completed_packet()))
    original_packet_text = packet_path.read_text()
    manifest_path = tmp_path / "shadow-review-batch.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": "batch-2026-07-07",
                "entries": [
                    _manifest_entry(
                        entry_id="study-a",
                        packet_path=packet_path,
                        output_subdir="study-a",
                        export_id="shadow-export-study-a",
                    ),
                ],
            },
        ),
    )

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must not overwrite source packet" in captured.err
    assert "Traceback" not in captured.err
    assert packet_path.read_text() == original_packet_text


def _cli_module() -> object:
    try:
        return importlib.import_module(
            "scripts.build_evidence_selection_shadow_review_study_batch",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review study batch CLI is missing: {exc}")


def _write_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "shadow-review-batch.json"
    manifest_path.write_text(json.dumps(_manifest_payload(tmp_path)))
    return manifest_path


def _manifest_payload(tmp_path: Path) -> dict[str, object]:
    good_packet_path = tmp_path / "good-packet.json"
    weak_packet_path = tmp_path / "weak-packet.json"
    good_packet_path.write_text(json.dumps(_completed_packet()))
    weak_packet_path.write_text(json.dumps(_low_quality_packet()))
    return {
        "schema_version": "evidence_selection_shadow_review_study_batch.v1",
        "batch_id": "batch-2026-07-07",
        "entries": [
            _manifest_entry(
                entry_id="good-study",
                packet_path=good_packet_path,
                output_subdir="good-study",
                export_id="shadow-export-good",
            ),
            _manifest_entry(
                entry_id="weak-study",
                packet_path=weak_packet_path,
                output_subdir="weak-study",
                export_id="shadow-export-weak",
            ),
        ],
    }


def _manifest_entry(
    *,
    entry_id: str,
    packet_path: Path,
    output_subdir: str,
    export_id: str,
) -> dict[str, object]:
    return {
        "entry_id": entry_id,
        "packet_path": str(packet_path),
        "output_subdir": output_subdir,
        "adjudication_note": f"{entry_id} labels completed by reviewer.",
        "source_system": "artana-shadow-review",
        "export_id": export_id,
        "exported_at": "2026-07-07T14:00:00Z",
        "exporter_id": "review-ops-a",
        "redaction_statement": "No PHI or raw patient text included.",
        "description": f"{entry_id} completed shadow-review packet.",
    }


def _low_quality_packet() -> dict[str, object]:
    packet = copy.deepcopy(_completed_packet())
    selection_forms = packet["selection_review_forms"]
    assert isinstance(selection_forms, list)
    first_form = selection_forms[0]
    assert isinstance(first_form, dict)
    first_form["explanation_quality_score"] = 2
    return packet
