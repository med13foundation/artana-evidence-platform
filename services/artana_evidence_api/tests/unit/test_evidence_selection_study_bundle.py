"""Tests for reproducible evidence-selection expert-study bundle assembly."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from artana_evidence_api.evidence_selection.study_bundle import (
    EvidenceSelectionExpertStudyBundleRequest,
    build_evidence_selection_expert_study_bundle,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyGateThresholds,
    ReviewRankingCalibrationGateThresholds,
    evaluate_evidence_selection_expert_study_gate,
)
from pydantic import ValidationError


def test_builds_expert_study_bundle_with_computed_source_manifest(
    tmp_path: Path,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    adjudication_path = tmp_path / "adjudication-log.txt"
    selection_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_path.write_text(json.dumps(_review_ranking()))
    adjudication_path.write_text("reviewer-a accepted all calibration labels\n")

    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id="shadow-study-2026-07-07",
            study_evidence_kind="synthetic_fixture",
            selection_reviews_path=selection_path,
            review_ranking_path=ranking_path,
            adjudication_log_path=adjudication_path,
            source_system="artana-shadow-review",
            export_id="shadow-export-2026-07-07",
            exported_at=datetime(2026, 7, 7, 7, 0, tzinfo=UTC),
            exporter_id="review-ops-a",
            redaction_statement="No PHI or raw patient text included.",
            description="Reproducible expert/shadow study bundle.",
        ),
    )

    source_manifest = bundle.source_manifest
    assert source_manifest is not None
    assert bundle.schema_version == "evidence_selection_expert_study.v1"
    assert bundle.study_id == "shadow-study-2026-07-07"
    assert tuple(source_manifest.selection_review_run_ids) == tuple(
        UUID(review["run_id"]) for review in _selection_reviews()
    )
    assert source_manifest.review_ranking_decision_keys == tuple(
        f"{decision['source_kind']}:{decision['item_id']}"
        for decision in _review_ranking()["decisions"]
    )
    assert source_manifest.reviewer_roster == ("reviewer-a",)
    assert {
        artifact.artifact_kind: artifact.sha256
        for artifact in source_manifest.source_artifacts
    } == {
        "selection_review_export": _sha256(selection_path),
        "review_ranking_export": _sha256(ranking_path),
        "adjudication_log": _sha256(adjudication_path),
    }

    gate_report = evaluate_evidence_selection_expert_study_gate(
        bundle,
        thresholds=EvidenceSelectionExpertStudyGateThresholds(
            min_selection_review_count=3,
            min_distinct_selection_goals=3,
            min_source_artifact_count=3,
        ),
        review_ranking_thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=10,
            max_expected_calibration_error=0.05,
            min_distinct_goals=3,
            min_distinct_evidence_shapes=3,
        ),
    )

    assert gate_report.passed is False
    assert any(
        "real shadow-review evidence" in reason
        for reason in gate_report.blocking_reasons
    )


def test_build_preserves_duplicate_selection_run_ids_for_gate_detection(
    tmp_path: Path,
) -> None:
    duplicate_run_id = "00000000-0000-0000-0000-000000000001"
    selection_reviews = _selection_reviews()
    selection_reviews[1]["run_id"] = duplicate_run_id
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    selection_path.write_text(json.dumps({"selection_reviews": selection_reviews}))
    ranking_path.write_text(json.dumps(_review_ranking()))

    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id="duplicate-shadow-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews_path=selection_path,
            review_ranking_path=ranking_path,
            source_system="artana-shadow-review",
            export_id="shadow-export-duplicate",
            exported_at=datetime(2026, 7, 7, 7, 0, tzinfo=UTC),
            exporter_id="review-ops-a",
            redaction_statement="No PHI or raw patient text included.",
        ),
    )

    source_manifest = bundle.source_manifest
    assert source_manifest is not None
    assert source_manifest.selection_review_run_ids.count(UUID(duplicate_run_id)) == 2

    gate_report = evaluate_evidence_selection_expert_study_gate(
        bundle,
        review_ranking_thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=10,
            max_expected_calibration_error=0.05,
        ),
    )

    assert gate_report.passed is False
    assert any(
        "selection review run IDs" in reason
        for reason in gate_report.blocking_reasons
    )


def test_build_preserves_duplicate_review_ranking_keys_for_gate_detection(
    tmp_path: Path,
) -> None:
    ranking = _review_ranking()
    decisions = ranking["decisions"]
    assert isinstance(decisions, list)
    first_decision = decisions[0]
    assert isinstance(first_decision, dict)
    duplicate_decision = decisions[1]
    assert isinstance(duplicate_decision, dict)
    duplicate_decision["source_kind"] = first_decision["source_kind"]
    duplicate_decision["item_id"] = first_decision["item_id"]
    duplicate_key = f"{first_decision['source_kind']}:{first_decision['item_id']}"
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    selection_path.write_text(json.dumps({"selection_reviews": _selection_reviews()}))
    ranking_path.write_text(json.dumps(ranking))

    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id="duplicate-ranking-shadow-study",
            study_evidence_kind="real_shadow_review",
            selection_reviews_path=selection_path,
            review_ranking_path=ranking_path,
            source_system="artana-shadow-review",
            export_id="shadow-export-duplicate-ranking",
            exported_at=datetime(2026, 7, 7, 7, 0, tzinfo=UTC),
            exporter_id="review-ops-a",
            redaction_statement="No PHI or raw patient text included.",
        ),
    )

    source_manifest = bundle.source_manifest
    assert source_manifest is not None
    assert source_manifest.review_ranking_decision_keys.count(duplicate_key) == 2

    gate_report = evaluate_evidence_selection_expert_study_gate(
        bundle,
        review_ranking_thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=10,
            max_expected_calibration_error=0.05,
        ),
    )

    assert gate_report.passed is False
    assert any(
        "Duplicate review-ranking decision keys" in reason
        for reason in gate_report.review_ranking_gate.blocking_reasons
    )


def test_build_hashes_same_bytes_used_to_parse_source_exports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    adjudication_path = tmp_path / "adjudication-log.txt"
    selection_path.write_bytes(
        json.dumps({"selection_reviews": _selection_reviews()}).encode(),
    )
    ranking_path.write_bytes(json.dumps(_review_ranking()).encode())
    adjudication_path.write_bytes(b"reviewer-a accepted all calibration labels\n")
    original_read_bytes = Path.read_bytes
    read_counts: dict[Path, int] = {}

    def counting_read_bytes(path: Path) -> bytes:
        read_counts[path] = read_counts.get(path, 0) + 1
        return original_read_bytes(path)

    def fail_read_text(path: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError("source artifacts must be parsed from hashed bytes")

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    monkeypatch.setattr(Path, "read_text", fail_read_text)

    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id="read-once-shadow-study",
            study_evidence_kind="synthetic_fixture",
            selection_reviews_path=selection_path,
            review_ranking_path=ranking_path,
            adjudication_log_path=adjudication_path,
            source_system="artana-shadow-review",
            export_id="shadow-export-read-once",
            exported_at=datetime(2026, 7, 7, 7, 0, tzinfo=UTC),
            exporter_id="review-ops-a",
            redaction_statement="No PHI or raw patient text included.",
        ),
    )

    source_manifest = bundle.source_manifest
    assert source_manifest is not None
    assert read_counts == {
        selection_path: 1,
        ranking_path: 1,
        adjudication_path: 1,
    }


def test_build_rejects_selection_export_without_reviews(tmp_path: Path) -> None:
    selection_path = tmp_path / "bad-selection.json"
    ranking_path = tmp_path / "review-ranking.json"
    selection_path.write_text(json.dumps({"items": _selection_reviews()}))
    ranking_path.write_text(json.dumps(_review_ranking()))

    with pytest.raises(ValidationError):
        build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(
                study_id="bad-shadow-study",
                study_evidence_kind="real_shadow_review",
                selection_reviews_path=selection_path,
                review_ranking_path=ranking_path,
                source_system="artana-shadow-review",
                export_id="shadow-export-bad",
                exported_at=datetime(2026, 7, 7, 7, 0, tzinfo=UTC),
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
            ),
        )


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
    decisions = [
        {
            "source_kind": "proposal" if index % 2 == 0 else "review_item",
            "item_id": f"positive-{index}",
            "ranking_score": 1.0,
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
            "ranking_score": 0.0,
            "outcome": "negative",
            "reviewer_id": "reviewer-a",
            "goal": goals[index % len(goals)],
            "evidence_shape": evidence_shapes[index % len(evidence_shapes)],
        }
        for index in range(5)
    )
    return {
        "schema_version": "evidence_selection_review_ranking_calibration.v1",
        "study_id": "balanced-ranking",
        "adjudication_note": "No reviewer disagreements in this sample.",
        "decisions": decisions,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
