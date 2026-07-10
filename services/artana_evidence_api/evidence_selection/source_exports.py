"""Typed source export envelopes for evidence-selection expert studies."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionReviewInput,
    ReviewRankingCalibrationStudyInput,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

EvidenceSelectionReviewExportSchemaVersion = Literal[
    "evidence_selection_review_export.v1"
]
ReviewRankingCalibrationExportSchemaVersion = Literal[
    "evidence_selection_review_ranking_export.v1"
]
SOURCE_EXPORTED_AT_FORMAT = "YYYY-MM-DDTHH:MM:SSZ"
_CANONICAL_SOURCE_EXPORTED_AT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
)


class EvidenceSelectionSourceExportIdentity(BaseModel):
    """Shared source identity fields embedded in expert-study source exports."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_system: str = Field(min_length=1)
    export_id: str = Field(min_length=1)
    exported_at: datetime
    exporter_id: str = Field(min_length=1)
    redaction_statement: str = Field(min_length=1)

    @field_validator(
        "source_system",
        "export_id",
        "exporter_id",
        "redaction_statement",
    )
    @classmethod
    def _reject_nonliteral_identity_text(cls, value: str) -> str:
        if not value.strip():
            msg = "source export identity fields must be nonblank"
            raise ValueError(msg)
        if value != value.strip():
            msg = (
                "source export identity fields must not have leading or "
                "trailing whitespace"
            )
            raise ValueError(msg)
        return value

    @field_validator("exported_at", mode="before")
    @classmethod
    def _accept_json_exported_at(cls, value: object) -> object:
        if isinstance(value, datetime | str):
            return parse_canonical_source_exported_at(value)
        return value


class EvidenceSelectionReviewExport(EvidenceSelectionSourceExportIdentity):
    """Self-describing export of expert-labeled selection reviews."""

    schema_version: EvidenceSelectionReviewExportSchemaVersion
    selection_reviews: tuple[EvidenceSelectionReviewInput, ...]

    @field_validator("selection_reviews", mode="before")
    @classmethod
    def _accept_json_selection_review_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class ReviewRankingCalibrationExport(EvidenceSelectionSourceExportIdentity):
    """Self-describing export of expert review-ranking calibration decisions."""

    schema_version: ReviewRankingCalibrationExportSchemaVersion
    review_ranking: ReviewRankingCalibrationStudyInput


def source_export_identity_from_export(
    export: EvidenceSelectionSourceExportIdentity,
) -> EvidenceSelectionSourceExportIdentity:
    """Return only the source identity fields from an export envelope."""

    return EvidenceSelectionSourceExportIdentity(
        source_system=export.source_system,
        export_id=export.export_id,
        exported_at=export.exported_at,
        exporter_id=export.exporter_id,
        redaction_statement=export.redaction_statement,
    )


def ensure_matching_source_export_identity(
    *,
    selection_export: EvidenceSelectionReviewExport,
    ranking_export: ReviewRankingCalibrationExport,
) -> EvidenceSelectionSourceExportIdentity:
    """Return matched source identity or fail closed on drift."""

    selection_identity = source_export_identity_from_export(selection_export)
    ranking_identity = source_export_identity_from_export(ranking_export)
    if selection_identity != ranking_identity:
        msg = (
            "Selection-review and review-ranking source export identity fields "
            "must match before building an expert-study bundle."
        )
        raise ValueError(msg)
    return selection_identity


def parse_canonical_source_exported_at(
    value: datetime | str,
    *,
    field_name: str = "source export exported_at",
) -> datetime:
    """Parse canonical source-export timestamps without lossy normalization."""

    if isinstance(value, str):
        parsed = _parse_source_exported_at_string(value=value, field_name=field_name)
    else:
        parsed = value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = (
            f"{field_name} must include a timezone and use canonical UTC "
            f"format {SOURCE_EXPORTED_AT_FORMAT}."
        )
        raise ValueError(msg)
    if parsed.utcoffset() != timedelta(0):
        msg = f"{field_name} must be canonical UTC."
        raise ValueError(msg)
    if parsed.microsecond != 0:
        msg = (
            f"{field_name} must use canonical UTC format "
            f"{SOURCE_EXPORTED_AT_FORMAT}."
        )
        raise ValueError(msg)
    if (
        isinstance(value, str)
        and _CANONICAL_SOURCE_EXPORTED_AT_RE.fullmatch(value) is None
    ):
        msg = (
            f"{field_name} must use canonical UTC format "
            f"{SOURCE_EXPORTED_AT_FORMAT}."
        )
        raise ValueError(msg)
    return parsed.astimezone(UTC)


def _parse_source_exported_at_string(*, value: str, field_name: str) -> datetime:
    normalized_value = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized_value)
    except ValueError as exc:
        msg = (
            f"{field_name} must be valid ISO-8601 and use canonical UTC "
            f"format {SOURCE_EXPORTED_AT_FORMAT}."
        )
        raise ValueError(msg) from exc


__all__ = [
    "EvidenceSelectionReviewExport",
    "EvidenceSelectionReviewExportSchemaVersion",
    "EvidenceSelectionSourceExportIdentity",
    "ReviewRankingCalibrationExport",
    "ReviewRankingCalibrationExportSchemaVersion",
    "ensure_matching_source_export_identity",
    "parse_canonical_source_exported_at",
    "source_export_identity_from_export",
]
