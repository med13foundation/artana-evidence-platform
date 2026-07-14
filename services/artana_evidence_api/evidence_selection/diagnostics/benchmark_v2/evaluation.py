"""Derive benchmark eligibility through the existing expert-study gate."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from artana_evidence_api.evidence_selection.provenance import (
    EvidenceSelectionExpertStudySourceManifest,
)
from artana_evidence_api.evidence_selection.source_exports import (
    EvidenceSelectionReviewExport,
    EvidenceSelectionSourceExportIdentity,
    ReviewRankingCalibrationExport,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyInput,
    evaluate_evidence_selection_expert_study_gate,
)

from .contracts import (
    EvidenceSelectionBenchmarkEvaluation,
    EvidenceSelectionBenchmarkRecordEvaluation,
)
from .loader import LoadedEvidenceSelectionBenchmarkV2, read_verified_artifact


def evaluate_benchmark_v2(
    loaded: LoadedEvidenceSelectionBenchmarkV2,
) -> EvidenceSelectionBenchmarkEvaluation:
    """Verify existing study evidence and fail closed pending external attestation."""

    fixture = loaded.fixture
    if fixture.expert_study_bundle is None:
        return _pending_evaluation(loaded)
    _, bundle_bytes = read_verified_artifact(
        reference=fixture.expert_study_bundle,
        repository_root=loaded.repository_root,
    )
    study = EvidenceSelectionExpertStudyInput.model_validate_json(bundle_bytes)
    if study.study_evidence_kind != "real_shadow_review":
        raise ValueError(
            "AI or synthetic expert-study evidence cannot make benchmark records score-eligible",
        )
    gate = evaluate_evidence_selection_expert_study_gate(study)
    if not gate.passed:
        raise ValueError("linked expert-study bundle does not pass the existing gate")
    source_manifest = study.source_manifest
    if source_manifest is None or not any(
        artifact.artifact_kind == "adjudication_log"
        and artifact.sha256 == fixture.source_packet_manifest.sha256
        for artifact in source_manifest.source_artifacts
    ):
        raise ValueError(
            "expert-study source manifest must bind the benchmark packet manifest",
        )
    _verify_source_exports(study=study, loaded=loaded)
    _verify_benchmark_bindings(study=study, loaded=loaded)
    return _pending_evaluation(
        loaded,
        status="source_verified_external_attestation_pending",
        global_reason=(
            "Source exports and declared reviewer bindings are internally verified, "
            "but the repository has no independently authenticated reviewer-identity "
            "attestation bound to those exports and packet sufficiency."
        ),
    )


def _pending_evaluation(
    loaded: LoadedEvidenceSelectionBenchmarkV2,
    *,
    status: Literal[
        "pending",
        "source_verified_external_attestation_pending",
    ] = "pending",
    global_reason: str | None = None,
) -> EvidenceSelectionBenchmarkEvaluation:
    pending_reason = global_reason or loaded.fixture.pending_expert_reason
    if pending_reason is None:
        raise ValueError("pending benchmark has no pending-expert reason")
    records = tuple(
        EvidenceSelectionBenchmarkRecordEvaluation(
            case_id=case.case_id,
            display_name=case.display_name,
            evaluation_role=case.evaluation_role,
            record_id=record.record_id,
            diagnostic_decision=loaded.diagnostics_by_record[record.record_id].decision,
            diagnostic_rationale=loaded.diagnostics_by_record[
                record.record_id
            ].rationale,
            eligibility_status=(
                "ambiguous_pending_expert"
                if loaded.diagnostics_by_record[record.record_id].decision
                == "ambiguous"
                else "pending_expert"
            ),
            score_eligible=False,
            expert_label=None,
            exclusion_reasons=(
                loaded.packet_status_by_record[record.record_id].reason,
                pending_reason,
            ),
        )
        for case in loaded.historical_v1.cases
        for record in case.records
    )
    return EvidenceSelectionBenchmarkEvaluation(
        fixture_sha256=loaded.fixture_sha256,
        historical_v1_sha256=loaded.fixture.historical_v1.sha256,
        source_packet_manifest_sha256=loaded.fixture.source_packet_manifest.sha256,
        expert_study_status=status,
        records=records,
    )


def _verify_source_exports(
    *,
    study: EvidenceSelectionExpertStudyInput,
    loaded: LoadedEvidenceSelectionBenchmarkV2,
) -> None:
    manifest = study.source_manifest
    if manifest is None:
        raise ValueError("real-shadow review requires a source manifest")
    artifacts = {
        artifact.artifact_kind: artifact for artifact in manifest.source_artifacts
    }
    if len(artifacts) != len(manifest.source_artifacts):
        raise ValueError("expert-study source artifact kinds must be unique")
    selection_artifact = artifacts.get("selection_review_export")
    if selection_artifact is None:
        raise ValueError("real-shadow review requires a selection-review source export")
    selection_bytes = _read_manifest_artifact(
        uri=selection_artifact.uri,
        expected_sha256=selection_artifact.sha256,
        repository_root=loaded.repository_root,
    )
    selection_export = EvidenceSelectionReviewExport.model_validate_json(
        selection_bytes
    )
    if selection_export.selection_reviews != study.selection_reviews:
        raise ValueError(
            "selection-review source export does not match the study bundle"
        )
    _verify_export_identity(export=selection_export, manifest=manifest)
    reviewer_ids = {review.reviewer_id for review in study.selection_reviews}
    if None in reviewer_ids or reviewer_ids != set(manifest.reviewer_roster):
        raise ValueError("reviewer roster does not exactly bind the source reviews")
    ranking_artifact = artifacts.get("review_ranking_export")
    if study.review_ranking is not None:
        if ranking_artifact is None:
            raise ValueError("ranking study requires a review-ranking source export")
        ranking_bytes = _read_manifest_artifact(
            uri=ranking_artifact.uri,
            expected_sha256=ranking_artifact.sha256,
            repository_root=loaded.repository_root,
        )
        ranking_export = ReviewRankingCalibrationExport.model_validate_json(
            ranking_bytes
        )
        if ranking_export.review_ranking != study.review_ranking:
            raise ValueError(
                "review-ranking source export does not match the study bundle"
            )
        _verify_export_identity(export=ranking_export, manifest=manifest)
    adjudication_artifact = artifacts.get("adjudication_log")
    if adjudication_artifact is None:
        raise ValueError(
            "benchmark study requires the packet manifest adjudication binding"
        )
    adjudication_bytes = _read_manifest_artifact(
        uri=adjudication_artifact.uri,
        expected_sha256=adjudication_artifact.sha256,
        repository_root=loaded.repository_root,
    )
    if (
        hashlib.sha256(adjudication_bytes).hexdigest()
        != loaded.fixture.source_packet_manifest.sha256
    ):
        raise ValueError("adjudication artifact is not the benchmark packet manifest")


def _read_manifest_artifact(
    *,
    uri: str,
    expected_sha256: str,
    repository_root: Path,
) -> bytes:
    path = (repository_root / uri).resolve()
    if not path.is_relative_to(repository_root) or not path.is_file():
        raise ValueError(
            f"expert-study source artifact is not locally resolvable: {uri}"
        )
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError(f"expert-study source artifact digest mismatch: {uri}")
    return content


def _verify_benchmark_bindings(
    *,
    study: EvidenceSelectionExpertStudyInput,
    loaded: LoadedEvidenceSelectionBenchmarkV2,
) -> None:
    reviews_by_id = {review.run_id: review for review in study.selection_reviews}
    cases_by_id = {case.case_id: case for case in loaded.historical_v1.cases}
    for binding in loaded.fixture.expert_review_bindings:
        review = reviews_by_id.get(binding.review_run_id)
        if review is None:
            raise ValueError(
                f"expert review binding is absent from source export: {binding.case_id}"
            )
        expected_ids = {
            record.record_id for record in cases_by_id[binding.case_id].records
        }
        if set(review.candidate_record_ids) != expected_ids or len(
            review.candidate_record_ids
        ) != len(expected_ids):
            raise ValueError(
                f"expert review inventory mismatches benchmark case: {binding.case_id}"
            )


def _verify_export_identity(
    *,
    export: EvidenceSelectionSourceExportIdentity,
    manifest: EvidenceSelectionExpertStudySourceManifest,
) -> None:
    identity_fields = (
        "source_system",
        "export_id",
        "exported_at",
        "exporter_id",
        "redaction_statement",
    )
    if any(
        getattr(export, field) != getattr(manifest, field) for field in identity_fields
    ):
        raise ValueError("source export identity does not match its manifest")


__all__ = ["evaluate_benchmark_v2"]
