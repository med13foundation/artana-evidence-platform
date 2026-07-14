"""Freeze and verify repository-backed semantic diagnostic source evidence."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path, PurePosixPath

from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    EvidenceSelectionSemanticDiagnosticFixture,
)
from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    load_semantic_prediction_artifact,
    verify_prediction_provenance,
)
from artana_evidence_api.evidence_selection.diagnostics.report import (
    EvidenceSelectionSemanticDiagnosticReport,
)
from artana_evidence_api.evidence_selection.diagnostics.scoring import (
    score_semantic_diagnostic,
)

from .contracts import SemanticRepositorySourceFile

BUNDLED_REPOSITORY_ROOT = Path("sources/repository")


def build_repository_source_files(
    *,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    baseline: EvidenceSelectionSemanticDiagnosticReport,
    repository_root: Path,
) -> tuple[SemanticRepositorySourceFile, ...]:
    """Resolve and verify every repository file behind the baseline report."""

    prediction_relative = _canonical_relative_path(
        baseline.prediction_artifact_path,
    )
    prediction_path = _resolved_repository_path(
        repository_root=repository_root,
        relative_path=prediction_relative,
    )
    if _sha256_path(prediction_path) != baseline.prediction_artifact_sha256:
        raise ValueError("baseline prediction artifact digest mismatch")
    prediction_artifact = load_semantic_prediction_artifact(prediction_path)
    if prediction_artifact.source_artifacts != baseline.source_artifacts:
        raise ValueError("baseline report source manifest does not match predictions")
    verify_prediction_provenance(
        fixture=fixture,
        artifact=prediction_artifact,
        repository_root=repository_root,
    )
    recomputed_score = score_semantic_diagnostic(
        fixture,
        prediction_artifact.predictions,
    )
    if recomputed_score != baseline.score:
        raise ValueError("baseline score does not match its categorical predictions")

    source_files = [
        SemanticRepositorySourceFile(
            role="baseline_predictions",
            relative_path=prediction_relative,
            sha256=baseline.prediction_artifact_sha256,
        ),
    ]
    source_files.extend(
        SemanticRepositorySourceFile(
            role="sanitized_source_snapshot",
            relative_path=_canonical_relative_path(source.source_artifact_path),
            sha256=source.source_artifact_sha256,
        )
        for source in sorted(
            baseline.source_artifacts,
            key=lambda item: item.source_artifact_path,
        )
    )
    return tuple(source_files)


def verify_repository_source_provenance(
    *,
    expected_files: tuple[SemanticRepositorySourceFile, ...],
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    baseline: EvidenceSelectionSemanticDiagnosticReport,
    repository_root: Path,
) -> None:
    """Reject source-manifest, snapshot, or baseline-prediction drift."""

    observed_files = build_repository_source_files(
        fixture=fixture,
        baseline=baseline,
        repository_root=repository_root,
    )
    if observed_files != expected_files:
        raise ValueError("repository source files do not match the frozen protocol")


def copy_repository_source_files(
    *,
    source_files: tuple[SemanticRepositorySourceFile, ...],
    repository_root: Path,
    destination_root: Path,
) -> None:
    """Copy frozen repository sources while preserving their relative paths."""

    for source in source_files:
        origin = _resolved_repository_path(
            repository_root=repository_root,
            relative_path=source.relative_path,
        )
        if _sha256_path(origin) != source.sha256:
            raise ValueError(
                f"repository source digest mismatch: {source.relative_path}",
            )
        destination = destination_root / source.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)


def _canonical_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError("semantic source paths must be canonical and relative")
    return value


def _resolved_repository_path(*, repository_root: Path, relative_path: str) -> Path:
    root = repository_root.resolve()
    path = (root / _canonical_relative_path(relative_path)).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"semantic source path escapes repository: {relative_path}")
    if not path.is_file():
        raise ValueError(f"semantic source file is not resolvable: {relative_path}")
    return path


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "BUNDLED_REPOSITORY_ROOT",
    "build_repository_source_files",
    "copy_repository_source_files",
    "verify_repository_source_provenance",
]
