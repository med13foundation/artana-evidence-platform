"""Tests for reproducible evidence-selection expert-study bundle assembly."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from artana_evidence_api.evidence_selection.study_bundle import (
    EvidenceSelectionExpertStudyBundleRequest,
    build_evidence_selection_expert_study_bundle,
    validate_evidence_selection_expert_study_bundle_output_path,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyGateThresholds,
    ReviewRankingCalibrationGateThresholds,
    evaluate_evidence_selection_expert_study_gate,
)
from pydantic import ValidationError

from .evidence_selection_review_fixtures import adequate_explanation_assessment


def test_build_derives_source_manifest_identity_from_source_exports(
    tmp_path: Path,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    selection_path.write_text(json.dumps(_selection_review_export()))
    ranking_path.write_text(json.dumps(_review_ranking_export()))

    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id="shadow-study-2026-07-07",
            study_type="selection_and_review_ranking",
            study_evidence_kind="synthetic_fixture",
            selection_reviews_path=selection_path,
            review_ranking_path=ranking_path,
            description="Self-describing source export bundle.",
        ),
    )

    source_manifest = bundle.source_manifest
    assert source_manifest is not None
    assert source_manifest.source_system == "artana-shadow-review"
    assert source_manifest.export_id == "shadow-export-2026-07-07"
    assert source_manifest.exported_at == datetime(2026, 7, 7, 7, 0, tzinfo=UTC)
    assert source_manifest.exporter_id == "review-ops-a"
    assert source_manifest.redaction_statement == "No PHI or raw patient text included."


def test_bundle_output_rejects_hard_link_to_source_artifact(tmp_path: Path) -> None:
    source_path = tmp_path / "selection-review-export.json"
    output_path = tmp_path / "expert-study.json"
    source_path.write_text("source artifact\n")
    os.link(source_path, output_path)

    with pytest.raises(ValueError, match="must not overwrite source artifact"):
        validate_evidence_selection_expert_study_bundle_output_path(
            output_path=output_path,
            source_paths=(source_path,),
        )


def test_build_rejects_mismatched_source_export_identity(
    tmp_path: Path,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    ranking_export = _review_ranking_export()
    ranking_export["export_id"] = "different-export"
    selection_path.write_text(json.dumps(_selection_review_export()))
    ranking_path.write_text(json.dumps(ranking_export))

    with pytest.raises(ValueError, match="source export identity"):
        build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(
                study_id="mismatched-shadow-study",
                study_type="selection_and_review_ranking",
                study_evidence_kind="synthetic_fixture",
                selection_reviews_path=selection_path,
                review_ranking_path=ranking_path,
            ),
        )


@pytest.mark.parametrize("export_kind", ["selection", "ranking"])
def test_build_rejects_source_export_without_timezone(
    tmp_path: Path,
    export_kind: str,
) -> None:
    selection_export = _selection_review_export()
    ranking_export = _review_ranking_export()
    if export_kind == "selection":
        selection_export["exported_at"] = "2026-07-07T07:00:00"
    else:
        ranking_export["exported_at"] = "2026-07-07T07:00:00"
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    selection_path.write_text(json.dumps(selection_export))
    ranking_path.write_text(json.dumps(ranking_export))

    with pytest.raises(ValueError, match="timezone"):
        build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(
                study_id="naive-timestamp-shadow-study",
                study_type="selection_and_review_ranking",
                study_evidence_kind="synthetic_fixture",
                selection_reviews_path=selection_path,
                review_ranking_path=ranking_path,
            ),
        )


def test_build_rejects_noncanonical_source_export_timestamp_offset(
    tmp_path: Path,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    ranking_export = _review_ranking_export()
    ranking_export["exported_at"] = "2026-07-07T08:00:00+01:00"
    selection_path.write_text(json.dumps(_selection_review_export()))
    ranking_path.write_text(json.dumps(ranking_export))

    with pytest.raises(ValueError, match="canonical UTC"):
        build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(
                study_id="offset-timestamp-shadow-study",
                study_type="selection_and_review_ranking",
                study_evidence_kind="synthetic_fixture",
                selection_reviews_path=selection_path,
                review_ranking_path=ranking_path,
            ),
        )


@pytest.mark.parametrize(
    "alternate_exported_at",
    [
        "2026-07-07T07:00:00.000Z",
        "2026-07-07T07:00:00+00:00",
        "2026-07-07 07:00:00Z",
        "2026-07-07T07:00Z",
    ],
)
def test_build_rejects_alternate_utc_source_export_timestamp_spellings(
    tmp_path: Path,
    alternate_exported_at: str,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    ranking_export = _review_ranking_export()
    ranking_export["exported_at"] = alternate_exported_at
    selection_path.write_text(json.dumps(_selection_review_export()))
    ranking_path.write_text(json.dumps(ranking_export))

    with pytest.raises(ValueError, match="YYYY-MM-DDTHH:MM:SSZ"):
        build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(
                study_id="alternate-timestamp-shadow-study",
                study_type="selection_and_review_ranking",
                study_evidence_kind="synthetic_fixture",
                selection_reviews_path=selection_path,
                review_ranking_path=ranking_path,
            ),
        )


@pytest.mark.parametrize(
    "identity_field",
    ["source_system", "export_id", "exporter_id", "redaction_statement"],
)
def test_build_rejects_source_export_identity_field_with_outer_whitespace(
    tmp_path: Path,
    identity_field: str,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    selection_export = _selection_review_export()
    selection_export[identity_field] = f" {selection_export[identity_field]} "
    selection_path.write_text(json.dumps(selection_export))
    ranking_path.write_text(json.dumps(_review_ranking_export()))

    with pytest.raises(ValueError, match="leading or trailing whitespace"):
        build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(
                study_id="whitespace-identity-shadow-study",
                study_type="selection_and_review_ranking",
                study_evidence_kind="synthetic_fixture",
                selection_reviews_path=selection_path,
                review_ranking_path=ranking_path,
            ),
        )


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
def test_build_rejects_source_identity_override_mismatch(
    tmp_path: Path,
    override_field: str,
    override_value: str,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    selection_path.write_text(json.dumps(_selection_review_export()))
    ranking_path.write_text(json.dumps(_review_ranking_export()))
    request_kwargs: dict[str, object] = {
        "study_id": "override-mismatch-shadow-study",
        "study_type": "selection_and_review_ranking",
        "study_evidence_kind": "synthetic_fixture",
        "selection_reviews_path": selection_path,
        "review_ranking_path": ranking_path,
        **_source_export_identity(),
    }
    request_kwargs[override_field] = override_value

    with pytest.raises(ValueError, match="source export identity"):
        build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(**request_kwargs),
        )


def test_build_rejects_noncanonical_source_identity_override_timestamp(
    tmp_path: Path,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    selection_path.write_text(json.dumps(_selection_review_export()))
    ranking_path.write_text(json.dumps(_review_ranking_export()))

    with pytest.raises(ValueError, match="canonical UTC"):
        build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(
                study_id="override-noncanonical-shadow-study",
                study_type="selection_and_review_ranking",
                study_evidence_kind="synthetic_fixture",
                selection_reviews_path=selection_path,
                review_ranking_path=ranking_path,
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T08:00:00+01:00",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
            ),
        )


def test_builds_expert_study_bundle_with_computed_source_manifest(
    tmp_path: Path,
) -> None:
    selection_path = tmp_path / "selection-reviews.json"
    ranking_path = tmp_path / "review-ranking.json"
    adjudication_path = tmp_path / "adjudication-log.txt"
    selection_path.write_text(json.dumps(_selection_review_export()))
    ranking_path.write_text(json.dumps(_review_ranking_export()))
    adjudication_path.write_text("reviewer-a accepted all calibration labels\n")

    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id="shadow-study-2026-07-07",
            study_type="selection_and_review_ranking",
            study_evidence_kind="synthetic_fixture",
            selection_reviews_path=selection_path,
            review_ranking_path=ranking_path,
            adjudication_log_path=adjudication_path,
            description="Reproducible expert/shadow study bundle.",
        ),
    )

    source_manifest = bundle.source_manifest
    assert source_manifest is not None
    assert bundle.schema_version == "evidence_selection_expert_study.v2"
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
    selection_path.write_text(
        json.dumps(_selection_review_export(selection_reviews=selection_reviews)),
    )
    ranking_path.write_text(
        json.dumps(_review_ranking_export(study_id="duplicate-shadow-study")),
    )

    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id="duplicate-shadow-study",
            study_type="selection_and_review_ranking",
            study_evidence_kind="real_shadow_review",
            selection_reviews_path=selection_path,
            review_ranking_path=ranking_path,
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
    ranking = _review_ranking(study_id="duplicate-ranking-shadow-study")
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
    selection_path.write_text(json.dumps(_selection_review_export()))
    ranking_path.write_text(json.dumps(_review_ranking_export(review_ranking=ranking)))

    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id="duplicate-ranking-shadow-study",
            study_type="selection_and_review_ranking",
            study_evidence_kind="real_shadow_review",
            selection_reviews_path=selection_path,
            review_ranking_path=ranking_path,
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
        json.dumps(_selection_review_export()).encode(),
    )
    ranking_path.write_bytes(
        json.dumps(
            _review_ranking_export(study_id="read-once-shadow-study"),
        ).encode(),
    )
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
            study_type="selection_and_review_ranking",
            study_evidence_kind="synthetic_fixture",
            selection_reviews_path=selection_path,
            review_ranking_path=ranking_path,
            adjudication_log_path=adjudication_path,
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
    ranking_path.write_text(json.dumps(_review_ranking_export()))

    with pytest.raises(ValidationError):
        build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(
                study_id="bad-shadow-study",
                study_type="selection_and_review_ranking",
                study_evidence_kind="real_shadow_review",
                selection_reviews_path=selection_path,
                review_ranking_path=ranking_path,
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
            "explanation_assessment": (
                adequate_explanation_assessment().model_dump(mode="json")
            ),
            "high_severity_overclaim_findings": [],
        }
        for index, goal in enumerate(goals)
    ]


def _source_export_identity() -> dict[str, object]:
    return {
        "source_system": "artana-shadow-review",
        "export_id": "shadow-export-2026-07-07",
        "exported_at": "2026-07-07T07:00:00Z",
        "exporter_id": "review-ops-a",
        "redaction_statement": "No PHI or raw patient text included.",
    }


def _selection_review_export(
    *,
    selection_reviews: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "evidence_selection_review_export.v1",
        **_source_export_identity(),
        "selection_reviews": selection_reviews or _selection_reviews(),
    }


def _review_ranking_export(
    *,
    review_ranking: dict[str, object] | None = None,
    study_id: str = "shadow-study-2026-07-07",
) -> dict[str, object]:
    return {
        "schema_version": "evidence_selection_review_ranking_export.v1",
        **_source_export_identity(),
        "review_ranking": review_ranking or _review_ranking(study_id=study_id),
    }


def _review_ranking(
    *,
    study_id: str = "shadow-study-2026-07-07",
) -> dict[str, object]:
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
        "study_id": study_id,
        "adjudication_note": "No reviewer disagreements in this sample.",
        "decisions": decisions,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
