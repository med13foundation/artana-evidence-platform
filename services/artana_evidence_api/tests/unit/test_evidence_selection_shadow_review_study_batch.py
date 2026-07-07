"""Tests for completed shadow-review study batch orchestration."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

from services.artana_evidence_api.tests.unit.test_evidence_selection_shadow_review_study_pipeline import (  # noqa: E501
    _completed_packet,
)


def test_shadow_review_study_batch_aggregates_passed_and_failed_gates(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    good_packet_path = _write_packet(tmp_path, "good-packet.json", _completed_packet())
    weak_packet_path = _write_packet(
        tmp_path,
        "weak-packet.json",
        _low_quality_packet(),
    )
    output_dir = tmp_path / "batch-output"

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
                {
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
                },
            ),
            output_dir=output_dir,
            thresholds=batch.EvidenceSelectionShadowReviewStudyBatchThresholds(
                min_selection_review_count=1,
                min_distinct_selection_goals=1,
                min_review_ranking_sample_count=2,
                min_distinct_ranking_goals=1,
                min_distinct_evidence_shapes=2,
            ),
        ),
    )

    assert result.batch_id == "batch-2026-07-07"
    assert result.passed is False
    assert result.entry_count == 2
    assert result.passed_entry_count == 1
    assert result.failed_entry_count == 1
    assert [entry.entry_id for entry in result.entries] == ["good-study", "weak-study"]
    assert result.entries[0].gate_passed is True
    assert result.entries[1].gate_passed is False
    assert result.entries[1].blocking_reasons
    assert result.entries[0].artifact_result.bundle_path == (
        output_dir / "good-study" / "evidence-selection-expert-study.json"
    )
    assert result.entries[1].artifact_result.bundle_path == (
        output_dir / "weak-study" / "evidence-selection-expert-study.json"
    )
    report = result.to_json()
    assert report["schema_version"] == "evidence_selection_shadow_review_study_batch_report.v1"
    assert report["passed"] is False
    assert report["passed_entry_count"] == 1
    assert report["failed_entry_count"] == 1


def test_shadow_review_study_batch_rejects_duplicate_entry_ids_before_writing(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    packet_path = _write_packet(tmp_path, "completed-packet.json", _completed_packet())
    output_dir = tmp_path / "batch-output"

    with pytest.raises(ValueError, match="Duplicate batch entry_id"):
        batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": "batch-2026-07-07",
                "entries": [
                    _manifest_entry(
                        entry_id="duplicated",
                        packet_path=packet_path,
                        output_subdir="first",
                        export_id="shadow-export-first",
                    ),
                    _manifest_entry(
                        entry_id="duplicated",
                        packet_path=packet_path,
                        output_subdir="second",
                        export_id="shadow-export-second",
                    ),
                ],
            },
        )

    assert not output_dir.exists()


def test_shadow_review_study_batch_rejects_duplicate_output_subdirs(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    first_packet_path = _write_packet(tmp_path, "first-packet.json", _completed_packet())
    second_packet_path = _write_packet(
        tmp_path,
        "second-packet.json",
        _completed_packet(),
    )

    with pytest.raises(ValueError, match="Duplicate batch output_subdir"):
        batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": "batch-2026-07-07",
                "entries": [
                    _manifest_entry(
                        entry_id="first",
                        packet_path=first_packet_path,
                        output_subdir="same-output",
                        export_id="shadow-export-first",
                    ),
                    _manifest_entry(
                        entry_id="second",
                        packet_path=second_packet_path,
                        output_subdir="same-output",
                        export_id="shadow-export-second",
                    ),
                ],
            },
        )


def test_shadow_review_study_batch_rejects_duplicate_export_ids(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    first_packet_path = _write_packet(tmp_path, "first-packet.json", _completed_packet())
    second_packet_path = _write_packet(
        tmp_path,
        "second-packet.json",
        _completed_packet(),
    )

    with pytest.raises(ValueError, match="Duplicate batch export_id"):
        batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": "batch-2026-07-07",
                "entries": [
                    _manifest_entry(
                        entry_id="first",
                        packet_path=first_packet_path,
                        output_subdir="first-output",
                        export_id="same-export",
                    ),
                    _manifest_entry(
                        entry_id="second",
                        packet_path=second_packet_path,
                        output_subdir="second-output",
                        export_id="same-export",
                    ),
                ],
            },
        )


def test_shadow_review_study_batch_rejects_unsafe_output_subdirs(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    packet_path = _write_packet(tmp_path, "completed-packet.json", _completed_packet())

    with pytest.raises(ValueError, match="output_subdir must be relative"):
        batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": "batch-2026-07-07",
                "entries": [
                    _manifest_entry(
                        entry_id="unsafe",
                        packet_path=packet_path,
                        output_subdir="../escape",
                        export_id="shadow-export-unsafe",
                    ),
                ],
            },
        )


def test_shadow_review_study_batch_rejects_manifest_artifact_collision(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    packet_path = _write_packet(tmp_path, "completed-packet.json", _completed_packet())
    output_dir = tmp_path / "batch-output"
    manifest_path = output_dir / "study-a" / "selection-review-labels.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("original manifest text\n")

    manifest = batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
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
    )

    with pytest.raises(ValueError, match="must not overwrite manifest"):
        batch.build_evidence_selection_shadow_review_study_batch(
            batch.EvidenceSelectionShadowReviewStudyBatchRequest(
                manifest=manifest,
                manifest_path=manifest_path,
                output_dir=output_dir,
                thresholds=batch.EvidenceSelectionShadowReviewStudyBatchThresholds(
                    min_selection_review_count=1,
                    min_distinct_selection_goals=1,
                    min_review_ranking_sample_count=2,
                    min_distinct_ranking_goals=1,
                    min_distinct_evidence_shapes=2,
                ),
            ),
        )

    assert manifest_path.read_text() == "original manifest text\n"


def test_shadow_review_study_batch_rejects_cross_entry_packet_artifact_collision(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    output_dir = tmp_path / "batch-output"
    colliding_packet_path = output_dir / "second" / "selection-review-labels.json"
    colliding_packet_path.parent.mkdir(parents=True)
    colliding_packet_path.write_text(json.dumps(_completed_packet()))
    original_packet_text = colliding_packet_path.read_text()
    second_packet_path = _write_packet(tmp_path, "second-packet.json", _completed_packet())

    manifest = batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
        {
            "schema_version": "evidence_selection_shadow_review_study_batch.v1",
            "batch_id": "batch-2026-07-07",
            "entries": [
                _manifest_entry(
                    entry_id="first",
                    packet_path=colliding_packet_path,
                    output_subdir="first",
                    export_id="shadow-export-first",
                ),
                _manifest_entry(
                    entry_id="second",
                    packet_path=second_packet_path,
                    output_subdir="second",
                    export_id="shadow-export-second",
                ),
            ],
        },
    )

    with pytest.raises(ValueError, match="must not overwrite source packet"):
        batch.build_evidence_selection_shadow_review_study_batch(
            batch.EvidenceSelectionShadowReviewStudyBatchRequest(
                manifest=manifest,
                output_dir=output_dir,
                thresholds=batch.EvidenceSelectionShadowReviewStudyBatchThresholds(
                    min_selection_review_count=1,
                    min_distinct_selection_goals=1,
                    min_review_ranking_sample_count=2,
                    min_distinct_ranking_goals=1,
                    min_distinct_evidence_shapes=2,
                ),
            ),
        )

    assert colliding_packet_path.read_text() == original_packet_text
    assert not (output_dir / "first" / "selection-review-labels.json").exists()


def _batch_module() -> object:
    try:
        return importlib.import_module(
            "artana_evidence_api.evidence_selection.shadow_review_study_batch",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review study batch module is missing: {exc}")


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


def _write_packet(tmp_path: Path, filename: str, packet: dict[str, object]) -> Path:
    packet_path = tmp_path / filename
    packet_path.write_text(json.dumps(packet))
    return packet_path


def _low_quality_packet() -> dict[str, object]:
    packet = copy.deepcopy(_completed_packet())
    selection_forms = packet["selection_review_forms"]
    assert isinstance(selection_forms, list)
    first_form = selection_forms[0]
    assert isinstance(first_form, dict)
    first_form["explanation_quality_score"] = 2
    return packet
