"""Run completed shadow-review study pipelines as a measured batch."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from artana_evidence_api.evidence_selection.shadow_review_study_pipeline import (
    EvidenceSelectionShadowReviewStudyArtifactRequest,
    EvidenceSelectionShadowReviewStudyArtifactResult,
    build_evidence_selection_shadow_review_study_artifacts,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyGateThresholds,
    EvidenceSelectionExpertStudyInput,
    ReviewRankingCalibrationGateThresholds,
    evaluate_evidence_selection_expert_study_gate,
)
from artana_evidence_api.types.common import JSONObject, json_object
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_MANIFEST_SCHEMA_VERSION = "evidence_selection_shadow_review_study_batch.v1"
_REPORT_SCHEMA_VERSION = "evidence_selection_shadow_review_study_batch_report.v1"
_ENTRY_ARTIFACT_FILENAMES = (
    "selection-review-labels.json",
    "review-ranking-study.json",
    "selection-review-export.json",
    "review-ranking-export.json",
    "evidence-selection-expert-study.json",
)


class EvidenceSelectionShadowReviewStudyBatchEntry(BaseModel):
    """One completed packet in a shadow-review study batch manifest."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    entry_id: str
    packet_path: Path
    output_subdir: str
    adjudication_note: str
    source_system: str
    export_id: str
    exported_at: str
    exporter_id: str
    redaction_statement: str
    description: str | None = None

    @field_validator("packet_path", mode="before")
    @classmethod
    def _parse_packet_path(cls, value: object) -> Path:
        if isinstance(value, Path):
            return value
        if isinstance(value, str) and value.strip():
            return Path(value)
        msg = "packet_path must be a non-empty path."
        raise ValueError(msg)

    @field_validator(
        "entry_id",
        "adjudication_note",
        "source_system",
        "export_id",
        "exported_at",
        "exporter_id",
        "redaction_statement",
    )
    @classmethod
    def _reject_blank_or_padded_text(cls, value: str) -> str:
        if not value.strip():
            msg = "Batch manifest text fields must not be blank."
            raise ValueError(msg)
        if value != value.strip():
            msg = "Batch manifest text fields must not have leading/trailing whitespace."
            raise ValueError(msg)
        return value

    @field_validator("description")
    @classmethod
    def _reject_padded_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            msg = "description must not be blank when provided."
            raise ValueError(msg)
        if value != value.strip():
            msg = "description must not have leading/trailing whitespace."
            raise ValueError(msg)
        return value

    @field_validator("output_subdir")
    @classmethod
    def _validate_output_subdir(cls, value: str) -> str:
        if value != value.strip() or not value.strip():
            msg = "output_subdir must be relative and non-empty."
            raise ValueError(msg)
        if "\\" in value:
            msg = "output_subdir must be relative and use POSIX path separators."
            raise ValueError(msg)
        subdir = PurePosixPath(value)
        if subdir.is_absolute() or subdir.parts in ((), (".",)):
            msg = "output_subdir must be relative and non-empty."
            raise ValueError(msg)
        if any(part in {"", ".", ".."} for part in subdir.parts):
            msg = "output_subdir must be relative and must not escape output_dir."
            raise ValueError(msg)
        return str(subdir)


class EvidenceSelectionShadowReviewStudyBatchManifest(BaseModel):
    """Strict manifest for a batch of completed shadow-review study packets."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_shadow_review_study_batch.v1"]
    batch_id: str
    entries: tuple[EvidenceSelectionShadowReviewStudyBatchEntry, ...] = Field(
        min_length=1,
    )

    @field_validator("entries", mode="before")
    @classmethod
    def _parse_entries(
        cls,
        value: object,
    ) -> tuple[object, ...]:
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(value)
        msg = "entries must be a non-empty list."
        raise ValueError(msg)

    @field_validator("batch_id")
    @classmethod
    def _reject_blank_or_padded_batch_id(cls, value: str) -> str:
        if not value.strip():
            msg = "batch_id must not be blank."
            raise ValueError(msg)
        if value != value.strip():
            msg = "batch_id must not have leading/trailing whitespace."
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _reject_duplicate_entry_identity(self) -> Self:
        _reject_duplicates(
            label="batch entry_id",
            values=(entry.entry_id for entry in self.entries),
        )
        _reject_duplicates(
            label="batch output_subdir",
            values=(entry.output_subdir for entry in self.entries),
        )
        _reject_duplicates(
            label="batch export_id",
            values=(entry.export_id for entry in self.entries),
        )
        return self


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyBatchThresholds:
    """Thresholds for per-packet expert/shadow study gates in a batch."""

    min_selection_review_count: int = 3
    min_distinct_selection_goals: int = 3
    min_selection_reviewer_count: int = 1
    min_mean_precision: float = 0.8
    min_mean_recall: float = 0.8
    min_mean_explanation_quality: float = 3.0
    min_source_artifact_count: int = 2
    min_review_ranking_sample_count: int = 10
    max_expected_calibration_error: float = 0.05
    min_distinct_ranking_goals: int = 3
    min_distinct_evidence_shapes: int = 3


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyBatchRequest:
    """Inputs for building a measured completed-packet study batch."""

    manifest: EvidenceSelectionShadowReviewStudyBatchManifest
    output_dir: Path
    manifest_path: Path | None = None
    thresholds: EvidenceSelectionShadowReviewStudyBatchThresholds = field(
        default_factory=EvidenceSelectionShadowReviewStudyBatchThresholds,
    )


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyBatchEntryResult:
    """Artifacts and gate evidence for one completed packet in a batch."""

    entry_id: str
    packet_path: Path
    output_dir: Path
    artifact_result: EvidenceSelectionShadowReviewStudyArtifactResult
    gate_report: JSONObject

    @property
    def gate_passed(self) -> bool:
        return self._gate().get("passed") is True

    @property
    def gate_status(self) -> str | None:
        status = self._gate().get("status")
        if isinstance(status, str):
            return status
        return None

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        return tuple(_string_list(self._gate().get("blocking_reasons")))

    def to_json(self, gate_report_manifest: JSONObject | None = None) -> JSONObject:
        payload: JSONObject = {
            "entry_id": self.entry_id,
            "packet_path": str(self.packet_path),
            "output_dir": str(self.output_dir),
            "gate_passed": self.gate_passed,
            "gate_status": self.gate_status,
            "blocking_reasons": list(self.blocking_reasons),
            "selection_review_count": self.artifact_result.selection_review_count,
            "review_ranking_decision_count": (
                self.artifact_result.review_ranking_decision_count
            ),
            "source_artifact_count": self.artifact_result.source_artifact_count,
            "paths": {
                "selection_reviews": str(self.artifact_result.selection_reviews_path),
                "review_ranking": str(self.artifact_result.review_ranking_path),
                "selection_export": str(self.artifact_result.selection_export_path),
                "review_ranking_export": str(
                    self.artifact_result.review_ranking_export_path,
                ),
                "bundle": str(self.artifact_result.bundle_path),
            },
        }
        if gate_report_manifest is not None:
            payload["gate_report"] = gate_report_manifest
        return payload

    def _gate(self) -> JSONObject:
        return _object_value(self.gate_report, "gate")


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyBatchResult:
    """Aggregate result for a completed-packet shadow-review batch."""

    batch_id: str
    output_dir: Path
    generated_at: str
    entries: tuple[EvidenceSelectionShadowReviewStudyBatchEntryResult, ...]

    @property
    def passed(self) -> bool:
        return self.failed_entry_count == 0

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def passed_entry_count(self) -> int:
        return sum(1 for entry in self.entries if entry.gate_passed)

    @property
    def failed_entry_count(self) -> int:
        return self.entry_count - self.passed_entry_count

    def to_json(
        self,
        *,
        gate_report_manifests: Mapping[str, JSONObject] | None = None,
    ) -> JSONObject:
        manifests = gate_report_manifests or {}
        return {
            "schema_version": _REPORT_SCHEMA_VERSION,
            "batch_id": self.batch_id,
            "generated_at": self.generated_at,
            "output_dir": str(self.output_dir),
            "passed": self.passed,
            "entry_count": self.entry_count,
            "passed_entry_count": self.passed_entry_count,
            "failed_entry_count": self.failed_entry_count,
            "entries": [
                entry.to_json(gate_report_manifest=manifests.get(entry.entry_id))
                for entry in self.entries
            ],
        }


def load_evidence_selection_shadow_review_study_batch_manifest(
    path: Path,
) -> EvidenceSelectionShadowReviewStudyBatchManifest:
    """Load and validate a completed shadow-review study batch manifest."""

    return EvidenceSelectionShadowReviewStudyBatchManifest.model_validate(
        _load_json_object(path),
    )


def collect_evidence_selection_shadow_review_study_batch_source_paths(
    *,
    manifest: EvidenceSelectionShadowReviewStudyBatchManifest,
    manifest_path: Path | None = None,
) -> tuple[Path, ...]:
    """Return every source path protected from batch artifact/report writes."""

    source_paths = list(_protected_manifest_paths(manifest_path))
    source_paths.extend(
        _resolve_packet_path(
            packet_path=entry.packet_path,
            manifest_path=manifest_path,
        )
        for entry in manifest.entries
    )
    return tuple(source_paths)


def build_evidence_selection_shadow_review_study_batch(
    request: EvidenceSelectionShadowReviewStudyBatchRequest,
) -> EvidenceSelectionShadowReviewStudyBatchResult:
    """Run the single-packet shadow-review study pipeline for every batch entry."""

    _validate_output_dir(request.output_dir)
    protected_source_paths = collect_evidence_selection_shadow_review_study_batch_source_paths(
        manifest=request.manifest,
        manifest_path=request.manifest_path,
    )
    _validate_batch_artifact_source_collisions(
        output_dir=request.output_dir,
        manifest=request.manifest,
        manifest_path=request.manifest_path,
        source_paths=protected_source_paths,
    )
    entries: list[EvidenceSelectionShadowReviewStudyBatchEntryResult] = []
    for entry in request.manifest.entries:
        packet_path = _resolve_packet_path(
            packet_path=entry.packet_path,
            manifest_path=request.manifest_path,
        )
        output_dir = request.output_dir / entry.output_subdir
        artifact_result = build_evidence_selection_shadow_review_study_artifacts(
            EvidenceSelectionShadowReviewStudyArtifactRequest(
                packet=_load_json_object(packet_path),
                packet_path=packet_path,
                protected_source_paths=protected_source_paths,
                output_dir=output_dir,
                adjudication_note=entry.adjudication_note,
                source_system=entry.source_system,
                export_id=entry.export_id,
                exported_at=entry.exported_at,
                exporter_id=entry.exporter_id,
                redaction_statement=entry.redaction_statement,
                description=entry.description,
            ),
        )
        entries.append(
            EvidenceSelectionShadowReviewStudyBatchEntryResult(
                entry_id=entry.entry_id,
                packet_path=packet_path,
                output_dir=output_dir,
                artifact_result=artifact_result,
                gate_report=build_evidence_selection_shadow_review_study_gate_report(
                    input_path=artifact_result.bundle_path,
                    thresholds=request.thresholds,
                ),
            ),
        )
    return EvidenceSelectionShadowReviewStudyBatchResult(
        batch_id=request.manifest.batch_id,
        output_dir=request.output_dir,
        generated_at=datetime.now(UTC).isoformat(),
        entries=tuple(entries),
    )


def build_evidence_selection_shadow_review_study_gate_report(
    *,
    input_path: Path,
    thresholds: EvidenceSelectionShadowReviewStudyBatchThresholds,
) -> JSONObject:
    """Evaluate one expert/shadow study bundle and return a gate report."""

    payload = _load_json_object(input_path)
    study_input = EvidenceSelectionExpertStudyInput.model_validate(payload)
    gate_report = evaluate_evidence_selection_expert_study_gate(
        study_input,
        thresholds=EvidenceSelectionExpertStudyGateThresholds(
            min_selection_review_count=thresholds.min_selection_review_count,
            min_distinct_selection_goals=thresholds.min_distinct_selection_goals,
            min_selection_reviewer_count=thresholds.min_selection_reviewer_count,
            min_mean_precision=thresholds.min_mean_precision,
            min_mean_recall=thresholds.min_mean_recall,
            min_mean_explanation_quality=thresholds.min_mean_explanation_quality,
            min_source_artifact_count=thresholds.min_source_artifact_count,
        ),
        review_ranking_thresholds=ReviewRankingCalibrationGateThresholds(
            min_sample_count=thresholds.min_review_ranking_sample_count,
            max_expected_calibration_error=thresholds.max_expected_calibration_error,
            min_distinct_goals=thresholds.min_distinct_ranking_goals,
            min_distinct_evidence_shapes=thresholds.min_distinct_evidence_shapes,
            require_reviewer_ids=True,
            require_adjudication_note=True,
        ),
    )
    return {
        "schema_version": study_input.schema_version,
        "study_id": study_input.study_id,
        "input_path": str(input_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "gate": gate_report.to_json(),
    }


def _load_json_object(path: Path) -> JSONObject:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"{path} is not valid JSON: {exc.msg}."
        raise ValueError(msg) from exc
    result = json_object(payload)
    if result is None:
        msg = f"{path} does not contain a JSON object."
        raise ValueError(msg)
    return result


def _validate_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        msg = f"Output directory must be a directory: {output_dir}"
        raise ValueError(msg)
    output_dir.mkdir(parents=True, exist_ok=True)


def _protected_manifest_paths(manifest_path: Path | None) -> tuple[Path, ...]:
    if manifest_path is None:
        return ()
    return (manifest_path,)


def _resolve_packet_path(
    *,
    packet_path: Path,
    manifest_path: Path | None,
) -> Path:
    if manifest_path is not None and not packet_path.is_absolute():
        return manifest_path.parent / packet_path
    return packet_path


def _validate_batch_artifact_source_collisions(
    *,
    output_dir: Path,
    manifest: EvidenceSelectionShadowReviewStudyBatchManifest,
    manifest_path: Path | None,
    source_paths: tuple[Path, ...],
) -> None:
    protected_sources = tuple(
        (source_path, source_path.resolve(strict=False)) for source_path in source_paths
    )
    for entry in manifest.entries:
        entry_output_dir = output_dir / entry.output_subdir
        for filename in _ENTRY_ARTIFACT_FILENAMES:
            output_path = entry_output_dir / filename
            resolved_output = output_path.resolve(strict=False)
            for source_path, resolved_source in protected_sources:
                if resolved_output == resolved_source:
                    source_label = _source_path_label(
                        source_path=source_path,
                        manifest_path=manifest_path,
                    )
                    msg = (
                        f"Shadow-review batch artifacts must not overwrite {source_label}: "
                        f"{output_path} matches {source_path}."
                    )
                    raise ValueError(msg)


def _source_path_label(*, source_path: Path, manifest_path: Path | None) -> str:
    if (
        manifest_path is not None
        and source_path.resolve(strict=False) == manifest_path.resolve(strict=False)
    ):
        return "manifest"
    return "source packet"


def _reject_duplicates(*, label: str, values: Iterable[str]) -> None:
    seen: set[str] = set()
    for value in values:
        value_text = str(value)
        if value_text in seen:
            msg = f"Duplicate {label}: {value_text}"
            raise ValueError(msg)
        seen.add(value_text)


def _object_value(payload: Mapping[str, object], key: str) -> JSONObject:
    value = payload.get(key)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


__all__ = [
    "EvidenceSelectionShadowReviewStudyBatchEntry",
    "EvidenceSelectionShadowReviewStudyBatchEntryResult",
    "EvidenceSelectionShadowReviewStudyBatchManifest",
    "EvidenceSelectionShadowReviewStudyBatchRequest",
    "EvidenceSelectionShadowReviewStudyBatchResult",
    "EvidenceSelectionShadowReviewStudyBatchThresholds",
    "build_evidence_selection_shadow_review_study_batch",
    "build_evidence_selection_shadow_review_study_gate_report",
    "collect_evidence_selection_shadow_review_study_batch_source_paths",
    "load_evidence_selection_shadow_review_study_batch_manifest",
]
