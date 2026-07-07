"""Build reproducible evidence-selection expert/shadow study bundles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from artana_evidence_api.evidence_selection.provenance import (
    EvidenceSelectionExpertStudySourceArtifact,
    EvidenceSelectionExpertStudySourceArtifactKind,
    EvidenceSelectionExpertStudySourceManifest,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyEvidenceKind,
    EvidenceSelectionExpertStudyInput,
    EvidenceSelectionReviewInput,
    ReviewRankingCalibrationStudyInput,
)
from pydantic import BaseModel, ConfigDict, field_validator


class EvidenceSelectionExpertStudyBundleError(ValueError):
    """Raised when expert-study source artifacts cannot build a safe bundle."""


@dataclass(frozen=True, slots=True)
class EvidenceSelectionExpertStudyBundleRequest:
    """Source files and metadata required to build an expert-study bundle."""

    study_id: str
    study_evidence_kind: EvidenceSelectionExpertStudyEvidenceKind
    selection_reviews_path: Path
    review_ranking_path: Path
    source_system: str
    export_id: str
    exported_at: datetime
    exporter_id: str
    redaction_statement: str
    description: str | None = None
    selection_reviews_uri: str | None = None
    review_ranking_uri: str | None = None
    adjudication_log_path: Path | None = None
    adjudication_log_uri: str | None = None


@dataclass(frozen=True, slots=True)
class _LoadedSourceArtifact:
    """Immutable source bytes plus the manifest fields derived from them."""

    path: Path
    uri: str
    content: bytes
    sha256: str


class _SelectionReviewExport(BaseModel):
    """Strict source export envelope for selection-review labels."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    selection_reviews: tuple[EvidenceSelectionReviewInput, ...]

    @field_validator("selection_reviews", mode="before")
    @classmethod
    def _accept_json_selection_review_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


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
    selection_reviews = _load_selection_reviews(selection_source)
    review_ranking = _load_review_ranking(ranking_source)
    source_manifest = _build_source_manifest(
        request=request,
        selection_source=selection_source,
        ranking_source=ranking_source,
        adjudication_source=adjudication_source,
        selection_reviews=selection_reviews,
        review_ranking=review_ranking,
    )
    return EvidenceSelectionExpertStudyInput(
        schema_version="evidence_selection_expert_study.v1",
        study_id=request.study_id,
        study_evidence_kind=request.study_evidence_kind,
        selection_reviews=selection_reviews,
        review_ranking=review_ranking,
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

    resolved_output_path = output_path.resolve(strict=False)
    for source_path in source_paths:
        if resolved_output_path == source_path.resolve(strict=False):
            msg = (
                "Output path must not overwrite source artifact: "
                f"{output_path} matches {source_path}."
            )
            raise EvidenceSelectionExpertStudyBundleError(msg)


def _load_selection_reviews(
    source: _LoadedSourceArtifact,
) -> tuple[EvidenceSelectionReviewInput, ...]:
    payload = _load_json_object(source)
    export = _SelectionReviewExport.model_validate(payload)
    return export.selection_reviews


def _load_review_ranking(
    source: _LoadedSourceArtifact,
) -> ReviewRankingCalibrationStudyInput:
    payload = _load_json_object(source)
    return ReviewRankingCalibrationStudyInput.model_validate(payload)


def _build_source_manifest(
    *,
    request: EvidenceSelectionExpertStudyBundleRequest,
    selection_source: _LoadedSourceArtifact,
    ranking_source: _LoadedSourceArtifact,
    adjudication_source: _LoadedSourceArtifact | None,
    selection_reviews: tuple[EvidenceSelectionReviewInput, ...],
    review_ranking: ReviewRankingCalibrationStudyInput,
) -> EvidenceSelectionExpertStudySourceManifest:
    return EvidenceSelectionExpertStudySourceManifest(
        source_system=request.source_system,
        export_id=request.export_id,
        exported_at=request.exported_at,
        exporter_id=request.exporter_id,
        redaction_statement=request.redaction_statement,
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
