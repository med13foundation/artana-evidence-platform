"""Strict provenance contract for a frozen semantic prediction set."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .fixture import EvidenceSelectionSemanticDiagnosticFixture

EvidenceSelectionSemanticPredictionDecision = Literal[
    "select", "reject", "abstain", "invalid_agent"
]


class EvidenceSelectionSemanticSourceArtifact(BaseModel):
    """Resolvable identity for one sanitized live-result snapshot."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    evaluation_role: Literal["primary", "canary"]
    source_run_id: str = Field(min_length=1)
    source_artifact_path: str = Field(min_length=1)
    source_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    upstream_source_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class EvidenceSelectionSemanticPrediction(BaseModel):
    """One candidate decision transcribed from a live selector run."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_id: str = Field(min_length=1)
    decision: EvidenceSelectionSemanticPredictionDecision
    reason: str = Field(min_length=1)


class EvidenceSelectionSemanticPredictionArtifact(BaseModel):
    """Versioned live decisions, separate from adjudicated expected labels."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_predictions.v1"]
    provenance: Literal["manually_transcribed_live_shadow_results"]
    baseline_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    baseline_model: str = Field(min_length=1)
    source_artifacts: tuple[EvidenceSelectionSemanticSourceArtifact, ...]
    predictions: tuple[EvidenceSelectionSemanticPrediction, ...]

    @field_validator("source_artifacts", "predictions", mode="before")
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class _SemanticSourceSnapshotRecord(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_id: str
    source_key: Literal["pubmed"]
    source_record_id: str
    title: str
    evidence_excerpt: str


class _SemanticSourceSnapshotCase(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str
    evaluation_role: Literal["primary", "canary"]
    source_run_id: str
    upstream_source_artifact_sha256: str
    goal: str
    instructions: str
    inclusion_criteria: tuple[str, ...]
    exclusion_criteria: tuple[str, ...]
    records: tuple[_SemanticSourceSnapshotRecord, ...]

    @field_validator(
        "inclusion_criteria", "exclusion_criteria", "records", mode="before"
    )
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


class _SemanticSourceSnapshot(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_source_snapshot.v1"]
    source_kind: Literal["sanitized_live_shadow_result_snapshot"]
    case: _SemanticSourceSnapshotCase


def load_semantic_prediction_artifact(
    path: Path,
) -> EvidenceSelectionSemanticPredictionArtifact:
    """Load one frozen prediction artifact."""

    return EvidenceSelectionSemanticPredictionArtifact.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def verify_prediction_provenance(
    *,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    artifact: EvidenceSelectionSemanticPredictionArtifact,
    repository_root: Path,
) -> None:
    """Verify baseline identity and every committed source snapshot digest."""

    if (artifact.baseline_commit, artifact.baseline_model) != (
        fixture.baseline_commit,
        fixture.baseline_model,
    ):
        raise ValueError("prediction baseline identity does not match fixture")
    expected = {
        case.case_id: (
            case.evaluation_role,
            case.source_run_id,
            case.source_artifact_path,
            case.source_artifact_sha256,
            case.upstream_source_artifact_sha256,
        )
        for case in fixture.cases
    }
    actual = {
        source.case_id: (
            source.evaluation_role,
            source.source_run_id,
            source.source_artifact_path,
            source.source_artifact_sha256,
            source.upstream_source_artifact_sha256,
        )
        for source in artifact.source_artifacts
    }
    if actual != expected or len(actual) != len(artifact.source_artifacts):
        raise ValueError("prediction source artifact manifest does not match fixture")
    for source in artifact.source_artifacts:
        resolved_root = repository_root.resolve()
        source_path = (resolved_root / source.source_artifact_path).resolve()
        if not source_path.is_relative_to(resolved_root):
            raise ValueError(
                f"source artifact escapes repository root: {source.source_artifact_path}"
            )
        try:
            source_bytes = source_path.read_bytes()
        except OSError as exc:
            raise ValueError(
                f"source artifact is not resolvable: {source.source_artifact_path}"
            ) from exc
        if hashlib.sha256(source_bytes).hexdigest() != source.source_artifact_sha256:
            raise ValueError(
                f"source artifact digest mismatch: {source.source_artifact_path}"
            )
        snapshot = _SemanticSourceSnapshot.model_validate_json(source_bytes)
        fixture_case = next(
            case for case in fixture.cases if case.case_id == source.case_id
        )
        expected_case = {
            "case_id": fixture_case.case_id,
            "evaluation_role": fixture_case.evaluation_role,
            "source_run_id": fixture_case.source_run_id,
            "upstream_source_artifact_sha256": fixture_case.upstream_source_artifact_sha256,
            "goal": fixture_case.goal,
            "instructions": fixture_case.instructions,
            "inclusion_criteria": fixture_case.inclusion_criteria,
            "exclusion_criteria": fixture_case.exclusion_criteria,
            "records": tuple(
                {
                    "record_id": record.record_id,
                    "source_key": record.source_key,
                    "source_record_id": record.source_record_id,
                    "title": record.title,
                    "evidence_excerpt": record.evidence_excerpt,
                }
                for record in fixture_case.records
            ),
        }
        if snapshot.case.model_dump() != expected_case:
            raise ValueError(
                f"fixture content does not match source snapshot: {source.source_artifact_path}"
            )


__all__ = [
    "EvidenceSelectionSemanticPrediction",
    "EvidenceSelectionSemanticPredictionArtifact",
    "EvidenceSelectionSemanticPredictionDecision",
    "EvidenceSelectionSemanticSourceArtifact",
    "load_semantic_prediction_artifact",
    "verify_prediction_provenance",
]
