"""Tests for the shadow-review study batch manifest builder CLI."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.shadow_review_completion import (
    machine_packet_sidecar_path,
)

from services.artana_evidence_api.tests.unit.test_evidence_selection_shadow_review_study_batch import (  # noqa: E501
    _completed_packet_for_batch,
)
from services.artana_evidence_api.tests.unit.test_evidence_selection_shadow_review_study_pipeline import (  # noqa: E501
    _machine_packet_for_completed_packet,
)


def test_shadow_review_study_batch_manifest_cli_writes_strict_manifest(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    packet_dir = tmp_path / "packets"
    first_packet_path = _write_packet(
        packet_dir,
        "braf.json",
        _completed_packet_for_batch(
            study_id="Shadow Study One",
            source_run_id="11111111-1111-4111-8111-111111111111",
            goal="Assess BRAF targeted therapy evidence.",
            first_shape="variant_drug_response",
            second_shape="background_context",
        ),
    )
    second_packet_path = _write_packet(
        packet_dir,
        "egfr.json",
        _completed_packet_for_batch(
            study_id="EGFR Resistance Study",
            source_run_id="22222222-2222-4222-8222-222222222222",
            goal="Assess EGFR resistance evidence.",
            first_shape="drug_resistance",
            second_shape="mechanistic_context",
        ),
    )
    output_path = tmp_path / "manifests" / "batch-manifest.json"

    exit_code = cli.main(
        (
            "--batch-id",
            "real-shadow-review-batch-2026-07-07",
            "--packet",
            str(first_packet_path),
            "--packet",
            str(second_packet_path),
            "--output",
            str(output_path),
            "--adjudication-note",
            "Reviewer adjudicated every packet.",
            "--source-system",
            "artana-shadow-review",
            "--export-id-prefix",
            "real-shadow-2026-07-07",
            "--exported-at",
            "2026-07-07T14:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
            "--description",
            "Completed real shadow-review packet.",
        ),
    )

    assert exit_code == 0
    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "evidence_selection_shadow_review_study_batch.v1"
    assert manifest["batch_id"] == "real-shadow-review-batch-2026-07-07"
    assert [entry["entry_id"] for entry in manifest["entries"]] == [
        "01-shadow-study-one",
        "02-egfr-resistance-study",
    ]
    assert [entry["packet_path"] for entry in manifest["entries"]] == [
        "../packets/braf.json",
        "../packets/egfr.json",
    ]


def test_shadow_review_study_batch_manifest_cli_rejects_source_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    packet_path = _write_packet(
        tmp_path,
        "packet.json",
        _completed_packet_for_batch(
            study_id="Shadow Study One",
            source_run_id="11111111-1111-4111-8111-111111111111",
            goal="Assess BRAF targeted therapy evidence.",
            first_shape="variant_drug_response",
            second_shape="background_context",
        ),
    )
    original_packet = packet_path.read_text(encoding="utf-8")

    exit_code = cli.main(
        (
            "--batch-id",
            "real-shadow-review-batch-2026-07-07",
            "--packet",
            str(packet_path),
            "--output",
            str(packet_path),
            "--adjudication-note",
            "Reviewer adjudicated every packet.",
            "--source-system",
            "artana-shadow-review",
            "--export-id-prefix",
            "real-shadow-2026-07-07",
            "--exported-at",
            "2026-07-07T14:00:00Z",
            "--exporter-id",
            "review-ops-a",
            "--redaction-statement",
            "No PHI or raw patient text included.",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must not overwrite source packet" in captured.err
    assert packet_path.read_text(encoding="utf-8") == original_packet


def _cli_module() -> object:
    try:
        return importlib.import_module(
            "scripts.build_evidence_selection_shadow_review_study_batch_manifest",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review study batch manifest CLI is missing: {exc}")


def _write_packet(
    directory: Path,
    filename: str,
    packet: dict[str, object],
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    packet_path = directory / filename
    machine_packet = _machine_packet_for_completed_packet(packet)
    packet["machine_packet_sha256"] = machine_packet["machine_packet_sha256"]
    packet["machine_packet_signature"] = machine_packet["machine_packet_signature"]
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    machine_packet_sidecar_path(packet_path).write_text(
        json.dumps(machine_packet),
        encoding="utf-8",
    )
    return packet_path
