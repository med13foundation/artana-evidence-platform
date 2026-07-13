"""Tests for the completed shadow-review study pipeline CLI."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.shadow_review_completion import (
    machine_packet_sidecar_path,
)

from services.artana_evidence_api.tests.unit.test_evidence_selection_shadow_review_study_pipeline import (  # noqa: E501
    _completed_packet,
    _machine_packet_for_completed_packet,
    _selection_only_completed_packet,
)


def test_shadow_review_study_pipeline_cli_writes_artifacts_but_blocks_thin_gate(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    output_dir = tmp_path / "shadow-review-study"
    _write_completed_packet(packet_path)

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--output-dir",
            str(output_dir),
            "--adjudication-note",
            "Reviewer A completed all labels.",
            "--source-system",
            "artana-shadow-review",
            "--export-id",
            "shadow-export-2026-07-07",
            "--exported-at",
            "2026-07-07T14:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
            "--study-evidence-kind",
            "real_shadow_review",
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
    bundle = json.loads(
        (output_dir / "evidence-selection-expert-study.json").read_text()
    )
    gate_report = json.loads(
        (output_dir / "gate" / "evidence_selection_expert_study_gate.json").read_text(),
    )
    assert bundle["source_manifest"]["source_system"] == "artana-shadow-review"
    assert gate_report["gate"]["passed"] is False
    assert any(
        "reviewer outcome is required for source kind" in reason
        for reason in gate_report["gate"]["blocking_reasons"]
    )
    assert (output_dir / "gate" / "evidence_selection_expert_study_gate.md").exists()


def test_shadow_review_study_pipeline_cli_runs_selection_only_without_ranking_artifacts(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-selection-packet.json"
    output_dir = tmp_path / "selection-study"
    _write_completed_packet(packet_path, _selection_only_completed_packet())

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--output-dir",
            str(output_dir),
            "--source-system",
            "artana-shadow-review",
            "--export-id",
            "selection-export-2026-07-13",
            "--exported-at",
            "2026-07-13T14:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
            "--study-evidence-kind",
            "real_shadow_review",
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
        ),
    )

    assert exit_code == 0
    bundle = json.loads(
        (output_dir / "evidence-selection-expert-study.json").read_text()
    )
    assert bundle["study_type"] == "selection_relevance"
    assert "review_ranking" not in bundle
    assert not (output_dir / "review-ranking-study.json").exists()
    assert not (output_dir / "review-ranking-export.json").exists()


def test_shadow_review_study_pipeline_cli_returns_nonzero_but_keeps_failed_gate_report(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    output_dir = tmp_path / "shadow-review-study"
    _write_completed_packet(packet_path)

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--output-dir",
            str(output_dir),
            "--adjudication-note",
            "Reviewer A completed all labels.",
            "--source-system",
            "artana-shadow-review",
            "--export-id",
            "shadow-export-2026-07-07",
            "--exported-at",
            "2026-07-07T14:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
            "--study-evidence-kind",
            "real_shadow_review",
        ),
    )

    assert exit_code == 1
    assert (output_dir / "selection-review-labels.json").exists()
    assert (output_dir / "review-ranking-study.json").exists()
    gate_report = json.loads(
        (output_dir / "gate" / "evidence_selection_expert_study_gate.json").read_text(),
    )
    assert gate_report["gate"]["passed"] is False
    assert gate_report["gate"]["blocking_reasons"]


def test_shadow_review_study_pipeline_cli_removes_artifacts_when_gate_report_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    output_dir = tmp_path / "shadow-review-study"
    _write_completed_packet(packet_path)

    def fail_gate_report(*_args: object, **_kwargs: object) -> object:
        raise OSError("injected gate-report failure")

    monkeypatch.setattr(
        cli,
        "write_evidence_selection_expert_study_gate_report",
        fail_gate_report,
    )

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--output-dir",
            str(output_dir),
            "--adjudication-note",
            "Reviewer A completed all labels.",
            "--source-system",
            "artana-shadow-review",
            "--export-id",
            "shadow-export-2026-07-07",
            "--exported-at",
            "2026-07-07T14:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
            "--study-evidence-kind",
            "real_shadow_review",
        ),
    )

    assert exit_code == 1
    assert not output_dir.exists()


def test_shadow_review_study_pipeline_cli_rejects_file_output_dir_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "completed-shadow-review-packet.json"
    output_dir = tmp_path / "shadow-review-study.json"
    _write_completed_packet(packet_path)
    output_dir.write_text("not a directory\n")

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--output-dir",
            str(output_dir),
            "--adjudication-note",
            "Reviewer A completed all labels.",
            "--source-system",
            "artana-shadow-review",
            "--export-id",
            "shadow-export-2026-07-07",
            "--exported-at",
            "2026-07-07T14:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
            "--study-evidence-kind",
            "real_shadow_review",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Output directory must be a directory" in captured.err
    assert "Traceback" not in captured.err
    assert output_dir.read_text() == "not a directory\n"


def test_shadow_review_study_pipeline_cli_rejects_packet_output_collision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    output_dir = tmp_path / "shadow-review-study"
    output_dir.mkdir()
    packet_path = output_dir / "selection-review-labels.json"
    _write_completed_packet(packet_path)
    original_packet_text = packet_path.read_text()

    exit_code = cli.main(
        (
            "--packet",
            str(packet_path),
            "--output-dir",
            str(output_dir),
            "--adjudication-note",
            "Reviewer A completed all labels.",
            "--source-system",
            "artana-shadow-review",
            "--export-id",
            "shadow-export-2026-07-07",
            "--exported-at",
            "2026-07-07T14:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
            "--study-evidence-kind",
            "real_shadow_review",
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
            "scripts.build_evidence_selection_shadow_review_study_artifacts",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review study pipeline CLI is missing: {exc}")


def _write_completed_packet(
    packet_path: Path,
    packet: dict[str, object] | None = None,
) -> Path:
    packet = packet or _completed_packet()
    machine_packet = _machine_packet_for_completed_packet(packet)
    packet["machine_packet_sha256"] = machine_packet["machine_packet_sha256"]
    packet["machine_packet_signature"] = machine_packet["machine_packet_signature"]
    packet_path.write_text(json.dumps(packet))
    machine_packet_sidecar_path(packet_path).write_text(json.dumps(machine_packet))
    return packet_path
