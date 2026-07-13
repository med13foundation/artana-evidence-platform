"""Tests for completed shadow-review study artifact assembly."""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.shadow_review_integrity import (
    sign_machine_packet_digest,
)
from artana_evidence_api.evidence_selection.shadow_review_packet import (
    EvidenceSelectionShadowReviewPacket,
    machine_packet_digest,
)

from .evidence_selection_review_fixtures import adequate_explanation_assessment

_RUN_ID = "00000000-0000-0000-0000-000000000049"
_GOAL = "Review BRAF V600E treatment-response evidence."


def test_shadow_review_study_pipeline_builds_bundle_ready_artifacts(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline_module()
    output_dir = tmp_path / "shadow-review-study"

    result = pipeline.build_evidence_selection_shadow_review_study_artifacts(
        pipeline.EvidenceSelectionShadowReviewStudyArtifactRequest(
            machine_packet=_machine_packet(),
            packet=_completed_packet(),
            output_dir=output_dir,
            adjudication_note="Reviewer A completed all labels.",
            source_system="artana-shadow-review",
            export_id="shadow-export-2026-07-07",
            exported_at="2026-07-07T14:00:00Z",
            exporter_id="review-ops-a",
            redaction_statement="No PHI or raw patient text included.",
            study_evidence_kind="real_shadow_review",
            description="Completed shadow-review packet pipeline fixture.",
        ),
    )

    assert result.selection_review_count == 1
    assert result.review_ranking_decision_count == 2
    assert result.source_artifact_count == 2
    assert result.selection_reviews_path == output_dir / "selection-review-labels.json"
    assert result.review_ranking_path == output_dir / "review-ranking-study.json"
    assert result.selection_export_path == output_dir / "selection-review-export.json"
    assert (
        result.review_ranking_export_path == output_dir / "review-ranking-export.json"
    )
    assert result.bundle_path == output_dir / "evidence-selection-expert-study.json"

    selection_input = json.loads(result.selection_reviews_path.read_text())
    ranking_input = json.loads(result.review_ranking_path.read_text())
    selection_export = json.loads(result.selection_export_path.read_text())
    ranking_export = json.loads(result.review_ranking_export_path.read_text())
    bundle = json.loads(result.bundle_path.read_text())

    assert selection_input["selection_reviews"][0]["reviewer_id"] == "reviewer-a"
    assert ranking_input["study_id"] == "shadow-study-2026-07-07"
    assert selection_export["schema_version"] == "evidence_selection_review_export.v2"
    assert ranking_export["schema_version"] == (
        "evidence_selection_review_ranking_export.v1"
    )
    assert bundle["schema_version"] == "evidence_selection_expert_study.v2"
    assert bundle["study_type"] == "selection_and_review_ranking"
    assert bundle["study_evidence_kind"] == "real_shadow_review"
    assert bundle["source_manifest"]["export_id"] == "shadow-export-2026-07-07"
    source_artifact_uris = {
        artifact["artifact_id"]: artifact["uri"]
        for artifact in bundle["source_manifest"]["source_artifacts"]
    }
    assert source_artifact_uris == {
        "selection-review-export": str(result.selection_export_path),
        "review-ranking-export": str(result.review_ranking_export_path),
    }
    assert all(Path(uri).exists() for uri in source_artifact_uris.values())


def test_selection_only_pipeline_does_not_fabricate_ranking_artifacts(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline_module()
    completed_packet = _selection_only_completed_packet()
    machine_packet = _machine_packet_for_completed_packet(completed_packet)
    completed_packet["machine_packet_sha256"] = machine_packet["machine_packet_sha256"]
    completed_packet["machine_packet_signature"] = machine_packet[
        "machine_packet_signature"
    ]
    output_dir = tmp_path / "selection-only-study"

    result = pipeline.build_evidence_selection_shadow_review_study_artifacts(
        pipeline.EvidenceSelectionShadowReviewStudyArtifactRequest(
            machine_packet=machine_packet,
            packet=completed_packet,
            output_dir=output_dir,
            adjudication_note=None,
            source_system="artana-shadow-review",
            export_id="selection-only-export-2026-07-07",
            exported_at="2026-07-07T14:00:00Z",
            exporter_id="review-ops-a",
            redaction_statement="No PHI or raw patient text included.",
            study_evidence_kind="real_shadow_review",
        ),
    )

    bundle = json.loads(result.bundle_path.read_text())
    assert result.review_ranking_path is None
    assert result.review_ranking_export_path is None
    assert result.review_ranking_decision_count == 0
    assert result.source_artifact_count == 1
    assert not (output_dir / "review-ranking-study.json").exists()
    assert not (output_dir / "review-ranking-export.json").exists()
    assert bundle["study_type"] == "selection_relevance"
    assert "review_ranking" not in bundle
    assert [
        artifact["artifact_kind"]
        for artifact in bundle["source_manifest"]["source_artifacts"]
    ] == ["selection_review_export"]


def test_shadow_review_study_pipeline_rejects_file_output_dir(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline_module()
    output_dir = tmp_path / "shadow-review-study.json"
    output_dir.write_text("not a directory\n")

    with pytest.raises(ValueError, match="Output directory must be a directory"):
        pipeline.build_evidence_selection_shadow_review_study_artifacts(
            pipeline.EvidenceSelectionShadowReviewStudyArtifactRequest(
                machine_packet=_machine_packet(),
                packet=_completed_packet(),
                output_dir=output_dir,
                adjudication_note="Reviewer A completed all labels.",
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T14:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
                study_evidence_kind="real_shadow_review",
            ),
        )

    assert output_dir.read_text() == "not a directory\n"


def test_shadow_review_study_pipeline_rejects_packet_output_collision(
    tmp_path: Path,
) -> None:
    pipeline = _pipeline_module()
    output_dir = tmp_path / "shadow-review-study"
    output_dir.mkdir()
    packet_path = output_dir / "selection-review-labels.json"
    packet_path.write_text(json.dumps(_completed_packet()))
    original_packet_text = packet_path.read_text()

    with pytest.raises(ValueError, match="must not overwrite source packet"):
        pipeline.build_evidence_selection_shadow_review_study_artifacts(
            pipeline.EvidenceSelectionShadowReviewStudyArtifactRequest(
                machine_packet=_machine_packet(),
                packet=_completed_packet(),
                packet_path=packet_path,
                output_dir=output_dir,
                adjudication_note="Reviewer A completed all labels.",
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T14:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
                study_evidence_kind="real_shadow_review",
            ),
        )

    assert packet_path.read_text() == original_packet_text


def test_shadow_review_study_pipeline_removes_staged_artifacts_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = _pipeline_module()
    output_dir = tmp_path / "shadow-review-study"

    def fail_source_export(*_args: object, **_kwargs: object) -> object:
        raise OSError("injected source-export failure")

    monkeypatch.setattr(
        pipeline,
        "write_evidence_selection_source_exports",
        fail_source_export,
    )

    with pytest.raises(OSError, match="injected source-export failure"):
        pipeline.build_evidence_selection_shadow_review_study_artifacts(
            pipeline.EvidenceSelectionShadowReviewStudyArtifactRequest(
                machine_packet=_machine_packet(),
                packet=_completed_packet(),
                output_dir=output_dir,
                adjudication_note="Reviewer A completed all labels.",
                source_system="artana-shadow-review",
                export_id="shadow-export-2026-07-07",
                exported_at="2026-07-07T14:00:00Z",
                exporter_id="review-ops-a",
                redaction_statement="No PHI or raw patient text included.",
                study_evidence_kind="real_shadow_review",
            ),
        )

    assert not output_dir.exists()
    assert list(tmp_path.glob(".shadow-review-study.staging-*")) == []


def _pipeline_module() -> object:
    try:
        return importlib.import_module(
            "artana_evidence_api.evidence_selection.shadow_review_study_pipeline",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review study pipeline module is missing: {exc}")


def _completed_packet() -> dict[str, object]:
    packet = _completed_packet_payload()
    machine_packet = _machine_packet()
    packet["machine_packet_sha256"] = machine_packet["machine_packet_sha256"]
    packet["machine_packet_signature"] = machine_packet["machine_packet_signature"]
    return packet


def _machine_packet() -> dict[str, object]:
    return _machine_packet_for_completed_packet(_completed_packet_payload())


def _selection_only_completed_packet() -> dict[str, object]:
    packet = _completed_packet_payload()
    packet["study_type"] = "selection_relevance"
    packet["completion_required_fields"] = packet["completion_required_fields"][:4]
    packet["review_ranking_forms"] = []
    return packet


def _machine_packet_for_completed_packet(
    completed_packet: dict[str, object],
) -> dict[str, object]:
    packet = deepcopy(completed_packet)
    selection_form = packet["selection_review_forms"][0]
    selection_form["reviewer_id"] = None
    selection_form["human_selected_record_ids"] = []
    selection_form["duplicate_suggestion_ids"] = []
    selection_form["explanation_assessment"] = None
    selection_form["high_severity_overclaim_findings"] = None
    selection_form["reviewer_notes"] = None
    for ranking_form in packet["review_ranking_forms"]:
        ranking_form["outcome"] = None
        ranking_form["reviewer_id"] = None
    packet.pop("machine_packet_sha256", None)
    packet.pop("machine_packet_signature", None)
    model = EvidenceSelectionShadowReviewPacket.model_validate(packet)
    digest = machine_packet_digest(model)
    packet["machine_packet_sha256"] = digest
    packet["machine_packet_signature"] = sign_machine_packet_digest(digest)
    return packet


def _completed_packet_payload() -> dict[str, object]:
    return {
        "schema_version": "evidence_selection_shadow_review_packet.v2",
        "study_id": "shadow-study-2026-07-07",
        "study_type": "selection_and_review_ranking",
        "source_run_id": _RUN_ID,
        "goal": _GOAL,
        "production_readiness_claim": False,
        "completion_status": "requires_human_labels",
        "completion_required_fields": [
            "selection_review_forms[].reviewer_id",
            "selection_review_forms[].human_selected_record_ids",
            "selection_review_forms[].explanation_assessment",
            "selection_review_forms[].high_severity_overclaim_findings",
            "review_ranking_forms[].reviewer_id",
            "review_ranking_forms[].outcome",
        ],
        "candidate_records": [
            _candidate_record("pubmed:search-1:0"),
            _candidate_record("pubmed:search-1:1"),
        ],
        "selection_review_forms": [
            {
                "run_id": _RUN_ID,
                "goal": _GOAL,
                "reviewer_id": "reviewer-a",
                "harness_selected_record_ids": ["pubmed:search-1:0"],
                "harness_skipped_record_ids": ["pubmed:search-1:1"],
                "harness_deferred_record_ids": [],
                "human_selected_record_ids": ["pubmed:search-1:0"],
                "duplicate_suggestion_ids": [],
                "explanation_assessment": (
                    adequate_explanation_assessment().model_dump(mode="json")
                ),
                "high_severity_overclaim_findings": [],
                "reviewer_notes": "Specific relation with direct support.",
            },
        ],
        "review_ranking_forms": [
            {
                "source_kind": "proposal",
                "item_id": "proposal-1",
                "ranking_score": 1.0,
                "outcome": "positive",
                "reviewer_id": "reviewer-a",
                "goal": _GOAL,
                "evidence_shape": "variant_drug_response",
            },
            {
                "source_kind": "review_item",
                "item_id": "review-item-1",
                "ranking_score": 0.0,
                "outcome": "negative",
                "reviewer_id": "reviewer-a",
                "goal": _GOAL,
                "evidence_shape": "background_context",
            },
        ],
    }


def _candidate_record(record_id: str) -> dict[str, object]:
    source_key, search_id, record_index_text = record_id.split(":")
    return {
        "record_id": record_id,
        "source_key": source_key,
        "source_family": "literature",
        "search_id": search_id,
        "decision": "selected",
        "relevance_label": "strong_fit",
        "reason": "Candidate evidence fixture.",
        "record_index": int(record_index_text),
        "record_hash": f"hash-{record_index_text}",
        "title": f"Candidate {record_index_text}",
        "score": 0.8,
        "matched_terms": ["BRAF"],
        "excluded_terms": [],
        "caveats": [],
    }
