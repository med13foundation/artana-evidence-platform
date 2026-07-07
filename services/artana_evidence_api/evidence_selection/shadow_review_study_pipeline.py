"""Build expert-study artifacts from completed shadow-review packets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from artana_evidence_api.evidence_selection.shadow_review_completion import (
    EvidenceSelectionShadowReviewSourceInputRequest,
    build_evidence_selection_shadow_review_source_inputs,
)
from artana_evidence_api.evidence_selection.source_export_writer import (
    EvidenceSelectionSourceExportWriteRequest,
    write_evidence_selection_source_exports,
)
from artana_evidence_api.evidence_selection.study_bundle import (
    EvidenceSelectionExpertStudyBundleRequest,
    build_evidence_selection_expert_study_bundle,
    validate_evidence_selection_expert_study_bundle_output_path,
    write_evidence_selection_expert_study_bundle,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyEvidenceKind,
)
from artana_evidence_api.types.common import JSONObject

_SELECTION_REVIEWS_FILENAME = "selection-review-labels.json"
_REVIEW_RANKING_FILENAME = "review-ranking-study.json"
_SELECTION_EXPORT_FILENAME = "selection-review-export.json"
_REVIEW_RANKING_EXPORT_FILENAME = "review-ranking-export.json"
_BUNDLE_FILENAME = "evidence-selection-expert-study.json"


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyArtifactRequest:
    """Completed packet and identity fields for a full study artifact handoff."""

    packet: JSONObject
    output_dir: Path
    adjudication_note: str
    source_system: str
    export_id: str
    exported_at: datetime | str
    exporter_id: str
    redaction_statement: str
    packet_path: Path | None = None
    protected_source_paths: tuple[Path, ...] = ()
    study_evidence_kind: EvidenceSelectionExpertStudyEvidenceKind = "real_shadow_review"
    description: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyArtifactResult:
    """Paths and counts produced by the completed-packet artifact pipeline."""

    selection_reviews_path: Path
    review_ranking_path: Path
    selection_export_path: Path
    review_ranking_export_path: Path
    bundle_path: Path
    selection_review_count: int
    review_ranking_decision_count: int
    source_artifact_count: int


def build_evidence_selection_shadow_review_study_artifacts(
    request: EvidenceSelectionShadowReviewStudyArtifactRequest,
) -> EvidenceSelectionShadowReviewStudyArtifactResult:
    """Write raw inputs, source exports, and an expert-study bundle."""

    _validate_output_dir(request.output_dir)
    paths = _study_artifact_paths(request.output_dir)
    source_paths = request.protected_source_paths
    if request.packet_path is not None:
        source_paths = (request.packet_path, *source_paths)
    _validate_output_paths(
        paths=paths,
        source_paths=source_paths,
    )
    source_inputs = build_evidence_selection_shadow_review_source_inputs(
        EvidenceSelectionShadowReviewSourceInputRequest(
            packet=request.packet,
            adjudication_note=request.adjudication_note,
            description=request.description,
        ),
    )
    _write_json_payload(
        paths.selection_reviews_path,
        source_inputs.selection_reviews_payload(),
    )
    _write_json_payload(
        paths.review_ranking_path,
        source_inputs.review_ranking_payload(),
    )
    source_export_result = write_evidence_selection_source_exports(
        EvidenceSelectionSourceExportWriteRequest(
            selection_reviews_path=paths.selection_reviews_path,
            review_ranking_path=paths.review_ranking_path,
            selection_export_path=paths.selection_export_path,
            review_ranking_export_path=paths.review_ranking_export_path,
            source_system=request.source_system,
            export_id=request.export_id,
            exported_at=request.exported_at,
            exporter_id=request.exporter_id,
            redaction_statement=request.redaction_statement,
        ),
    )
    validate_evidence_selection_expert_study_bundle_output_path(
        output_path=paths.bundle_path,
        source_paths=(paths.selection_export_path, paths.review_ranking_export_path),
    )
    bundle = build_evidence_selection_expert_study_bundle(
        EvidenceSelectionExpertStudyBundleRequest(
            study_id=source_inputs.review_ranking.study_id,
            study_evidence_kind=request.study_evidence_kind,
            selection_reviews_path=paths.selection_export_path,
            review_ranking_path=paths.review_ranking_export_path,
            description=request.description,
        ),
    )
    write_evidence_selection_expert_study_bundle(
        bundle=bundle,
        output_path=paths.bundle_path,
    )
    source_artifact_count = (
        0 if bundle.source_manifest is None else len(bundle.source_manifest.source_artifacts)
    )
    return EvidenceSelectionShadowReviewStudyArtifactResult(
        selection_reviews_path=paths.selection_reviews_path,
        review_ranking_path=paths.review_ranking_path,
        selection_export_path=source_export_result.selection_export_path,
        review_ranking_export_path=source_export_result.review_ranking_export_path,
        bundle_path=paths.bundle_path,
        selection_review_count=source_export_result.selection_review_count,
        review_ranking_decision_count=source_export_result.review_ranking_decision_count,
        source_artifact_count=source_artifact_count,
    )


@dataclass(frozen=True, slots=True)
class _StudyArtifactPaths:
    """Fixed file layout for one completed shadow-review study handoff."""

    selection_reviews_path: Path
    review_ranking_path: Path
    selection_export_path: Path
    review_ranking_export_path: Path
    bundle_path: Path


def _study_artifact_paths(output_dir: Path) -> _StudyArtifactPaths:
    return _StudyArtifactPaths(
        selection_reviews_path=output_dir / _SELECTION_REVIEWS_FILENAME,
        review_ranking_path=output_dir / _REVIEW_RANKING_FILENAME,
        selection_export_path=output_dir / _SELECTION_EXPORT_FILENAME,
        review_ranking_export_path=output_dir / _REVIEW_RANKING_EXPORT_FILENAME,
        bundle_path=output_dir / _BUNDLE_FILENAME,
    )


def _validate_output_paths(
    *,
    paths: _StudyArtifactPaths,
    source_paths: tuple[Path, ...],
) -> None:
    output_paths = (
        paths.selection_reviews_path,
        paths.review_ranking_path,
        paths.selection_export_path,
        paths.review_ranking_export_path,
        paths.bundle_path,
    )
    resolved_outputs = [path.resolve(strict=False) for path in output_paths]
    if len(set(resolved_outputs)) != len(resolved_outputs):
        msg = "Shadow-review study output paths must be unique."
        raise ValueError(msg)
    for source_path in source_paths:
        resolved_source = source_path.resolve(strict=False)
        for output_path, resolved_output in zip(output_paths, resolved_outputs, strict=True):
            if resolved_output == resolved_source:
                msg = (
                    "Shadow-review study output must not overwrite source packet: "
                    f"{output_path} matches {source_path}."
                )
                raise ValueError(msg)
    for output_path in output_paths:
        _validate_json_output_file(output_path)


def _validate_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        msg = f"Output directory must be a directory: {output_dir}"
        raise ValueError(msg)
    output_dir.mkdir(parents=True, exist_ok=True)


def _write_json_payload(output_path: Path, payload: JSONObject) -> None:
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_json_output_file(output_path: Path) -> None:
    if output_path.exists() and output_path.is_dir():
        msg = f"Output path must be a file: {output_path}"
        raise ValueError(msg)
    if output_path.parent.exists() and not output_path.parent.is_dir():
        msg = f"Output parent must be a directory: {output_path.parent}"
        raise ValueError(msg)


__all__ = [
    "EvidenceSelectionShadowReviewStudyArtifactRequest",
    "EvidenceSelectionShadowReviewStudyArtifactResult",
    "build_evidence_selection_shadow_review_study_artifacts",
]
