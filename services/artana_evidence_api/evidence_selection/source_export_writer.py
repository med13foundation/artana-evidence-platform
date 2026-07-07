"""Write self-describing evidence-selection expert-study source exports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from artana_evidence_api.evidence_selection.source_exports import (
    EvidenceSelectionReviewExport,
    EvidenceSelectionSourceExportIdentity,
    ReviewRankingCalibrationExport,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionReviewInput,
    ReviewRankingCalibrationStudyInput,
)
from pydantic import BaseModel, ConfigDict, field_validator


class EvidenceSelectionSourceExportWriterError(ValueError):
    """Raised when source-export files cannot be written safely."""


@dataclass(frozen=True, slots=True)
class EvidenceSelectionSourceExportWriteRequest:
    """Input files, output files, and identity for writing source exports."""

    selection_reviews_path: Path
    review_ranking_path: Path
    selection_export_path: Path
    review_ranking_export_path: Path
    source_system: str
    export_id: str
    exported_at: datetime | str
    exporter_id: str
    redaction_statement: str


@dataclass(frozen=True, slots=True)
class EvidenceSelectionSourceExportWriteResult:
    """Counts and output paths produced by the source-export writer."""

    selection_export_path: Path
    review_ranking_export_path: Path
    selection_review_count: int
    review_ranking_decision_count: int


@dataclass(frozen=True, slots=True)
class _PreparedOutput:
    """Rollback information for one final output path."""

    final_path: Path
    backup_path: Path | None


class _SelectionReviewInputEnvelope(BaseModel):
    """Strict input envelope for collected selection-review labels."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    selection_reviews: tuple[EvidenceSelectionReviewInput, ...]

    @field_validator("selection_reviews", mode="before")
    @classmethod
    def _accept_json_selection_review_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


def write_evidence_selection_source_exports(
    request: EvidenceSelectionSourceExportWriteRequest,
) -> EvidenceSelectionSourceExportWriteResult:
    """Write matched selection-review and review-ranking source exports."""

    validate_evidence_selection_source_export_output_paths(
        selection_export_path=request.selection_export_path,
        review_ranking_export_path=request.review_ranking_export_path,
        source_paths=(request.selection_reviews_path, request.review_ranking_path),
    )
    selection_reviews = _load_selection_reviews(request.selection_reviews_path)
    review_ranking = _load_review_ranking(request.review_ranking_path)
    identity = _source_identity(request)
    selection_export = EvidenceSelectionReviewExport(
        schema_version="evidence_selection_review_export.v1",
        source_system=identity.source_system,
        export_id=identity.export_id,
        exported_at=identity.exported_at,
        exporter_id=identity.exporter_id,
        redaction_statement=identity.redaction_statement,
        selection_reviews=selection_reviews,
    )
    review_ranking_export = ReviewRankingCalibrationExport(
        schema_version="evidence_selection_review_ranking_export.v1",
        source_system=identity.source_system,
        export_id=identity.export_id,
        exported_at=identity.exported_at,
        exporter_id=identity.exporter_id,
        redaction_statement=identity.redaction_statement,
        review_ranking=review_ranking,
    )
    _write_paired_json_models(
        selection_export_path=request.selection_export_path,
        selection_export=selection_export,
        review_ranking_export_path=request.review_ranking_export_path,
        review_ranking_export=review_ranking_export,
    )
    return EvidenceSelectionSourceExportWriteResult(
        selection_export_path=request.selection_export_path,
        review_ranking_export_path=request.review_ranking_export_path,
        selection_review_count=len(selection_reviews),
        review_ranking_decision_count=len(review_ranking.decisions),
    )


def validate_evidence_selection_source_export_output_paths(
    *,
    selection_export_path: Path,
    review_ranking_export_path: Path,
    source_paths: tuple[Path, ...],
) -> None:
    """Reject source-export outputs that would overwrite inputs or each other."""

    resolved_selection_output = selection_export_path.resolve(strict=False)
    resolved_ranking_output = review_ranking_export_path.resolve(strict=False)
    if resolved_selection_output == resolved_ranking_output:
        msg = "Selection-review and review-ranking export outputs must be different files."
        raise EvidenceSelectionSourceExportWriterError(msg)
    for source_path in source_paths:
        resolved_source_path = source_path.resolve(strict=False)
        if resolved_selection_output == resolved_source_path:
            msg = (
                "Selection-review export output must not overwrite source input: "
                f"{selection_export_path} matches {source_path}."
            )
            raise EvidenceSelectionSourceExportWriterError(msg)
        if resolved_ranking_output == resolved_source_path:
            msg = (
                "Review-ranking export output must not overwrite source input: "
                f"{review_ranking_export_path} matches {source_path}."
            )
            raise EvidenceSelectionSourceExportWriterError(msg)


def _source_identity(
    request: EvidenceSelectionSourceExportWriteRequest,
) -> EvidenceSelectionSourceExportIdentity:
    return EvidenceSelectionSourceExportIdentity.model_validate(
        {
            "source_system": request.source_system,
            "export_id": request.export_id,
            "exported_at": request.exported_at,
            "exporter_id": request.exporter_id,
            "redaction_statement": request.redaction_statement,
        },
    )


def _load_selection_reviews(path: Path) -> tuple[EvidenceSelectionReviewInput, ...]:
    payload = _load_json_object(path)
    envelope = _SelectionReviewInputEnvelope.model_validate(payload)
    return envelope.selection_reviews


def _load_review_ranking(path: Path) -> ReviewRankingCalibrationStudyInput:
    payload = _load_json_object(path)
    return ReviewRankingCalibrationStudyInput.model_validate(payload)


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        source_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Unable to read source-export input {path}: {exc}"
        raise EvidenceSelectionSourceExportWriterError(msg) from exc
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        msg = f"{path} is not valid JSON: {exc.msg}."
        raise EvidenceSelectionSourceExportWriterError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"{path} does not contain a JSON object."
        raise EvidenceSelectionSourceExportWriterError(msg)
    return cast("dict[str, object]", payload)


def _write_paired_json_models(
    *,
    selection_export_path: Path,
    selection_export: BaseModel,
    review_ranking_export_path: Path,
    review_ranking_export: BaseModel,
) -> None:
    selection_payload = _json_model_text(selection_export)
    review_ranking_payload = _json_model_text(review_ranking_export)
    selection_temp_path: Path | None = None
    review_ranking_temp_path: Path | None = None
    prepared_outputs: list[_PreparedOutput] = []
    try:
        _preflight_output_file(selection_export_path)
        _preflight_output_file(review_ranking_export_path)
        selection_temp_path = _write_temp_sibling(
            final_path=selection_export_path,
            payload=selection_payload,
        )
        review_ranking_temp_path = _write_temp_sibling(
            final_path=review_ranking_export_path,
            payload=review_ranking_payload,
        )
        prepared_outputs.append(_prepare_output_for_replace(selection_export_path))
        prepared_outputs.append(_prepare_output_for_replace(review_ranking_export_path))
        selection_temp_path.replace(selection_export_path)
        selection_temp_path = None
        review_ranking_temp_path.replace(review_ranking_export_path)
        review_ranking_temp_path = None
        _discard_prepared_output_backups(prepared_outputs)
        prepared_outputs = []
    except (OSError, EvidenceSelectionSourceExportWriterError) as exc:
        _remove_temp_file(selection_temp_path)
        _remove_temp_file(review_ranking_temp_path)
        _rollback_prepared_outputs(prepared_outputs)
        msg = f"Unable to write paired source exports: {exc}"
        raise EvidenceSelectionSourceExportWriterError(msg) from exc


def _json_model_text(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2) + "\n"


def _preflight_output_file(path: Path) -> None:
    if path.exists() and path.is_dir():
        msg = f"{path} is a directory, not a writable source-export file."
        raise EvidenceSelectionSourceExportWriterError(msg)
    if path.parent.exists() and not path.parent.is_dir():
        msg = f"{path.parent} is not a directory."
        raise EvidenceSelectionSourceExportWriterError(msg)


def _write_temp_sibling(*, final_path: Path, payload: str) -> Path:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = final_path.with_name(f".{final_path.name}.tmp-{uuid4().hex}")
    temp_path.write_text(payload, encoding="utf-8")
    return temp_path


def _prepare_output_for_replace(final_path: Path) -> _PreparedOutput:
    if not final_path.exists():
        return _PreparedOutput(final_path=final_path, backup_path=None)
    backup_path = final_path.with_name(f".{final_path.name}.bak-{uuid4().hex}")
    final_path.replace(backup_path)
    return _PreparedOutput(final_path=final_path, backup_path=backup_path)


def _discard_prepared_output_backups(prepared_outputs: list[_PreparedOutput]) -> None:
    for prepared_output in prepared_outputs:
        _remove_temp_file(prepared_output.backup_path)


def _rollback_prepared_outputs(prepared_outputs: list[_PreparedOutput]) -> None:
    for prepared_output in reversed(prepared_outputs):
        if prepared_output.backup_path is None:
            _remove_temp_file(prepared_output.final_path)
            continue
        _remove_temp_file(prepared_output.final_path)
        try:
            prepared_output.backup_path.replace(prepared_output.final_path)
        except OSError:
            continue


def _remove_temp_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


__all__ = [
    "EvidenceSelectionSourceExportWriteRequest",
    "EvidenceSelectionSourceExportWriteResult",
    "EvidenceSelectionSourceExportWriterError",
    "validate_evidence_selection_source_export_output_paths",
    "write_evidence_selection_source_exports",
]
