"""Run completed shadow-review study pipelines as a measured batch."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Self

from artana_evidence_api.evidence_selection.output_paths import paths_alias
from artana_evidence_api.evidence_selection.shadow_review_completion import (
    machine_packet_sidecar_path,
)
from artana_evidence_api.evidence_selection.shadow_review_study_batch_outputs import (
    prepare_batch_output_dir,
    rollback_published_batch_outputs,
)
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
_MIN_EXPLANATION_QUALITY = 1.0
_MAX_EXPLANATION_QUALITY = 5.0
_ENTRY_ARTIFACT_FILENAMES = (
    "selection-review-labels.json",
    "review-ranking-study.json",
    "selection-review-export.json",
    "review-ranking-export.json",
    "evidence-selection-expert-study.json",
)
_REVIEW_RANKING_SOURCE_KINDS = ("proposal", "review_item")
_REVIEW_RANKING_OUTCOMES = ("positive", "negative")


class EvidenceSelectionShadowReviewStudyBatchEntry(BaseModel):
    """One completed packet in a shadow-review study batch manifest."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    entry_id: str
    machine_packet_path: Path | None = None
    packet_path: Path
    output_subdir: str
    adjudication_note: str
    source_system: str
    export_id: str
    exported_at: str
    exporter_id: str
    redaction_statement: str
    description: str | None = None

    @field_validator("machine_packet_path", "packet_path", mode="before")
    @classmethod
    def _parse_packet_path(cls, value: object) -> Path | None:
        if value is None:
            return None
        if isinstance(value, Path):
            return value
        if isinstance(value, str) and value.strip():
            return Path(value)
        msg = "machine_packet_path and packet_path must be non-empty paths."
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

    min_selection_review_count: int = 1
    min_distinct_selection_goals: int = 1
    min_selection_reviewer_count: int = 1
    min_mean_precision: float = 0.8
    min_mean_recall: float = 0.8
    min_mean_explanation_quality: float = 3.0
    min_source_artifact_count: int = 2
    min_review_ranking_sample_count: int = 2
    max_expected_calibration_error: float = 0.05
    min_distinct_ranking_goals: int = 1
    min_distinct_evidence_shapes: int = 1


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyBatchSuiteThresholds:
    """Thresholds for claiming a completed-packet batch is study-level evidence."""

    min_entry_count: int = 3
    min_passed_entry_count: int = 3
    max_failed_entry_count: int = 0
    min_passed_entry_rate: float = 1.0
    min_suite_mean_precision: float = 0.8
    min_suite_mean_recall: float = 0.8
    min_suite_mean_explanation_quality: float = 3.0
    max_suite_expected_calibration_error: float = 0.05
    min_total_selection_review_count: int = 3
    min_total_review_ranking_decision_count: int = 10
    min_distinct_source_run_ids: int = 3
    min_distinct_study_ids: int = 3
    min_distinct_selection_goals: int = 3
    min_distinct_review_ranking_goals: int = 3
    min_distinct_evidence_shapes: int = 3


_PRODUCTION_SUITE_THRESHOLD_FLOORS = (
    EvidenceSelectionShadowReviewStudyBatchSuiteThresholds()
)


@dataclass(frozen=True, slots=True)
class _BatchQualityMetrics:
    suite_mean_precision: float
    suite_mean_recall: float
    suite_mean_explanation_quality: float
    max_review_ranking_expected_calibration_error: float

    def to_json(self) -> JSONObject:
        return {
            "suite_mean_precision": round(self.suite_mean_precision, 4),
            "suite_mean_recall": round(self.suite_mean_recall, 4),
            "suite_mean_explanation_quality": round(
                self.suite_mean_explanation_quality,
                4,
            ),
            "max_review_ranking_expected_calibration_error": round(
                self.max_review_ranking_expected_calibration_error,
                6,
            ),
        }


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyBatchRequest:
    """Inputs for building a measured completed-packet study batch."""

    manifest: EvidenceSelectionShadowReviewStudyBatchManifest
    output_dir: Path
    manifest_path: Path | None = None
    thresholds: EvidenceSelectionShadowReviewStudyBatchThresholds = field(
        default_factory=EvidenceSelectionShadowReviewStudyBatchThresholds,
    )
    suite_thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds = field(
        default_factory=EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
    )


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewStudyBatchEntryResult:
    """Artifacts and gate evidence for one completed packet in a batch."""

    entry_id: str
    machine_packet_path: Path
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
            "machine_packet_path": str(self.machine_packet_path),
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
    suite_gate: JSONObject

    @property
    def passed(self) -> bool:
        return self.suite_gate.get("passed") is True

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
            "suite_gate": dict(self.suite_gate),
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
            packet_path=packet_path,
            manifest_path=manifest_path,
        )
        for entry in manifest.entries
        for packet_path in (
            _machine_packet_path(entry),
            entry.packet_path,
        )
    )
    return tuple(source_paths)


def build_evidence_selection_shadow_review_study_batch(
    request: EvidenceSelectionShadowReviewStudyBatchRequest,
) -> EvidenceSelectionShadowReviewStudyBatchResult:
    """Run the single-packet shadow-review study pipeline for every batch entry."""

    _validate_suite_thresholds(request.suite_thresholds)
    output_dir_created = prepare_batch_output_dir(request.output_dir)
    entries: list[EvidenceSelectionShadowReviewStudyBatchEntryResult] = []
    published_entry_output_dirs: list[Path] = []
    try:
        protected_source_paths = (
            collect_evidence_selection_shadow_review_study_batch_source_paths(
                manifest=request.manifest,
                manifest_path=request.manifest_path,
            )
        )
        _validate_batch_artifact_source_collisions(
            output_dir=request.output_dir,
            manifest=request.manifest,
            manifest_path=request.manifest_path,
            source_paths=protected_source_paths,
        )
        for entry in request.manifest.entries:
            machine_packet_path = _resolve_packet_path(
                packet_path=_machine_packet_path(entry),
                manifest_path=request.manifest_path,
            )
            packet_path = _resolve_packet_path(
                packet_path=entry.packet_path,
                manifest_path=request.manifest_path,
            )
            entry_output_dir = request.output_dir / entry.output_subdir
            artifact_result = build_evidence_selection_shadow_review_study_artifacts(
                EvidenceSelectionShadowReviewStudyArtifactRequest(
                    machine_packet=_load_json_object(machine_packet_path),
                    packet=_load_json_object(packet_path),
                    machine_packet_path=machine_packet_path,
                    packet_path=packet_path,
                    protected_source_paths=protected_source_paths,
                    output_dir=entry_output_dir,
                    adjudication_note=entry.adjudication_note,
                    source_system=entry.source_system,
                    export_id=entry.export_id,
                    exported_at=entry.exported_at,
                    exporter_id=entry.exporter_id,
                    redaction_statement=entry.redaction_statement,
                    description=entry.description,
                ),
            )
            published_entry_output_dirs.append(entry_output_dir)
            entries.append(
                EvidenceSelectionShadowReviewStudyBatchEntryResult(
                    entry_id=entry.entry_id,
                    machine_packet_path=machine_packet_path,
                    packet_path=packet_path,
                    output_dir=entry_output_dir,
                    artifact_result=artifact_result,
                    gate_report=build_evidence_selection_shadow_review_study_gate_report(
                        input_path=artifact_result.bundle_path,
                        thresholds=request.thresholds,
                    ),
                ),
            )
        suite_gate = build_evidence_selection_shadow_review_study_batch_suite_gate(
            entries=tuple(entries),
            thresholds=request.suite_thresholds,
        )
    except Exception:
        try:
            rollback_published_batch_outputs(
                entry_output_dirs=published_entry_output_dirs,
                batch_output_dir=request.output_dir,
                remove_empty_batch_output_dir=output_dir_created,
            )
        except OSError as cleanup_error:
            msg = (
                "Shadow-review batch failed and published entry artifacts could "
                "not be rolled back."
            )
            raise RuntimeError(msg) from cleanup_error
        raise
    return EvidenceSelectionShadowReviewStudyBatchResult(
        batch_id=request.manifest.batch_id,
        output_dir=request.output_dir,
        generated_at=datetime.now(UTC).isoformat(),
        entries=tuple(entries),
        suite_gate=suite_gate,
    )


def build_evidence_selection_shadow_review_study_batch_suite_gate(
    *,
    entries: tuple[EvidenceSelectionShadowReviewStudyBatchEntryResult, ...],
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> JSONObject:
    """Evaluate whether a completed-packet batch is broad enough study evidence."""

    _validate_suite_thresholds(thresholds)
    effective_thresholds = _production_suite_thresholds(thresholds)
    passed_entry_count = sum(1 for entry in entries if entry.gate_passed)
    failed_entry_count = len(entries) - passed_entry_count
    passed_entry_rate = passed_entry_count / len(entries) if entries else 0.0
    passed_entries = tuple(entry for entry in entries if entry.gate_passed)
    total_selection_review_count = sum(
        entry.artifact_result.selection_review_count for entry in passed_entries
    )
    total_review_ranking_decision_count = sum(
        entry.artifact_result.review_ranking_decision_count
        for entry in passed_entries
    )
    quality_metrics = _batch_quality_metrics(passed_entries)
    selection_goals = _batch_selection_goals(passed_entries)
    review_ranking_goals, evidence_shapes = _batch_review_ranking_labels(passed_entries)
    source_outcomes = _batch_review_ranking_source_outcomes(passed_entries)
    source_run_ids, study_ids = _batch_study_identity_labels(passed_entries)
    summary: JSONObject = {
        "entry_count": len(entries),
        "passed_entry_count": passed_entry_count,
        "failed_entry_count": failed_entry_count,
        "passed_entry_rate": round(passed_entry_rate, 4),
        **quality_metrics.to_json(),
        "total_selection_review_count": total_selection_review_count,
        "total_review_ranking_decision_count": total_review_ranking_decision_count,
        "distinct_source_run_id_count": len(source_run_ids),
        "distinct_study_id_count": len(study_ids),
        "distinct_selection_goal_count": len(selection_goals),
        "distinct_review_ranking_goal_count": len(review_ranking_goals),
        "distinct_evidence_shape_count": len(evidence_shapes),
        "review_ranking_source_outcomes": {
            source_kind: sorted(source_outcomes[source_kind])
            for source_kind in _REVIEW_RANKING_SOURCE_KINDS
        },
    }
    blocking_reasons = _batch_suite_blocking_reasons(
        summary=summary,
        raw_passed_entry_rate=passed_entry_rate,
        raw_quality_metrics=quality_metrics,
        source_outcomes=source_outcomes,
        thresholds=effective_thresholds,
    )
    return {
        "passed": not blocking_reasons,
        "status": "passed" if not blocking_reasons else "failed",
        "thresholds": _suite_thresholds_to_json(effective_thresholds),
        "requested_thresholds": _suite_thresholds_to_json(thresholds),
        "production_floor_applied": (
            _suite_thresholds_to_json(effective_thresholds)
            != _suite_thresholds_to_json(thresholds)
        ),
        "summary": summary,
        "blocking_reasons": list(blocking_reasons),
    }


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
            require_positive_and_negative_per_source=False,
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


def _validate_suite_thresholds(
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> None:
    count_thresholds = {
        "min_entry_count": thresholds.min_entry_count,
        "min_passed_entry_count": thresholds.min_passed_entry_count,
        "max_failed_entry_count": thresholds.max_failed_entry_count,
        "min_total_selection_review_count": thresholds.min_total_selection_review_count,
        "min_total_review_ranking_decision_count": (
            thresholds.min_total_review_ranking_decision_count
        ),
        "min_distinct_source_run_ids": thresholds.min_distinct_source_run_ids,
        "min_distinct_study_ids": thresholds.min_distinct_study_ids,
        "min_distinct_selection_goals": thresholds.min_distinct_selection_goals,
        "min_distinct_review_ranking_goals": (
            thresholds.min_distinct_review_ranking_goals
        ),
        "min_distinct_evidence_shapes": thresholds.min_distinct_evidence_shapes,
    }
    for count_name, count_value in count_thresholds.items():
        if count_value < 0:
            msg = f"{count_name} must be non-negative."
            raise ValueError(msg)
    if thresholds.min_passed_entry_rate < 0 or thresholds.min_passed_entry_rate > 1:
        msg = "min_passed_entry_rate must be between 0 and 1."
        raise ValueError(msg)
    bounded_float_thresholds: dict[str, float] = {
        "min_suite_mean_precision": thresholds.min_suite_mean_precision,
        "min_suite_mean_recall": thresholds.min_suite_mean_recall,
        "max_suite_expected_calibration_error": (
            thresholds.max_suite_expected_calibration_error
        ),
    }
    for float_name, float_value in bounded_float_thresholds.items():
        if float_value < 0 or float_value > 1:
            msg = f"{float_name} must be between 0 and 1."
            raise ValueError(msg)
    if (
        thresholds.min_suite_mean_explanation_quality < _MIN_EXPLANATION_QUALITY
        or thresholds.min_suite_mean_explanation_quality > _MAX_EXPLANATION_QUALITY
    ):
        msg = "min_suite_mean_explanation_quality must be between 1 and 5."
        raise ValueError(msg)


def _production_suite_thresholds(
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> EvidenceSelectionShadowReviewStudyBatchSuiteThresholds:
    floors = _PRODUCTION_SUITE_THRESHOLD_FLOORS
    return EvidenceSelectionShadowReviewStudyBatchSuiteThresholds(
        min_entry_count=max(thresholds.min_entry_count, floors.min_entry_count),
        min_passed_entry_count=max(
            thresholds.min_passed_entry_count,
            floors.min_passed_entry_count,
        ),
        max_failed_entry_count=min(
            thresholds.max_failed_entry_count,
            floors.max_failed_entry_count,
        ),
        min_passed_entry_rate=max(
            thresholds.min_passed_entry_rate,
            floors.min_passed_entry_rate,
        ),
        min_suite_mean_precision=max(
            thresholds.min_suite_mean_precision,
            floors.min_suite_mean_precision,
        ),
        min_suite_mean_recall=max(
            thresholds.min_suite_mean_recall,
            floors.min_suite_mean_recall,
        ),
        min_suite_mean_explanation_quality=max(
            thresholds.min_suite_mean_explanation_quality,
            floors.min_suite_mean_explanation_quality,
        ),
        max_suite_expected_calibration_error=min(
            thresholds.max_suite_expected_calibration_error,
            floors.max_suite_expected_calibration_error,
        ),
        min_total_selection_review_count=max(
            thresholds.min_total_selection_review_count,
            floors.min_total_selection_review_count,
        ),
        min_total_review_ranking_decision_count=max(
            thresholds.min_total_review_ranking_decision_count,
            floors.min_total_review_ranking_decision_count,
        ),
        min_distinct_source_run_ids=max(
            thresholds.min_distinct_source_run_ids,
            floors.min_distinct_source_run_ids,
        ),
        min_distinct_study_ids=max(
            thresholds.min_distinct_study_ids,
            floors.min_distinct_study_ids,
        ),
        min_distinct_selection_goals=max(
            thresholds.min_distinct_selection_goals,
            floors.min_distinct_selection_goals,
        ),
        min_distinct_review_ranking_goals=max(
            thresholds.min_distinct_review_ranking_goals,
            floors.min_distinct_review_ranking_goals,
        ),
        min_distinct_evidence_shapes=max(
            thresholds.min_distinct_evidence_shapes,
            floors.min_distinct_evidence_shapes,
        ),
    )


def _suite_thresholds_to_json(
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> JSONObject:
    return {
        "min_entry_count": thresholds.min_entry_count,
        "min_passed_entry_count": thresholds.min_passed_entry_count,
        "max_failed_entry_count": thresholds.max_failed_entry_count,
        "min_passed_entry_rate": thresholds.min_passed_entry_rate,
        "min_suite_mean_precision": thresholds.min_suite_mean_precision,
        "min_suite_mean_recall": thresholds.min_suite_mean_recall,
        "min_suite_mean_explanation_quality": (
            thresholds.min_suite_mean_explanation_quality
        ),
        "max_suite_expected_calibration_error": (
            thresholds.max_suite_expected_calibration_error
        ),
        "min_total_selection_review_count": thresholds.min_total_selection_review_count,
        "min_total_review_ranking_decision_count": (
            thresholds.min_total_review_ranking_decision_count
        ),
        "min_distinct_source_run_ids": thresholds.min_distinct_source_run_ids,
        "min_distinct_study_ids": thresholds.min_distinct_study_ids,
        "min_distinct_selection_goals": thresholds.min_distinct_selection_goals,
        "min_distinct_review_ranking_goals": (
            thresholds.min_distinct_review_ranking_goals
        ),
        "min_distinct_evidence_shapes": thresholds.min_distinct_evidence_shapes,
    }


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


def _machine_packet_path(
    entry: EvidenceSelectionShadowReviewStudyBatchEntry,
) -> Path:
    return entry.machine_packet_path or machine_packet_sidecar_path(entry.packet_path)


def _validate_batch_artifact_source_collisions(
    *,
    output_dir: Path,
    manifest: EvidenceSelectionShadowReviewStudyBatchManifest,
    manifest_path: Path | None,
    source_paths: tuple[Path, ...],
) -> None:
    for entry in manifest.entries:
        entry_output_dir = output_dir / entry.output_subdir
        for filename in _ENTRY_ARTIFACT_FILENAMES:
            output_path = entry_output_dir / filename
            for source_path in source_paths:
                if paths_alias(output_path, source_path):
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
        and paths_alias(source_path, manifest_path)
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


def _batch_selection_goals(
    entries: tuple[EvidenceSelectionShadowReviewStudyBatchEntryResult, ...],
) -> set[str]:
    goals: set[str] = set()
    for entry in entries:
        gate = _object_value(entry.gate_report, "gate")
        reports = gate.get("selection_reports")
        if not isinstance(reports, list):
            continue
        for report in reports:
            if not isinstance(report, dict):
                continue
            if goal := _normalized_label(report.get("goal")):
                goals.add(goal)
    return goals


def _batch_review_ranking_labels(
    entries: tuple[EvidenceSelectionShadowReviewStudyBatchEntryResult, ...],
) -> tuple[set[str], set[str]]:
    goals: set[str] = set()
    evidence_shapes: set[str] = set()
    for entry in entries:
        study_input = EvidenceSelectionExpertStudyInput.model_validate(
            _load_json_object(entry.artifact_result.bundle_path),
        )
        for decision in study_input.review_ranking.decisions:
            if goal := _normalized_label(decision.goal):
                goals.add(goal)
            if evidence_shape := _normalized_label(decision.evidence_shape):
                evidence_shapes.add(evidence_shape)
    return goals, evidence_shapes


def _batch_review_ranking_source_outcomes(
    entries: tuple[EvidenceSelectionShadowReviewStudyBatchEntryResult, ...],
) -> dict[str, set[str]]:
    source_outcomes = {
        source_kind: set[str]() for source_kind in _REVIEW_RANKING_SOURCE_KINDS
    }
    for entry in entries:
        study_input = EvidenceSelectionExpertStudyInput.model_validate(
            _load_json_object(entry.artifact_result.bundle_path),
        )
        for decision in study_input.review_ranking.decisions:
            source_outcomes[decision.source_kind].add(decision.outcome)
    return source_outcomes


def _batch_quality_metrics(
    entries: tuple[EvidenceSelectionShadowReviewStudyBatchEntryResult, ...],
) -> _BatchQualityMetrics:
    total_review_count = 0
    weighted_precision = 0.0
    weighted_recall = 0.0
    weighted_explanation_quality = 0.0
    max_expected_calibration_error = 0.0
    for entry in entries:
        gate = _object_value(entry.gate_report, "gate")
        selection_summary = _object_value(gate, "selection_summary")
        review_count = _int_value(selection_summary.get("review_count"))
        if review_count > 0:
            total_review_count += review_count
            weighted_precision += (
                _float_value(selection_summary.get("mean_precision")) * review_count
            )
            weighted_recall += (
                _float_value(selection_summary.get("mean_recall")) * review_count
            )
            weighted_explanation_quality += (
                _float_value(selection_summary.get("mean_explanation_quality"))
                * review_count
            )
        review_ranking_gate = _object_value(gate, "review_ranking_gate")
        calibration = _object_value(review_ranking_gate, "calibration")
        max_expected_calibration_error = max(
            max_expected_calibration_error,
            _float_value(calibration.get("expected_calibration_error")),
        )
    return _BatchQualityMetrics(
        suite_mean_precision=_ratio(
            numerator=weighted_precision,
            denominator=total_review_count,
        ),
        suite_mean_recall=_ratio(
            numerator=weighted_recall,
            denominator=total_review_count,
        ),
        suite_mean_explanation_quality=_ratio(
            numerator=weighted_explanation_quality,
            denominator=total_review_count,
        ),
        max_review_ranking_expected_calibration_error=max_expected_calibration_error,
    )


def _batch_study_identity_labels(
    entries: tuple[EvidenceSelectionShadowReviewStudyBatchEntryResult, ...],
) -> tuple[set[str], set[str]]:
    source_run_ids: set[str] = set()
    study_ids: set[str] = set()
    for entry in entries:
        study_input = EvidenceSelectionExpertStudyInput.model_validate(
            _load_json_object(entry.artifact_result.bundle_path),
        )
        if study_id := _identity_label(study_input.study_id):
            study_ids.add(study_id)
        for selection_review in study_input.selection_reviews:
            if source_run_id := _identity_label(selection_review.run_id):
                source_run_ids.add(source_run_id)
    return source_run_ids, study_ids


def _batch_suite_blocking_reasons(
    *,
    summary: JSONObject,
    raw_passed_entry_rate: float,
    raw_quality_metrics: _BatchQualityMetrics,
    source_outcomes: Mapping[str, set[str]],
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> tuple[str, ...]:
    return (
        *_batch_suite_entry_blocking_reasons(
            summary=summary,
            raw_passed_entry_rate=raw_passed_entry_rate,
            thresholds=thresholds,
        ),
        *_batch_suite_quality_blocking_reasons(
            raw_quality_metrics=raw_quality_metrics,
            thresholds=thresholds,
        ),
        *_batch_suite_sample_blocking_reasons(
            summary=summary,
            thresholds=thresholds,
        ),
        *_batch_suite_identity_blocking_reasons(
            summary=summary,
            thresholds=thresholds,
        ),
        *_batch_suite_diversity_blocking_reasons(
            summary=summary,
            thresholds=thresholds,
        ),
        *_batch_suite_source_outcome_blocking_reasons(
            source_outcomes=source_outcomes,
        ),
    )


def _batch_suite_entry_blocking_reasons(
    *,
    summary: JSONObject,
    raw_passed_entry_rate: float,
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if _int_value(summary.get("entry_count")) < thresholds.min_entry_count:
        reasons.append(
            "At least "
            f"{thresholds.min_entry_count} batch entries are required for "
            "production study evidence.",
        )
    if _int_value(summary.get("passed_entry_count")) < thresholds.min_passed_entry_count:
        reasons.append(
            "At least "
            f"{thresholds.min_passed_entry_count} batch entries must pass their "
            "expert-study gates.",
        )
    if _int_value(summary.get("failed_entry_count")) > thresholds.max_failed_entry_count:
        reasons.append(
            "No more than "
            f"{thresholds.max_failed_entry_count} batch entries may fail their "
            "expert-study gates.",
        )
    if raw_passed_entry_rate < thresholds.min_passed_entry_rate:
        reasons.append(
            "Batch passed-entry rate must be at least "
            f"{thresholds.min_passed_entry_rate:.4f}.",
        )
    return tuple(reasons)


def _batch_suite_quality_blocking_reasons(
    *,
    raw_quality_metrics: _BatchQualityMetrics,
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if raw_quality_metrics.suite_mean_precision < thresholds.min_suite_mean_precision:
        reasons.append(
            "Batch suite mean precision is below target: "
            f"{raw_quality_metrics.suite_mean_precision:.6f} < "
            f"{thresholds.min_suite_mean_precision:.6f}.",
        )
    if raw_quality_metrics.suite_mean_recall < thresholds.min_suite_mean_recall:
        reasons.append(
            "Batch suite mean recall is below target: "
            f"{raw_quality_metrics.suite_mean_recall:.6f} < "
            f"{thresholds.min_suite_mean_recall:.6f}.",
        )
    if (
        raw_quality_metrics.suite_mean_explanation_quality
        < thresholds.min_suite_mean_explanation_quality
    ):
        reasons.append(
            "Batch suite mean explanation quality is below target: "
            f"{raw_quality_metrics.suite_mean_explanation_quality:.6f} < "
            f"{thresholds.min_suite_mean_explanation_quality:.6f}.",
        )
    if (
        raw_quality_metrics.max_review_ranking_expected_calibration_error
        > thresholds.max_suite_expected_calibration_error
    ):
        observed = raw_quality_metrics.max_review_ranking_expected_calibration_error
        reasons.append(
            "Batch review-ranking calibration ECE is above target: "
            f"{observed:.6f} > "
            f"{thresholds.max_suite_expected_calibration_error:.6f}.",
        )
    return tuple(reasons)


def _batch_suite_sample_blocking_reasons(
    *,
    summary: JSONObject,
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if (
        _int_value(summary.get("total_selection_review_count"))
        < thresholds.min_total_selection_review_count
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_total_selection_review_count} total selection reviews "
            "are required across passed batch entries.",
        )
    if (
        _int_value(summary.get("total_review_ranking_decision_count"))
        < thresholds.min_total_review_ranking_decision_count
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_total_review_ranking_decision_count} total "
            "review-ranking decisions are required across passed batch entries.",
        )
    return tuple(reasons)


def _batch_suite_identity_blocking_reasons(
    *,
    summary: JSONObject,
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if (
        _int_value(summary.get("distinct_source_run_id_count"))
        < thresholds.min_distinct_source_run_ids
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_distinct_source_run_ids} distinct source run IDs "
            "are required across passed batch entries.",
        )
    if (
        _int_value(summary.get("distinct_study_id_count"))
        < thresholds.min_distinct_study_ids
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_distinct_study_ids} distinct study IDs are required "
            "across passed batch entries.",
        )
    return tuple(reasons)


def _batch_suite_diversity_blocking_reasons(
    *,
    summary: JSONObject,
    thresholds: EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if (
        _int_value(summary.get("distinct_selection_goal_count"))
        < thresholds.min_distinct_selection_goals
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_distinct_selection_goals} distinct selection goals "
            "are required across the batch.",
        )
    if (
        _int_value(summary.get("distinct_review_ranking_goal_count"))
        < thresholds.min_distinct_review_ranking_goals
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_distinct_review_ranking_goals} distinct review-ranking "
            "goals are required across the batch.",
        )
    if (
        _int_value(summary.get("distinct_evidence_shape_count"))
        < thresholds.min_distinct_evidence_shapes
    ):
        reasons.append(
            "At least "
            f"{thresholds.min_distinct_evidence_shapes} distinct evidence shapes "
            "are required across the batch.",
        )
    return tuple(reasons)


def _batch_suite_source_outcome_blocking_reasons(
    *,
    source_outcomes: Mapping[str, set[str]],
) -> tuple[str, ...]:
    return tuple(
        f"At least one {outcome} reviewer outcome is required for source kind "
        f"{source_kind} across passed batch entries."
        for source_kind in _REVIEW_RANKING_SOURCE_KINDS
        for outcome in _REVIEW_RANKING_OUTCOMES
        if outcome not in source_outcomes.get(source_kind, set())
    )


def _object_value(payload: Mapping[str, object], key: str) -> JSONObject:
    value = payload.get(key)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _normalized_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", value.strip().casefold())
    normalized = " ".join(normalized.split())
    return normalized or None


def _identity_label(value: object) -> str | None:
    text = str(value).strip()
    return text or None


def _ratio(*, numerator: float, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _float_value(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


__all__ = [
    "EvidenceSelectionShadowReviewStudyBatchEntry",
    "EvidenceSelectionShadowReviewStudyBatchEntryResult",
    "EvidenceSelectionShadowReviewStudyBatchManifest",
    "EvidenceSelectionShadowReviewStudyBatchRequest",
    "EvidenceSelectionShadowReviewStudyBatchResult",
    "EvidenceSelectionShadowReviewStudyBatchSuiteThresholds",
    "EvidenceSelectionShadowReviewStudyBatchThresholds",
    "build_evidence_selection_shadow_review_study_batch",
    "build_evidence_selection_shadow_review_study_batch_suite_gate",
    "build_evidence_selection_shadow_review_study_gate_report",
    "collect_evidence_selection_shadow_review_study_batch_source_paths",
    "load_evidence_selection_shadow_review_study_batch_manifest",
]
