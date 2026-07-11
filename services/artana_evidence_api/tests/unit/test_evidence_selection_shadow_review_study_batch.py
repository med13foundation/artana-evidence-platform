"""Tests for completed shadow-review study batch orchestration."""

from __future__ import annotations

import copy
import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.shadow_review_completion import (
    machine_packet_sidecar_path,
)

from services.artana_evidence_api.tests.unit.test_evidence_selection_shadow_review_study_pipeline import (  # noqa: E501
    _completed_packet,
    _machine_packet_for_completed_packet,
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


def test_shadow_review_study_batch_blocks_tiny_passing_suite(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    packet_path = _write_packet(tmp_path, "completed-packet.json", _completed_packet())
    output_dir = tmp_path / "batch-output"

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
                {
                    "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                    "batch_id": "tiny-batch-2026-07-07",
                    "entries": [
                        _manifest_entry(
                            entry_id="single-study",
                            packet_path=packet_path,
                            output_subdir="single-study",
                            export_id="shadow-export-single",
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

    assert result.entry_count == 1
    assert result.passed_entry_count == 1
    assert result.failed_entry_count == 0
    assert result.passed is False
    assert result.suite_gate["passed"] is False
    assert any(
        "At least 3 batch entries" in reason
        for reason in result.suite_gate["blocking_reasons"]
    )
    report = result.to_json()
    assert report["passed"] is False
    assert report["suite_gate"]["passed"] is False
    assert report["suite_gate"]["summary"]["entry_count"] == 1


def test_shadow_review_study_batch_passes_diverse_suite_gate(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    output_dir = tmp_path / "batch-output"
    first_packet_path = _write_packet(
        tmp_path,
        "first-packet.json",
        _completed_packet_for_batch(
            study_id="shadow-study-one",
            source_run_id="11111111-1111-4111-8111-111111111111",
            goal="Assess BRAF targeted therapy evidence.",
            first_shape="variant_drug_response",
            second_shape="background_context",
            review_ranking_decision_count=4,
        ),
    )
    second_packet_path = _write_packet(
        tmp_path,
        "second-packet.json",
        _completed_packet_for_batch(
            study_id="shadow-study-two",
            source_run_id="22222222-2222-4222-8222-222222222222",
            goal="Assess EGFR resistance evidence.",
            first_shape="drug_resistance",
            second_shape="mechanistic_context",
            review_ranking_decision_count=3,
            reverse_source_outcomes=True,
        ),
    )
    third_packet_path = _write_packet(
        tmp_path,
        "third-packet.json",
        _completed_packet_for_batch(
            study_id="shadow-study-three",
            source_run_id="33333333-3333-4333-8333-333333333333",
            goal="Assess BRCA1 pathogenicity evidence.",
            first_shape="gene_disease_association",
            second_shape="variant_pathogenicity",
            review_ranking_decision_count=3,
        ),
    )

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
                {
                    "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                    "batch_id": "diverse-batch-2026-07-07",
                    "entries": [
                        _manifest_entry(
                            entry_id="study-one",
                            packet_path=first_packet_path,
                            output_subdir="study-one",
                            export_id="shadow-export-one",
                        ),
                        _manifest_entry(
                            entry_id="study-two",
                            packet_path=second_packet_path,
                            output_subdir="study-two",
                            export_id="shadow-export-two",
                        ),
                        _manifest_entry(
                            entry_id="study-three",
                            packet_path=third_packet_path,
                            output_subdir="study-three",
                            export_id="shadow-export-three",
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

    assert result.passed is True
    assert result.suite_gate["passed"] is True
    assert result.suite_gate["summary"]["distinct_selection_goal_count"] == 3
    assert result.suite_gate["summary"]["distinct_review_ranking_goal_count"] == 3
    assert result.suite_gate["summary"]["distinct_evidence_shape_count"] == 6
    assert result.suite_gate["summary"]["distinct_source_run_id_count"] == 3
    assert result.suite_gate["summary"]["distinct_study_id_count"] == 3
    assert result.suite_gate["summary"]["total_review_ranking_decision_count"] == 10


def test_shadow_review_study_batch_default_thresholds_aggregate_single_run_packets(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    packet_specs = (
        (
            "one",
            "11111111-1111-4111-8111-111111111111",
            "Assess BRAF targeted therapy evidence.",
            "variant_drug_response",
            "background_context",
            4,
        ),
        (
            "two",
            "22222222-2222-4222-8222-222222222222",
            "Assess EGFR resistance evidence.",
            "drug_resistance",
            "mechanistic_context",
            3,
        ),
        (
            "three",
            "33333333-3333-4333-8333-333333333333",
            "Assess BRCA1 pathogenicity evidence.",
            "gene_disease_association",
            "variant_pathogenicity",
            3,
        ),
    )
    packet_paths = tuple(
        _write_packet(
            tmp_path,
            f"{label}.json",
            _completed_packet_for_batch(
                study_id=f"shadow-study-{label}",
                source_run_id=source_run_id,
                goal=goal,
                first_shape=first_shape,
                second_shape=second_shape,
                review_ranking_decision_count=decision_count,
                reverse_source_outcomes=label == "two",
            ),
        )
        for (
            label,
            source_run_id,
            goal,
            first_shape,
            second_shape,
            decision_count,
        ) in packet_specs
    )
    manifest = batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
        {
            "schema_version": "evidence_selection_shadow_review_study_batch.v1",
            "batch_id": "default-threshold-batch-2026-07-07",
            "entries": [
                _manifest_entry(
                    entry_id=f"study-{index}",
                    packet_path=packet_path,
                    output_subdir=f"study-{index}",
                    export_id=f"shadow-export-{index}",
                )
                for index, packet_path in enumerate(packet_paths, start=1)
            ],
        },
    )

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=manifest,
            output_dir=tmp_path / "batch-output",
        ),
    )

    assert result.passed is True
    assert result.passed_entry_count == 3
    assert result.suite_gate["summary"]["total_selection_review_count"] == 3
    assert result.suite_gate["summary"]["total_review_ranking_decision_count"] == 10


def test_shadow_review_study_batch_requires_per_source_ranking_outcomes(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    packet_specs = (
        (
            "one",
            "11111111-1111-4111-8111-111111111111",
            "Assess BRAF targeted therapy evidence.",
            "variant_drug_response",
            "background_context",
        ),
        (
            "two",
            "22222222-2222-4222-8222-222222222222",
            "Assess EGFR resistance evidence.",
            "drug_resistance",
            "mechanistic_context",
        ),
        (
            "three",
            "33333333-3333-4333-8333-333333333333",
            "Assess BRCA1 pathogenicity evidence.",
            "gene_disease_association",
            "variant_pathogenicity",
        ),
    )
    packet_paths = tuple(
        _write_packet(
            tmp_path,
            f"{label}.json",
            _completed_packet_for_batch(
                study_id=f"shadow-study-{label}",
                source_run_id=source_run_id,
                goal=goal,
                first_shape=first_shape,
                second_shape=second_shape,
                review_ranking_decision_count=4,
            ),
        )
        for label, source_run_id, goal, first_shape, second_shape in packet_specs
    )
    manifest = batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
        {
            "schema_version": "evidence_selection_shadow_review_study_batch.v1",
            "batch_id": "one-sided-source-outcomes-batch-2026-07-10",
            "entries": [
                _manifest_entry(
                    entry_id=f"study-{index}",
                    packet_path=packet_path,
                    output_subdir=f"study-{index}",
                    export_id=f"shadow-export-{index}",
                )
                for index, packet_path in enumerate(packet_paths, start=1)
            ],
        },
    )

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=manifest,
            output_dir=tmp_path / "batch-output",
        ),
    )

    assert result.passed_entry_count == 3
    assert result.passed is False
    assert result.suite_gate["summary"]["review_ranking_source_outcomes"] == {
        "proposal": ["positive"],
        "review_item": ["negative"],
    }
    assert any(
        "negative reviewer outcome is required for source kind proposal"
        in reason
        for reason in result.suite_gate["blocking_reasons"]
    )
    assert any(
        "positive reviewer outcome is required for source kind review_item"
        in reason
        for reason in result.suite_gate["blocking_reasons"]
    )


def test_shadow_review_study_batch_blocks_thin_total_ranking_sample(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    output_dir = tmp_path / "batch-output"
    packet_paths = [
        _write_packet(
            tmp_path,
            "first-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-one",
                source_run_id="11111111-1111-4111-8111-111111111111",
                goal="Assess BRAF targeted therapy evidence.",
                first_shape="variant_drug_response",
                second_shape="background_context",
            ),
        ),
        _write_packet(
            tmp_path,
            "second-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-two",
                source_run_id="22222222-2222-4222-8222-222222222222",
                goal="Assess EGFR resistance evidence.",
                first_shape="drug_resistance",
                second_shape="mechanistic_context",
            ),
        ),
        _write_packet(
            tmp_path,
            "third-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-three",
                source_run_id="33333333-3333-4333-8333-333333333333",
                goal="Assess BRCA1 pathogenicity evidence.",
                first_shape="gene_disease_association",
                second_shape="variant_pathogenicity",
            ),
        ),
    ]

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
                {
                    "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                    "batch_id": "thin-total-sample-batch-2026-07-07",
                    "entries": [
                        _manifest_entry(
                            entry_id=f"study-{index}",
                            packet_path=packet_path,
                            output_subdir=f"study-{index}",
                            export_id=f"shadow-export-{index}",
                        )
                        for index, packet_path in enumerate(packet_paths, start=1)
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

    assert result.passed is False
    assert result.suite_gate["summary"]["total_review_ranking_decision_count"] == 6
    assert any(
        "review-ranking decisions" in reason
        for reason in result.suite_gate["blocking_reasons"]
    )


def test_shadow_review_study_batch_blocks_cloned_source_runs(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    output_dir = tmp_path / "batch-output"
    packet_paths = [
        _write_packet(
            tmp_path,
            "first-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-one",
                goal="Assess BRAF targeted therapy evidence.",
                first_shape="variant_drug_response",
                second_shape="background_context",
            ),
        ),
        _write_packet(
            tmp_path,
            "second-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-two",
                goal="Assess EGFR resistance evidence.",
                first_shape="drug_resistance",
                second_shape="mechanistic_context",
            ),
        ),
        _write_packet(
            tmp_path,
            "third-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-three",
                goal="Assess BRCA1 pathogenicity evidence.",
                first_shape="gene_disease_association",
                second_shape="variant_pathogenicity",
            ),
        ),
    ]

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
                {
                    "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                    "batch_id": "cloned-source-run-batch-2026-07-07",
                    "entries": [
                        _manifest_entry(
                            entry_id=f"study-{index}",
                            packet_path=packet_path,
                            output_subdir=f"study-{index}",
                            export_id=f"shadow-export-{index}",
                        )
                        for index, packet_path in enumerate(packet_paths, start=1)
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

    assert result.passed is False
    assert result.suite_gate["summary"]["distinct_source_run_id_count"] == 1
    assert any(
        "distinct source run IDs" in reason
        for reason in result.suite_gate["blocking_reasons"]
    )


def test_shadow_review_study_batch_uses_only_passed_entries_for_suite_diversity(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    output_dir = tmp_path / "batch-output"
    first_packet_path = _write_packet(
        tmp_path,
        "first-packet.json",
        _completed_packet_for_batch(
            study_id="shadow-study-one",
            source_run_id="11111111-1111-4111-8111-111111111111",
            goal="Assess BRAF targeted therapy evidence.",
            first_shape="same_shape",
            second_shape="same_context",
        ),
    )
    second_packet_path = _write_packet(
        tmp_path,
        "second-packet.json",
        _completed_packet_for_batch(
            study_id="shadow-study-two",
            source_run_id="22222222-2222-4222-8222-222222222222",
            goal="Assess BRAF targeted therapy evidence.",
            first_shape="same_shape",
            second_shape="same_context",
        ),
    )
    failed_packet_path = _write_packet(
        tmp_path,
        "failed-packet.json",
        _low_quality_packet_for_batch(
            study_id="shadow-study-three",
            source_run_id="33333333-3333-4333-8333-333333333333",
            goal="Assess BRCA1 pathogenicity evidence.",
            first_shape="gene_disease_association",
            second_shape="variant_pathogenicity",
        ),
    )

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
                {
                    "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                    "batch_id": "failed-diversity-batch-2026-07-07",
                    "entries": [
                        _manifest_entry(
                            entry_id="study-one",
                            packet_path=first_packet_path,
                            output_subdir="study-one",
                            export_id="shadow-export-one",
                        ),
                        _manifest_entry(
                            entry_id="study-two",
                            packet_path=second_packet_path,
                            output_subdir="study-two",
                            export_id="shadow-export-two",
                        ),
                        _manifest_entry(
                            entry_id="study-three",
                            packet_path=failed_packet_path,
                            output_subdir="study-three",
                            export_id="shadow-export-three",
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
            suite_thresholds=batch.EvidenceSelectionShadowReviewStudyBatchSuiteThresholds(
                min_entry_count=3,
                min_passed_entry_count=2,
                max_failed_entry_count=1,
                min_passed_entry_rate=0.5,
                min_distinct_selection_goals=2,
                min_distinct_review_ranking_goals=2,
                min_distinct_evidence_shapes=3,
            ),
        ),
    )

    assert result.passed is False
    assert result.suite_gate["summary"]["distinct_selection_goal_count"] == 1
    assert result.suite_gate["summary"]["distinct_review_ranking_goal_count"] == 1
    assert result.suite_gate["summary"]["distinct_evidence_shape_count"] == 2
    assert any(
        "distinct selection goals" in reason
        for reason in result.suite_gate["blocking_reasons"]
    )


def test_shadow_review_study_batch_normalizes_punctuation_in_diversity_labels(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    output_dir = tmp_path / "batch-output"
    packet_paths = [
        _write_packet(
            tmp_path,
            "first-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-one",
                source_run_id="11111111-1111-4111-8111-111111111111",
                goal="Assess BRAF targeted therapy evidence.",
                first_shape="drug_resistance",
                second_shape="background_context",
            ),
        ),
        _write_packet(
            tmp_path,
            "second-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-two",
                source_run_id="22222222-2222-4222-8222-222222222222",
                goal="Assess EGFR resistance evidence.",
                first_shape="drug-resistance",
                second_shape="background context",
            ),
        ),
        _write_packet(
            tmp_path,
            "third-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-three",
                source_run_id="33333333-3333-4333-8333-333333333333",
                goal="Assess BRCA1 pathogenicity evidence.",
                first_shape="drug resistance",
                second_shape="background.context",
            ),
        ),
    ]

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
                {
                    "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                    "batch_id": "spoofed-diversity-batch-2026-07-07",
                    "entries": [
                        _manifest_entry(
                            entry_id=f"study-{index}",
                            packet_path=packet_path,
                            output_subdir=f"study-{index}",
                            export_id=f"shadow-export-{index}",
                        )
                        for index, packet_path in enumerate(packet_paths, start=1)
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

    assert result.passed is False
    assert result.suite_gate["summary"]["distinct_evidence_shape_count"] == 2
    assert any(
        "distinct evidence shapes" in reason
        for reason in result.suite_gate["blocking_reasons"]
    )


def test_shadow_review_study_batch_compares_pass_rate_without_rounding(
    tmp_path: Path,
) -> None:
    batch = _batch_module()
    output_dir = tmp_path / "batch-output"
    packet_paths = [
        _write_packet(
            tmp_path,
            "first-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-one",
                source_run_id="11111111-1111-4111-8111-111111111111",
                goal="Assess BRAF targeted therapy evidence.",
                first_shape="variant_drug_response",
                second_shape="background_context",
            ),
        ),
        _write_packet(
            tmp_path,
            "second-packet.json",
            _completed_packet_for_batch(
                study_id="shadow-study-two",
                source_run_id="22222222-2222-4222-8222-222222222222",
                goal="Assess EGFR resistance evidence.",
                first_shape="drug_resistance",
                second_shape="mechanistic_context",
            ),
        ),
        _write_packet(
            tmp_path,
            "failed-packet.json",
            _low_quality_packet_for_batch(
                study_id="shadow-study-three",
                source_run_id="33333333-3333-4333-8333-333333333333",
                goal="Assess BRCA1 pathogenicity evidence.",
                first_shape="gene_disease_association",
                second_shape="variant_pathogenicity",
            ),
        ),
    ]

    result = batch.build_evidence_selection_shadow_review_study_batch(
        batch.EvidenceSelectionShadowReviewStudyBatchRequest(
            manifest=batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
                {
                    "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                    "batch_id": "pass-rate-batch-2026-07-07",
                    "entries": [
                        _manifest_entry(
                            entry_id=f"study-{index}",
                            packet_path=packet_path,
                            output_subdir=f"study-{index}",
                            export_id=f"shadow-export-{index}",
                        )
                        for index, packet_path in enumerate(packet_paths, start=1)
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
            suite_thresholds=batch.EvidenceSelectionShadowReviewStudyBatchSuiteThresholds(
                min_entry_count=3,
                min_passed_entry_count=2,
                max_failed_entry_count=1,
                min_passed_entry_rate=0.6667,
                min_distinct_selection_goals=2,
                min_distinct_review_ranking_goals=2,
                min_distinct_evidence_shapes=3,
            ),
        ),
    )

    assert result.passed is False
    assert result.suite_gate["summary"]["passed_entry_rate"] == 0.6667
    assert any(
        "passed-entry rate" in reason
        for reason in result.suite_gate["blocking_reasons"]
    )


def test_shadow_review_study_batch_quality_gate_uses_unrounded_metrics() -> None:
    batch = _batch_module()
    metrics = batch._BatchQualityMetrics(  # noqa: SLF001
        suite_mean_precision=0.79996,
        suite_mean_recall=0.79996,
        suite_mean_explanation_quality=2.99996,
        max_review_ranking_expected_calibration_error=0.05,
    )

    reasons = batch._batch_suite_quality_blocking_reasons(  # noqa: SLF001
        raw_quality_metrics=metrics,
        thresholds=batch.EvidenceSelectionShadowReviewStudyBatchSuiteThresholds(),
    )

    assert any("suite mean precision" in reason for reason in reasons)
    assert any("suite mean recall" in reason for reason in reasons)
    assert any("suite mean explanation quality" in reason for reason in reasons)


def test_shadow_review_study_batch_rolls_back_published_entries_after_later_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = _batch_module()
    first_packet_path = _write_packet(
        tmp_path,
        "first-packet.json",
        _completed_packet(),
    )
    second_packet_path = _write_packet(
        tmp_path,
        "second-packet.json",
        _completed_packet(),
    )
    output_dir = tmp_path / "batch-output"
    manifest = batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
        {
            "schema_version": "evidence_selection_shadow_review_study_batch.v1",
            "batch_id": "rollback-batch-2026-07-10",
            "entries": [
                _manifest_entry(
                    entry_id="first",
                    packet_path=first_packet_path,
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
    request = batch.EvidenceSelectionShadowReviewStudyBatchRequest(
        manifest=manifest,
        output_dir=output_dir,
        thresholds=batch.EvidenceSelectionShadowReviewStudyBatchThresholds(
            min_selection_review_count=1,
            min_distinct_selection_goals=1,
            min_review_ranking_sample_count=2,
            min_distinct_ranking_goals=1,
            min_distinct_evidence_shapes=2,
        ),
    )
    original_gate_report = batch.build_evidence_selection_shadow_review_study_gate_report
    call_count = 0

    def _fail_second_gate_report(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("simulated second gate failure")
        return original_gate_report(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(
            batch,
            "build_evidence_selection_shadow_review_study_gate_report",
            _fail_second_gate_report,
        )
        with pytest.raises(RuntimeError, match="simulated second gate failure"):
            batch.build_evidence_selection_shadow_review_study_batch(request)

    assert not output_dir.exists()

    retry_result = batch.build_evidence_selection_shadow_review_study_batch(request)

    assert retry_result.entry_count == 2
    assert (output_dir / "first").is_dir()
    assert (output_dir / "second").is_dir()


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


def test_shadow_review_study_batch_rejects_nested_output_subdirs() -> None:
    batch = _batch_module()

    with pytest.raises(ValueError, match="output_subdir values must not be nested"):
        batch.EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": "nested-output-batch",
                "entries": [
                    _manifest_entry(
                        entry_id="child",
                        packet_path=Path("child.json"),
                        output_subdir="study/nested",
                        export_id="child-export",
                    ),
                    _manifest_entry(
                        entry_id="parent",
                        packet_path=Path("parent.json"),
                        output_subdir="study",
                        export_id="parent-export",
                    ),
                ],
            },
        )


@pytest.mark.parametrize(
    "threshold_name",
    [
        "min_passed_entry_rate",
        "min_suite_mean_precision",
        "min_suite_mean_recall",
        "min_suite_mean_explanation_quality",
        "max_suite_expected_calibration_error",
    ],
)
@pytest.mark.parametrize("non_finite_value", [float("nan"), float("inf"), float("-inf")])
def test_shadow_review_study_batch_rejects_non_finite_suite_thresholds(
    threshold_name: str,
    non_finite_value: float,
) -> None:
    batch = _batch_module()
    thresholds = replace(
        batch.EvidenceSelectionShadowReviewStudyBatchSuiteThresholds(),
        **{threshold_name: non_finite_value},
    )

    with pytest.raises(ValueError, match=f"{threshold_name} must be finite"):
        batch.build_evidence_selection_shadow_review_study_batch_suite_gate(
            entries=(),
            thresholds=thresholds,
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
    machine_packet = _machine_packet_for_completed_packet(packet)
    packet["machine_packet_sha256"] = machine_packet["machine_packet_sha256"]
    packet["machine_packet_signature"] = machine_packet["machine_packet_signature"]
    packet_path.write_text(json.dumps(packet))
    machine_packet_sidecar_path(packet_path).write_text(json.dumps(machine_packet))
    return packet_path


def _low_quality_packet() -> dict[str, object]:
    packet = copy.deepcopy(_completed_packet())
    selection_forms = packet["selection_review_forms"]
    assert isinstance(selection_forms, list)
    first_form = selection_forms[0]
    assert isinstance(first_form, dict)
    first_form["explanation_quality_score"] = 2
    return packet


def _low_quality_packet_for_batch(
    *,
    study_id: str,
    source_run_id: str | None = None,
    goal: str,
    first_shape: str,
    second_shape: str,
) -> dict[str, object]:
    packet = _completed_packet_for_batch(
        study_id=study_id,
        source_run_id=source_run_id,
        goal=goal,
        first_shape=first_shape,
        second_shape=second_shape,
    )
    selection_forms = packet["selection_review_forms"]
    assert isinstance(selection_forms, list)
    first_form = selection_forms[0]
    assert isinstance(first_form, dict)
    first_form["explanation_quality_score"] = 2
    return packet


def _completed_packet_for_batch(
    *,
    study_id: str,
    source_run_id: str | None = None,
    goal: str,
    first_shape: str,
    second_shape: str,
    review_ranking_decision_count: int = 2,
    reverse_source_outcomes: bool = False,
) -> dict[str, object]:
    packet = copy.deepcopy(_completed_packet())
    packet["study_id"] = study_id
    if source_run_id is not None:
        packet["source_run_id"] = source_run_id
    packet["goal"] = goal
    selection_forms = packet["selection_review_forms"]
    assert isinstance(selection_forms, list)
    for form in selection_forms:
        assert isinstance(form, dict)
        if source_run_id is not None:
            form["run_id"] = source_run_id
        form["goal"] = goal
    ranking_forms = packet["review_ranking_forms"]
    assert isinstance(ranking_forms, list)
    shapes = (first_shape, second_shape)
    while len(ranking_forms) < review_ranking_decision_count:
        index = len(ranking_forms)
        positive = index % 2 == 0
        ranking_forms.append(
            {
                "source_kind": "proposal" if positive else "review_item",
                "item_id": f"ranking-{study_id}-{index}",
                "ranking_score": 1.0 if positive else 0.0,
                "outcome": "positive" if positive else "negative",
                "reviewer_id": "reviewer-a",
                "goal": goal,
                "evidence_shape": shapes[index % len(shapes)],
            },
        )
    for index, form in enumerate(ranking_forms):
        assert isinstance(form, dict)
        form["goal"] = goal
        form["evidence_shape"] = shapes[index % len(shapes)]
        if reverse_source_outcomes:
            source_kind = "proposal" if index % 2 == 0 else "review_item"
            positive = source_kind == "review_item"
            form["source_kind"] = source_kind
            form["ranking_score"] = 1.0 if positive else 0.0
            form["outcome"] = "positive" if positive else "negative"
    return packet
