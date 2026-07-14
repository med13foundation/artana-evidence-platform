"""CLI coverage for atomic blinded expert-pilot packet publication."""

from __future__ import annotations

import json
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.pilot_contracts import (
    EvidenceSelectionExpertPilotMachineSidecar,
    EvidenceSelectionExpertPilotReviewerPacket,
)

from scripts.build_evidence_selection_expert_pilot_packets import main

PROTOCOL_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_expert_pilot_protocol_v1.json"
)
SIGNING_KEY_ENV = "ARTANA_EVIDENCE_SHADOW_REVIEW_PACKET_SIGNING_KEY"


def test_cli_publishes_blinded_packets_and_private_sidecars(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv(SIGNING_KEY_ENV, "cli-test-producer-key")
    output_dir = tmp_path / "expert-pilot"

    result = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--output-dir",
            str(output_dir),
        )
    )

    assert result == 0
    manifest = json.loads(
        (output_dir / "publication_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["independent_reviewer_count"] == 2
    assert manifest["reviewer_packet_count"] == 8
    assert manifest["candidate_review_count"] == 66
    assert manifest["production_readiness_claim"] is False
    assert manifest["production_calibration_claim"] is False
    assert len(list((output_dir / "reviewer_packets").rglob("*.json"))) == 8
    assert len(list((output_dir / "machine_sidecars").rglob("*.json"))) == 8
    reviewer_paths = list((output_dir / "reviewer_packets").rglob("*.json"))
    for reviewer_path in reviewer_paths:
        relative_path = reviewer_path.relative_to(output_dir / "reviewer_packets")
        packet = EvidenceSelectionExpertPilotReviewerPacket.model_validate_json(
            reviewer_path.read_bytes()
        )
        sidecar = EvidenceSelectionExpertPilotMachineSidecar.model_validate_json(
            (output_dir / "machine_sidecars" / relative_path).read_bytes()
        )
        assert reviewer_path.stem == packet.review_case_id
        assert packet.review_case_id == sidecar.review_case_id
        assert reviewer_path.stem.startswith("case-")
        assert sidecar.case_id not in reviewer_path.as_posix()
    reviewer_payload = json.loads(reviewer_paths[0].read_text(encoding="utf-8"))
    assert "candidate_bindings" not in reviewer_payload
    assert "producer_signature" not in reviewer_payload
    assert "production_readiness=false" in capsys.readouterr().out


def test_cli_fails_closed_without_signing_key_or_on_existing_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    missing_key_output = tmp_path / "missing-key"

    result = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--output-dir",
            str(missing_key_output),
        )
    )

    assert result == 1
    assert not missing_key_output.exists()
    assert SIGNING_KEY_ENV in capsys.readouterr().err

    monkeypatch.setenv(SIGNING_KEY_ENV, "cli-test-producer-key")
    existing_output = tmp_path / "existing"
    existing_output.mkdir()
    result = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--output-dir",
            str(existing_output),
        )
    )
    assert result == 1
    assert "must not already exist" in capsys.readouterr().err
