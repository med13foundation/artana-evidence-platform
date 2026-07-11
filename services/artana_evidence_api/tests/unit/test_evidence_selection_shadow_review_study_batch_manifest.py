"""Tests for building strict shadow-review study batch manifests."""

from __future__ import annotations

import copy
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


def test_shadow_review_study_batch_manifest_builder_derives_strict_entries(
    tmp_path: Path,
) -> None:
    manifest_builder = _manifest_builder_module()
    batch = _batch_module()
    packet_dir = tmp_path / "packets"
    manifest_path = tmp_path / "manifests" / "batch-manifest.json"
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

    manifest = (
        manifest_builder.build_evidence_selection_shadow_review_study_batch_manifest(
            manifest_builder.EvidenceSelectionShadowReviewStudyBatchManifestBuildRequest(
                batch_id="real-shadow-review-batch-2026-07-07",
                packet_paths=(first_packet_path, second_packet_path),
                manifest_path=manifest_path,
                adjudication_note="Reviewer adjudicated every packet.",
                source_system="artana-shadow-review",
                export_id_prefix="real-shadow-2026-07-07",
                exported_at="2026-07-07T14:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
                description="Completed real shadow-review packet.",
            ),
        )
    )

    assert manifest.schema_version == "evidence_selection_shadow_review_study_batch.v1"
    assert manifest.batch_id == "real-shadow-review-batch-2026-07-07"
    assert [entry.entry_id for entry in manifest.entries] == [
        "01-shadow-study-one",
        "02-egfr-resistance-study",
    ]
    assert [str(entry.packet_path) for entry in manifest.entries] == [
        "../packets/braf.json",
        "../packets/egfr.json",
    ]
    assert [entry.output_subdir for entry in manifest.entries] == [
        "01-shadow-study-one",
        "02-egfr-resistance-study",
    ]
    assert [entry.export_id for entry in manifest.entries] == [
        "real-shadow-2026-07-07-01-shadow-study-one",
        "real-shadow-2026-07-07-02-egfr-resistance-study",
    ]
    assert all(
        entry.adjudication_note == "Reviewer adjudicated every packet."
        for entry in manifest.entries
    )
    assert all(
        entry.redaction_statement == "No PHI or raw patient text included."
        for entry in manifest.entries
    )
    batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
        manifest.model_dump(mode="json"),
    )


def test_shadow_review_study_batch_manifest_builder_rejects_incomplete_packet(
    tmp_path: Path,
) -> None:
    manifest_builder = _manifest_builder_module()
    packet = copy.deepcopy(
        _completed_packet_for_batch(
            study_id="shadow-study-one",
            source_run_id="11111111-1111-4111-8111-111111111111",
            goal="Assess BRAF targeted therapy evidence.",
            first_shape="variant_drug_response",
            second_shape="background_context",
        ),
    )
    selection_forms = packet["selection_review_forms"]
    assert isinstance(selection_forms, list)
    first_form = selection_forms[0]
    assert isinstance(first_form, dict)
    first_form["reviewer_id"] = None
    packet_path = _write_packet(tmp_path, "incomplete.json", packet)

    with pytest.raises(ValueError, match="completed shadow-review packet"):
        manifest_builder.build_evidence_selection_shadow_review_study_batch_manifest(
            manifest_builder.EvidenceSelectionShadowReviewStudyBatchManifestBuildRequest(
                batch_id="real-shadow-review-batch-2026-07-07",
                packet_paths=(packet_path,),
                manifest_path=tmp_path / "batch-manifest.json",
                adjudication_note="Reviewer adjudicated every packet.",
                source_system="artana-shadow-review",
                export_id_prefix="real-shadow-2026-07-07",
                exported_at="2026-07-07T14:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
            ),
        )


def _manifest_builder_module() -> object:
    try:
        return importlib.import_module(
            "artana_evidence_api.evidence_selection.shadow_review_study_batch_manifest",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review study batch manifest builder is missing: {exc}")


def _batch_module() -> object:
    try:
        return importlib.import_module(
            "artana_evidence_api.evidence_selection.shadow_review_study_batch",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review study batch module is missing: {exc}")


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
