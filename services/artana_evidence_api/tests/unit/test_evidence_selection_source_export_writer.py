"""Tests for writing self-describing evidence-selection source exports."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.study_bundle import (
    EvidenceSelectionExpertStudyBundleRequest,
    build_evidence_selection_expert_study_bundle,
)


def test_source_export_writer_creates_builder_ready_exports(tmp_path: Path) -> None:
    writer = _writer_module()
    selection_input_path = tmp_path / "selection-review-labels.json"
    ranking_input_path = tmp_path / "review-ranking-study.json"
    selection_export_path = tmp_path / "selection-review-export.json"
    ranking_export_path = tmp_path / "review-ranking-export.json"
    selection_input_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_input_path.write_text(json.dumps(_review_ranking()))

    result = writer.write_evidence_selection_source_exports(
        writer.EvidenceSelectionSourceExportWriteRequest(
            selection_reviews_path=selection_input_path,
            review_ranking_path=ranking_input_path,
            selection_export_path=selection_export_path,
            review_ranking_export_path=ranking_export_path,
            source_system="artana-shadow-review",
            export_id="shadow-export-2026-07-07",
            exported_at="2026-07-07T07:00:00Z",
            exporter_id="review-ops-a",
            redaction_statement="No PHI or raw patient text included.",
        ),
    )

    assert result.selection_review_count == 3
    assert result.review_ranking_decision_count == 10
    selection_export = json.loads(selection_export_path.read_text())
    ranking_export = json.loads(ranking_export_path.read_text())
    assert selection_export["schema_version"] == "evidence_selection_review_export.v1"
    assert ranking_export["schema_version"] == (
        "evidence_selection_review_ranking_export.v1"
    )
    assert selection_export["source_system"] == "artana-shadow-review"
    assert ranking_export["exported_at"] == "2026-07-07T07:00:00Z"

    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id="shadow-study-2026-07-07",
            study_evidence_kind="synthetic_fixture",
            selection_reviews_path=selection_export_path,
            review_ranking_path=ranking_export_path,
        ),
    )

    assert bundle.source_manifest is not None
    assert bundle.source_manifest.export_id == "shadow-export-2026-07-07"


def test_source_export_writer_rejects_output_that_overwrites_input(
    tmp_path: Path,
) -> None:
    writer = _writer_module()
    selection_input_path = tmp_path / "selection-review-labels.json"
    ranking_input_path = tmp_path / "review-ranking-study.json"
    ranking_export_path = tmp_path / "review-ranking-export.json"
    selection_input_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_input_path.write_text(json.dumps(_review_ranking()))
    original_selection_text = selection_input_path.read_text()

    with pytest.raises(ValueError, match="must not overwrite source input"):
        writer.write_evidence_selection_source_exports(
            writer.EvidenceSelectionSourceExportWriteRequest(
                selection_reviews_path=selection_input_path,
                review_ranking_path=ranking_input_path,
                selection_export_path=selection_input_path,
                review_ranking_export_path=ranking_export_path,
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T07:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
            ),
        )
    assert selection_input_path.read_text() == original_selection_text


def test_source_export_writer_rejects_hard_linked_output_that_overwrites_input(
    tmp_path: Path,
) -> None:
    writer = _writer_module()
    selection_input_path = tmp_path / "selection-review-labels.json"
    ranking_input_path = tmp_path / "review-ranking-study.json"
    selection_export_path = tmp_path / "selection-review-export.json"
    ranking_export_path = tmp_path / "review-ranking-export.json"
    selection_input_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_input_path.write_text(json.dumps(_review_ranking()))
    os.link(selection_input_path, selection_export_path)

    with pytest.raises(ValueError, match="must not overwrite source input"):
        writer.write_evidence_selection_source_exports(
            writer.EvidenceSelectionSourceExportWriteRequest(
                selection_reviews_path=selection_input_path,
                review_ranking_path=ranking_input_path,
                selection_export_path=selection_export_path,
                review_ranking_export_path=ranking_export_path,
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T07:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
            ),
        )


def test_source_export_writer_rejects_colliding_output_paths(tmp_path: Path) -> None:
    writer = _writer_module()
    selection_input_path = tmp_path / "selection-review-labels.json"
    ranking_input_path = tmp_path / "review-ranking-study.json"
    shared_output_path = tmp_path / "source-export.json"
    selection_input_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_input_path.write_text(json.dumps(_review_ranking()))

    with pytest.raises(ValueError, match="must be different files"):
        writer.write_evidence_selection_source_exports(
            writer.EvidenceSelectionSourceExportWriteRequest(
                selection_reviews_path=selection_input_path,
                review_ranking_path=ranking_input_path,
                selection_export_path=shared_output_path,
                review_ranking_export_path=shared_output_path,
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T07:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
            ),
        )


def test_source_export_writer_keeps_paired_outputs_all_or_nothing(
    tmp_path: Path,
) -> None:
    writer = _writer_module()
    selection_input_path = tmp_path / "selection-review-labels.json"
    ranking_input_path = tmp_path / "review-ranking-study.json"
    selection_export_path = tmp_path / "selection-review-export.json"
    ranking_export_path = tmp_path / "review-ranking-export.json"
    ranking_export_path.mkdir()
    selection_input_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_input_path.write_text(json.dumps(_review_ranking()))
    selection_export_path.write_text("existing selection export")

    with pytest.raises(ValueError, match="Unable to write paired source exports"):
        writer.write_evidence_selection_source_exports(
            writer.EvidenceSelectionSourceExportWriteRequest(
                selection_reviews_path=selection_input_path,
                review_ranking_path=ranking_input_path,
                selection_export_path=selection_export_path,
                review_ranking_export_path=ranking_export_path,
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T07:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
            ),
        )

    assert selection_export_path.read_text() == "existing selection export"
    assert not any(tmp_path.glob(".selection-review-export.json.tmp-*"))
    assert not any(tmp_path.glob(".review-ranking-export.json.tmp-*"))


def test_source_export_writer_rolls_back_first_replace_when_second_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _writer_module()
    selection_input_path = tmp_path / "selection-review-labels.json"
    ranking_input_path = tmp_path / "review-ranking-study.json"
    selection_export_path = tmp_path / "selection-review-export.json"
    ranking_export_path = tmp_path / "review-ranking-export.json"
    selection_input_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_input_path.write_text(json.dumps(_review_ranking()))
    selection_export_path.write_text("old selection export")
    ranking_export_path.write_text("old ranking export")
    original_replace = Path.replace

    def _fail_second_final_replace(self: Path, target: Path) -> Path:
        if target == ranking_export_path and self.name.startswith(
            ".review-ranking-export.json.tmp-",
        ):
            raise OSError("simulated second final replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", _fail_second_final_replace)

    with pytest.raises(ValueError, match="Unable to write paired source exports"):
        writer.write_evidence_selection_source_exports(
            writer.EvidenceSelectionSourceExportWriteRequest(
                selection_reviews_path=selection_input_path,
                review_ranking_path=ranking_input_path,
                selection_export_path=selection_export_path,
                review_ranking_export_path=ranking_export_path,
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T07:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
            ),
        )

    assert selection_export_path.read_text() == "old selection export"
    assert ranking_export_path.read_text() == "old ranking export"
    assert not any(tmp_path.glob(".selection-review-export.json.tmp-*"))
    assert not any(tmp_path.glob(".review-ranking-export.json.tmp-*"))


def test_source_export_writer_rolls_back_first_backup_when_second_backup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _writer_module()
    selection_input_path = tmp_path / "selection-review-labels.json"
    ranking_input_path = tmp_path / "review-ranking-study.json"
    selection_export_path = tmp_path / "selection-review-export.json"
    ranking_export_path = tmp_path / "review-ranking-export.json"
    selection_input_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_input_path.write_text(json.dumps(_review_ranking()))
    selection_export_path.write_text("old selection export")
    ranking_export_path.write_text("old ranking export")
    original_replace = Path.replace

    def _fail_second_backup_replace(self: Path, target: Path) -> Path:
        if self == ranking_export_path and target.name.startswith(
            ".review-ranking-export.json.bak-",
        ):
            raise OSError("simulated second backup replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", _fail_second_backup_replace)

    with pytest.raises(ValueError, match="Unable to write paired source exports"):
        writer.write_evidence_selection_source_exports(
            writer.EvidenceSelectionSourceExportWriteRequest(
                selection_reviews_path=selection_input_path,
                review_ranking_path=ranking_input_path,
                selection_export_path=selection_export_path,
                review_ranking_export_path=ranking_export_path,
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T07:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
            ),
        )

    assert selection_export_path.read_text() == "old selection export"
    assert ranking_export_path.read_text() == "old ranking export"
    assert not any(tmp_path.glob(".selection-review-export.json.tmp-*"))
    assert not any(tmp_path.glob(".review-ranking-export.json.tmp-*"))
    assert not any(tmp_path.glob(".selection-review-export.json.bak-*"))
    assert not any(tmp_path.glob(".review-ranking-export.json.bak-*"))


def _writer_module() -> object:
    try:
        return importlib.import_module(
            "artana_evidence_api.evidence_selection.source_export_writer",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"source export writer module is missing: {exc}")


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
            "harness_selected_record_ids": [
                f"record-{index}-a",
                f"record-{index}-b",
            ],
            "human_selected_record_ids": [
                f"record-{index}-a",
                f"record-{index}-b",
            ],
            "harness_skipped_record_ids": [f"record-{index}-c"],
            "explanation_quality_score": 4,
            "high_severity_overclaim_count": 0,
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
    return {
        "schema_version": "evidence_selection_review_ranking_calibration.v1",
        "study_id": "shadow-study-2026-07-07",
        "adjudication_note": "Reviewer adjudicated all ranking labels.",
        "decisions": [
            {
                "source_kind": "proposal" if index < 5 else "review_item",
                "item_id": f"ranking-item-{index}",
                "ranking_score": 0.9 if index % 2 == 0 else 0.1,
                "outcome": "positive" if index % 2 == 0 else "negative",
                "reviewer_id": "reviewer-a",
                "goal": goals[index % len(goals)],
                "evidence_shape": evidence_shapes[index % len(evidence_shapes)],
            }
            for index in range(10)
        ],
    }
