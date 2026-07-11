"""Build reproducible evidence-selection expert/shadow study bundles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from artana_evidence_api.evidence_selection.output_paths import paths_alias
from artana_evidence_api.evidence_selection.provenance import (
    EvidenceSelectionExpertStudySourceArtifact,
    EvidenceSelectionExpertStudySourceArtifactKind,
    EvidenceSelectionExpertStudySourceManifest,
)
from artana_evidence_api.evidence_selection.source_exports import (
    EvidenceSelectionReviewExport,
    EvidenceSelectionSourceExportIdentity,
    ReviewRankingCalibrationExport,
    ensure_matching_source_export_identity,
    parse_canonical_source_exported_at,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyEvidenceKind,
    EvidenceSelectionExpertStudyInput,
    EvidenceSelectionReviewInput,
    ReviewRankingCalibrationStudyInput,
)


class EvidenceSelectionExpertStudyBundleError(ValueError):
    """Raised when expert-study source artifacts cannot build a safe bundle."""


@dataclass(frozen=True, slots=True)
class EvidenceSelectionExpertStudyBundleRequest:
    """Source files and metadata required to build an expert-study bundle."""

    study_id: str
    study_evidence_kind: EvidenceSelectionExpertStudyEvidenceKind
    selection_reviews_path: Path
    review_ranking_path: Path
    description: str | None = None
    selection_reviews_uri: str | None = None
    review_ranking_uri: str | None = None
    adjudication_log_path: Path | None = None
    adjudication_log_uri: str | None = None
    source_system: str | None = None
    export_id: str | None = None
    exported_at: datetime | str | None = None
    exporter_id: str | None = None
    redaction_statement: str | None = None


@dataclass(frozen=True, slots=True)
class _LoadedSourceArtifact:
    """Immutable source bytes plus the manifest fields derived from them."""

    path: Path
    uri: str
    content: bytes
    sha256: str


def build_evidence_selection_expert_study_bundle(
    request: EvidenceSelectionExpertStudyBundleRequest,
) -> EvidenceSelectionExpertStudyInput:
    """Return a complete expert/shadow study bundle from source exports."""

    selection_source = _read_source_artifact(
        path=request.selection_reviews_path,
        uri=request.selection_reviews_uri,
    )
    ranking_source = _read_source_artifact(
        path=request.review_ranking_path,
        uri=request.review_ranking_uri,
    )
    adjudication_source = (
        _read_source_artifact(
            path=request.adjudication_log_path,
            uri=request.adjudication_log_uri,
        )
        if request.adjudication_log_path is not None
        else None
    )
    selection_export = _load_selection_export(selection_source)
    ranking_export = _load_review_ranking_export(ranking_source)
    source_identity = _source_identity(
        request=request,
        selection_export=selection_export,
        ranking_export=ranking_export,
    )
    source_manifest = _build_source_manifest(
        source_identity=source_identity,
        selection_source=selection_source,
        ranking_source=ranking_source,
        adjudication_source=adjudication_source,
        selection_reviews=selection_export.selection_reviews,
        review_ranking=ranking_export.review_ranking,
    )
    return EvidenceSelectionExpertStudyInput(
        schema_version="evidence_selection_expert_study.v1",
        study_id=request.study_id,
        study_evidence_kind=request.study_evidence_kind,
        selection_reviews=selection_export.selection_reviews,
        review_ranking=ranking_export.review_ranking,
        source_manifest=source_manifest,
        description=request.description,
    )


def write_evidence_selection_expert_study_bundle(
    *,
    bundle: EvidenceSelectionExpertStudyInput,
    output_path: Path,
) -> None:
    """Write an expert/shadow study bundle JSON file."""

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                bundle.model_dump(mode="json", exclude_none=True),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        msg = f"Unable to write expert-study bundle {output_path}: {exc}"
        raise EvidenceSelectionExpertStudyBundleError(msg) from exc


def validate_evidence_selection_expert_study_bundle_output_path(
    *,
    output_path: Path,
    source_paths: tuple[Path, ...],
) -> None:
    """Reject output paths that would overwrite source artifacts."""

    for source_path in source_paths:
        if paths_alias(output_path, source_path):
            msg = (
                "Output path must not overwrite source artifact: "
                f"{output_path} matches {source_path}."
            )
            raise EvidenceSelectionExpertStudyBundleError(msg)


def _load_selection_export(
    source: _LoadedSourceArtifact,
) -> EvidenceSelectionReviewExport:
    payload = _load_json_object(source)
    return EvidenceSelectionReviewExport.model_validate(payload)


def _load_review_ranking_export(
    source: _LoadedSourceArtifact,
) -> ReviewRankingCalibrationExport:
    payload = _load_json_object(source)
    return ReviewRankingCalibrationExport.model_validate(payload)


def _source_identity(
    *,
    request: EvidenceSelectionExpertStudyBundleRequest,
    selection_export: EvidenceSelectionReviewExport,
    ranking_export: ReviewRankingCalibrationExport,
) -> EvidenceSelectionSourceExportIdentity:
    try:
        source_identity = ensure_matching_source_export_identity(
            selection_export=selection_export,
            ranking_export=ranking_export,
        )
    except ValueError as exc:
        raise EvidenceSelectionExpertStudyBundleError(str(exc)) from exc
    requested_identity = _requested_source_identity(request)
    if requested_identity is not None and requested_identity != source_identity:
        msg = (
            "Requested source export identity does not match the source export "
            "identity embedded in the selection-review and review-ranking files."
        )
        raise EvidenceSelectionExpertStudyBundleError(msg)
    return source_identity


def _requested_source_identity(
    request: EvidenceSelectionExpertStudyBundleRequest,
) -> EvidenceSelectionSourceExportIdentity | None:
    values = (
        request.source_system,
        request.export_id,
        request.exported_at,
        request.exporter_id,
        request.redaction_statement,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        msg = (
            "All source identity override fields must be provided together: "
            "source_system, export_id, exported_at, exporter_id, and "
            "redaction_statement."
        )
        raise EvidenceSelectionExpertStudyBundleError(msg)
    return EvidenceSelectionSourceExportIdentity(
        source_system=cast("str", request.source_system),
        export_id=cast("str", request.export_id),
        exported_at=_requested_exported_at(request.exported_at),
        exporter_id=cast("str", request.exporter_id),
        redaction_statement=cast("str", request.redaction_statement),
    )


def _requested_exported_at(value: datetime | str | None) -> datetime:
    if isinstance(value, datetime | str):
        try:
            return parse_canonical_source_exported_at(
                value,
                field_name="Requested source export identity exported_at",
            )
        except ValueError as exc:
            raise EvidenceSelectionExpertStudyBundleError(str(exc)) from exc
    msg = "Requested source export identity is missing exported_at."
    raise EvidenceSelectionExpertStudyBundleError(msg)


def _build_source_manifest(
    *,
    source_identity: EvidenceSelectionSourceExportIdentity,
    selection_source: _LoadedSourceArtifact,
    ranking_source: _LoadedSourceArtifact,
    adjudication_source: _LoadedSourceArtifact | None,
    selection_reviews: tuple[EvidenceSelectionReviewInput, ...],
    review_ranking: ReviewRankingCalibrationStudyInput,
) -> EvidenceSelectionExpertStudySourceManifest:
    return EvidenceSelectionExpertStudySourceManifest(
        source_system=source_identity.source_system,
        export_id=source_identity.export_id,
        exported_at=source_identity.exported_at,
        exporter_id=source_identity.exporter_id,
        redaction_statement=source_identity.redaction_statement,
        source_artifacts=_source_artifacts(
            selection_source=selection_source,
            ranking_source=ranking_source,
            adjudication_source=adjudication_source,
        ),
        selection_review_run_ids=tuple(review.run_id for review in selection_reviews),
        review_ranking_decision_keys=tuple(
            f"{decision.source_kind}:{decision.item_id}"
            for decision in review_ranking.decisions
        ),
        reviewer_roster=_reviewer_roster(
            selection_reviews=selection_reviews,
            review_ranking=review_ranking,
        ),
    )


def _source_artifacts(
    *,
    selection_source: _LoadedSourceArtifact,
    ranking_source: _LoadedSourceArtifact,
    adjudication_source: _LoadedSourceArtifact | None,
) -> tuple[EvidenceSelectionExpertStudySourceArtifact, ...]:
    artifacts = [
        _source_artifact(
            artifact_id="selection-review-export",
            artifact_kind="selection_review_export",
            source=selection_source,
        ),
        _source_artifact(
            artifact_id="review-ranking-export",
            artifact_kind="review_ranking_export",
            source=ranking_source,
        ),
    ]
    if adjudication_source is not None:
        artifacts.append(
            _source_artifact(
                artifact_id="adjudication-log",
                artifact_kind="adjudication_log",
                source=adjudication_source,
            ),
        )
    return tuple(artifacts)


def _source_artifact(
    *,
    artifact_id: str,
    artifact_kind: EvidenceSelectionExpertStudySourceArtifactKind,
    source: _LoadedSourceArtifact,
) -> EvidenceSelectionExpertStudySourceArtifact:
    return EvidenceSelectionExpertStudySourceArtifact(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        uri=source.uri,
        sha256=source.sha256,
    )


def _reviewer_roster(
    *,
    selection_reviews: tuple[EvidenceSelectionReviewInput, ...],
    review_ranking: ReviewRankingCalibrationStudyInput,
) -> tuple[str, ...]:
    reviewer_ids = {
        reviewer_id.strip()
        for review in selection_reviews
        if (reviewer_id := review.reviewer_id) and reviewer_id.strip()
    }
    reviewer_ids.update(
        reviewer_id.strip()
        for decision in review_ranking.decisions
        if (reviewer_id := decision.reviewer_id) and reviewer_id.strip()
    )
    return tuple(sorted(reviewer_ids))


def _read_source_artifact(*, path: Path, uri: str | None) -> _LoadedSourceArtifact:
    try:
        content = path.read_bytes()
    except OSError as exc:
        msg = f"Unable to read source artifact {path}: {exc}"
        raise EvidenceSelectionExpertStudyBundleError(msg) from exc
    return _LoadedSourceArtifact(
        path=path,
        uri=uri or str(path),
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _load_json_object(source: _LoadedSourceArtifact) -> dict[str, object]:
    try:
        source_text = source.content.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"{source.path} is not valid UTF-8 JSON."
        raise EvidenceSelectionExpertStudyBundleError(msg) from exc
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        msg = f"{source.path} is not valid JSON: {exc.msg}."
        raise EvidenceSelectionExpertStudyBundleError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"{source.path} does not contain a JSON object."
        raise EvidenceSelectionExpertStudyBundleError(msg)
    return cast("dict[str, object]", payload)


__all__ = [
    "EvidenceSelectionExpertStudyBundleError",
    "EvidenceSelectionExpertStudyBundleRequest",
    "build_evidence_selection_expert_study_bundle",
    "validate_evidence_selection_expert_study_bundle_output_path",
    "write_evidence_selection_expert_study_bundle",
]
