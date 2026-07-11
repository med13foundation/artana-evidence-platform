"""Provenance manifest validation for evidence-selection expert studies."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator

SOURCE_EXPORTED_AT_FORMAT = "YYYY-MM-DDTHH:MM:SSZ"
_CANONICAL_SOURCE_EXPORTED_AT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
)

EvidenceSelectionExpertStudySourceArtifactKind = Literal[
    "selection_review_export",
    "review_ranking_export",
    "adjudication_log",
]

_SOURCE_ARTIFACT_KINDS: tuple[EvidenceSelectionExpertStudySourceArtifactKind, ...] = (
    "selection_review_export",
    "review_ranking_export",
    "adjudication_log",
)
_REQUIRED_SOURCE_ARTIFACT_KINDS: tuple[
    EvidenceSelectionExpertStudySourceArtifactKind,
    ...,
] = (
    "selection_review_export",
    "review_ranking_export",
)


def validate_source_identity_text(value: str) -> str:
    """Return literal nonblank identity text or reject lossy normalization."""

    if not value.strip():
        msg = "source identity fields must be nonblank"
        raise ValueError(msg)
    if value != value.strip():
        msg = "source identity fields must not have leading or trailing whitespace"
        raise ValueError(msg)
    return value


def parse_canonical_source_exported_at(
    value: datetime | str,
    *,
    field_name: str = "source exported_at",
) -> datetime:
    """Parse canonical source timestamps without lossy normalization."""

    parsed = (
        _parse_source_exported_at_string(value=value, field_name=field_name)
        if isinstance(value, str)
        else value
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = (
            f"{field_name} must include a timezone and use canonical UTC "
            f"format {SOURCE_EXPORTED_AT_FORMAT}."
        )
        raise ValueError(msg)
    if parsed.utcoffset() != timedelta(0):
        msg = f"{field_name} must be canonical UTC."
        raise ValueError(msg)
    if parsed.microsecond != 0 or (
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


class EvidenceSelectionExpertStudySourceArtifact(BaseModel):
    """One immutable source artifact backing an expert/shadow study bundle."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    artifact_id: str = Field(min_length=1)
    artifact_kind: EvidenceSelectionExpertStudySourceArtifactKind
    uri: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("artifact_id", "uri")
    @classmethod
    def _strip_nonblank_artifact_text(cls, value: str) -> str:
        return _strip_nonblank_text(value)


class EvidenceSelectionExpertStudySourceManifest(BaseModel):
    """Auditable export manifest for an expert/shadow study bundle."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_system: str = Field(min_length=1)
    export_id: str = Field(min_length=1)
    exported_at: datetime
    exporter_id: str = Field(min_length=1)
    redaction_statement: str = Field(min_length=1)
    source_artifacts: tuple[EvidenceSelectionExpertStudySourceArtifact, ...]
    selection_review_run_ids: tuple[UUID, ...]
    review_ranking_decision_keys: tuple[str, ...]
    reviewer_roster: tuple[str, ...]

    @field_validator(
        "source_system",
        "export_id",
        "exporter_id",
        "redaction_statement",
    )
    @classmethod
    def _validate_manifest_identity_text(cls, value: str) -> str:
        return validate_source_identity_text(value)

    @field_validator("exported_at", mode="before")
    @classmethod
    def _accept_json_exported_at(cls, value: object) -> object:
        if isinstance(value, datetime | str):
            return parse_canonical_source_exported_at(
                value,
                field_name="source manifest exported_at",
            )
        return value

    @field_validator(
        "source_artifacts",
        "review_ranking_decision_keys",
        "reviewer_roster",
        mode="before",
    )
    @classmethod
    def _accept_json_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("selection_review_run_ids", mode="before")
    @classmethod
    def _accept_json_run_id_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(UUID(item) if isinstance(item, str) else item for item in value)
        return value


def build_evidence_selection_provenance_summary(
    *,
    source_manifest: EvidenceSelectionExpertStudySourceManifest | None,
    selection_run_ids: tuple[UUID, ...],
    review_ranking_decision_keys: tuple[str, ...],
    reviewer_ids: set[str],
) -> JSONObject:
    """Return stable provenance metrics for a study source manifest."""

    duplicate_selection_run_ids = _duplicate_uuid_strings(selection_run_ids)
    duplicate_review_ranking_decision_keys = _duplicate_strings(
        review_ranking_decision_keys,
    )
    expected_selection_run_id_set = set(selection_run_ids)
    expected_decision_key_set = set(review_ranking_decision_keys)
    if source_manifest is None:
        return _missing_source_manifest_summary(
            expected_selection_run_ids=expected_selection_run_id_set,
            duplicate_selection_run_ids=duplicate_selection_run_ids,
            expected_decision_keys=expected_decision_key_set,
            duplicate_review_ranking_decision_keys=(
                duplicate_review_ranking_decision_keys
            ),
            expected_reviewer_ids=reviewer_ids,
        )
    return _present_source_manifest_summary(
        source_manifest=source_manifest,
        expected_selection_run_id_set=expected_selection_run_id_set,
        duplicate_selection_run_ids=duplicate_selection_run_ids,
        expected_decision_key_set=expected_decision_key_set,
        duplicate_review_ranking_decision_keys=(
            duplicate_review_ranking_decision_keys
        ),
        expected_reviewer_ids=reviewer_ids,
    )


def source_manifest_blocking_reasons(
    *,
    provenance_summary: JSONObject,
    require_source_manifest: bool,
    min_source_artifact_count: int,
) -> tuple[str, ...]:
    """Return fail-closed reasons for source-manifest provenance gaps."""

    if (
        not require_source_manifest
        and provenance_summary.get("source_manifest_present") is not True
    ):
        return ()

    reasons: list[str] = []
    if (
        require_source_manifest
        and provenance_summary.get("source_manifest_present") is not True
    ):
        reasons.append(
            "A source manifest is required before expert/shadow study evidence "
            "can support production readiness.",
        )
    reasons.extend(
        _source_artifact_blocking_reasons(
            provenance_summary=provenance_summary,
            min_source_artifact_count=min_source_artifact_count,
        ),
    )
    reasons.extend(_source_selection_blocking_reasons(provenance_summary))
    reasons.extend(_source_ranking_blocking_reasons(provenance_summary))
    if _int_from_json(provenance_summary, "unknown_reviewer_id_count") > 0:
        reasons.append(
            "Every study reviewer ID must be present in the source manifest "
            "reviewer roster.",
        )
    return tuple(reasons)


def _missing_source_manifest_summary(
    *,
    expected_selection_run_ids: set[UUID],
    duplicate_selection_run_ids: tuple[str, ...],
    expected_decision_keys: set[str],
    duplicate_review_ranking_decision_keys: tuple[str, ...],
    expected_reviewer_ids: set[str],
) -> JSONObject:
    return {
        "source_manifest_present": False,
        "source_system": None,
        "export_id": None,
        "exporter_id": None,
        "exported_at": None,
        "artifact_count": 0,
        "source_artifact_kind_counts": _empty_source_artifact_kind_counts(),
        "missing_required_source_artifact_kinds": list(
            _REQUIRED_SOURCE_ARTIFACT_KINDS,
        ),
        "duplicate_source_artifact_id_count": 0,
        "duplicate_source_artifact_uri_count": 0,
        "duplicate_source_artifact_sha256_count": 0,
        "selection_review_run_id_count": 0,
        "duplicate_selection_run_id_count": len(duplicate_selection_run_ids),
        "duplicate_selection_run_ids": list(duplicate_selection_run_ids),
        "duplicate_manifest_selection_run_id_count": 0,
        "missing_selection_run_id_count": len(expected_selection_run_ids),
        "extra_selection_run_id_count": 0,
        "missing_selection_run_ids": [
            str(run_id) for run_id in sorted(expected_selection_run_ids)
        ],
        "extra_selection_run_ids": [],
        "review_ranking_decision_key_count": 0,
        "duplicate_review_ranking_decision_key_count": (
            len(duplicate_review_ranking_decision_keys)
        ),
        "duplicate_review_ranking_decision_keys": list(
            duplicate_review_ranking_decision_keys,
        ),
        "duplicate_manifest_review_ranking_decision_key_count": 0,
        "missing_review_ranking_decision_key_count": len(expected_decision_keys),
        "extra_review_ranking_decision_key_count": 0,
        "missing_review_ranking_decision_keys": sorted(expected_decision_keys),
        "extra_review_ranking_decision_keys": [],
        "reviewer_roster_count": 0,
        "unknown_reviewer_id_count": len(expected_reviewer_ids),
        "unknown_reviewer_ids": sorted(expected_reviewer_ids),
        "redaction_statement_present": False,
    }


def _present_source_manifest_summary(
    *,
    source_manifest: EvidenceSelectionExpertStudySourceManifest,
    expected_selection_run_id_set: set[UUID],
    duplicate_selection_run_ids: tuple[str, ...],
    expected_decision_key_set: set[str],
    duplicate_review_ranking_decision_keys: tuple[str, ...],
    expected_reviewer_ids: set[str],
) -> JSONObject:
    manifest_selection_run_ids = set(source_manifest.selection_review_run_ids)
    manifest_decision_keys = set(source_manifest.review_ranking_decision_keys)
    manifest_reviewer_ids = {
        reviewer_id.strip()
        for reviewer_id in source_manifest.reviewer_roster
        if reviewer_id.strip()
    }
    artifact_ids = tuple(
        artifact.artifact_id for artifact in source_manifest.source_artifacts
    )
    artifact_uris = tuple(artifact.uri for artifact in source_manifest.source_artifacts)
    artifact_sha256_values = tuple(
        artifact.sha256 for artifact in source_manifest.source_artifacts
    )
    artifact_kind_counts = _source_artifact_kind_counts(
        source_manifest.source_artifacts,
    )
    duplicate_manifest_selection_run_ids = _duplicate_uuid_strings(
        source_manifest.selection_review_run_ids,
    )
    duplicate_manifest_decision_keys = _duplicate_strings(
        source_manifest.review_ranking_decision_keys,
    )
    return {
        "source_manifest_present": True,
        "source_system": source_manifest.source_system,
        "export_id": source_manifest.export_id,
        "exporter_id": source_manifest.exporter_id,
        "exported_at": source_manifest.exported_at.isoformat(),
        "artifact_count": len(source_manifest.source_artifacts),
        "source_artifact_kind_counts": dict(artifact_kind_counts),
        "missing_required_source_artifact_kinds": [
            artifact_kind
            for artifact_kind in _REQUIRED_SOURCE_ARTIFACT_KINDS
            if artifact_kind_counts[artifact_kind] == 0
        ],
        "duplicate_source_artifact_id_count": len(_duplicate_strings(artifact_ids)),
        "duplicate_source_artifact_ids": list(_duplicate_strings(artifact_ids)),
        "duplicate_source_artifact_uri_count": len(_duplicate_strings(artifact_uris)),
        "duplicate_source_artifact_uris": list(_duplicate_strings(artifact_uris)),
        "duplicate_source_artifact_sha256_count": len(
            _duplicate_strings(artifact_sha256_values),
        ),
        "duplicate_source_artifact_sha256_values": list(
            _duplicate_strings(artifact_sha256_values),
        ),
        "selection_review_run_id_count": len(source_manifest.selection_review_run_ids),
        "duplicate_selection_run_id_count": len(duplicate_selection_run_ids),
        "duplicate_selection_run_ids": list(duplicate_selection_run_ids),
        "duplicate_manifest_selection_run_id_count": len(
            duplicate_manifest_selection_run_ids,
        ),
        "duplicate_manifest_selection_run_ids": list(
            duplicate_manifest_selection_run_ids,
        ),
        "missing_selection_run_id_count": len(
            expected_selection_run_id_set - manifest_selection_run_ids,
        ),
        "extra_selection_run_id_count": len(
            manifest_selection_run_ids - expected_selection_run_id_set,
        ),
        "missing_selection_run_ids": [
            str(run_id)
            for run_id in sorted(
                expected_selection_run_id_set - manifest_selection_run_ids,
            )
        ],
        "extra_selection_run_ids": [
            str(run_id)
            for run_id in sorted(
                manifest_selection_run_ids - expected_selection_run_id_set,
            )
        ],
        "review_ranking_decision_key_count": len(
            source_manifest.review_ranking_decision_keys,
        ),
        "duplicate_review_ranking_decision_key_count": (
            len(duplicate_review_ranking_decision_keys)
        ),
        "duplicate_review_ranking_decision_keys": list(
            duplicate_review_ranking_decision_keys,
        ),
        "duplicate_manifest_review_ranking_decision_key_count": len(
            duplicate_manifest_decision_keys,
        ),
        "duplicate_manifest_review_ranking_decision_keys": list(
            duplicate_manifest_decision_keys,
        ),
        "missing_review_ranking_decision_key_count": len(
            expected_decision_key_set - manifest_decision_keys,
        ),
        "extra_review_ranking_decision_key_count": len(
            manifest_decision_keys - expected_decision_key_set,
        ),
        "missing_review_ranking_decision_keys": sorted(
            expected_decision_key_set - manifest_decision_keys,
        ),
        "extra_review_ranking_decision_keys": sorted(
            manifest_decision_keys - expected_decision_key_set,
        ),
        "reviewer_roster_count": len(manifest_reviewer_ids),
        "unknown_reviewer_id_count": len(expected_reviewer_ids - manifest_reviewer_ids),
        "unknown_reviewer_ids": sorted(expected_reviewer_ids - manifest_reviewer_ids),
        "redaction_statement_present": bool(source_manifest.redaction_statement.strip()),
    }


def _source_artifact_blocking_reasons(
    *,
    provenance_summary: JSONObject,
    min_source_artifact_count: int,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if _int_from_json(provenance_summary, "artifact_count") < min_source_artifact_count:
        reasons.append(
            "At least "
            f"{min_source_artifact_count} source artifacts are required in the "
            "expert/shadow study manifest.",
        )
    missing_artifact_kinds = _string_tuple_from_json_list(
        provenance_summary,
        "missing_required_source_artifact_kinds",
    )
    if missing_artifact_kinds:
        reasons.append(
            "Source manifest must include hashed export artifacts for: "
            f"{', '.join(missing_artifact_kinds)}.",
        )
    if _int_from_json(provenance_summary, "duplicate_source_artifact_id_count") > 0:
        reasons.append("Source artifact IDs must be unique.")
    if _int_from_json(provenance_summary, "duplicate_source_artifact_uri_count") > 0:
        reasons.append("Source artifact URIs must be unique.")
    if _int_from_json(provenance_summary, "duplicate_source_artifact_sha256_count") > 0:
        reasons.append("Source artifact SHA-256 hashes must be unique.")
    return tuple(reasons)


def _source_selection_blocking_reasons(
    provenance_summary: JSONObject,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if _int_from_json(provenance_summary, "duplicate_selection_run_id_count") > 0:
        reasons.append("Selection review run IDs must be unique.")
    if (
        _int_from_json(
            provenance_summary,
            "duplicate_manifest_selection_run_id_count",
        )
        > 0
    ):
        reasons.append("Source manifest selection review run IDs must be unique.")
    if (
        _int_from_json(provenance_summary, "missing_selection_run_id_count") > 0
        or _int_from_json(provenance_summary, "extra_selection_run_id_count") > 0
    ):
        reasons.append(
            "Source manifest selection review run IDs must match the study "
            "selection reviews exactly.",
        )
    return tuple(reasons)


def _source_ranking_blocking_reasons(provenance_summary: JSONObject) -> tuple[str, ...]:
    reasons: list[str] = []
    if (
        _int_from_json(
            provenance_summary,
            "duplicate_review_ranking_decision_key_count",
        )
        > 0
    ):
        reasons.append("Review-ranking decision keys must be unique.")
    if (
        _int_from_json(
            provenance_summary,
            "duplicate_manifest_review_ranking_decision_key_count",
        )
        > 0
    ):
        reasons.append("Source manifest review-ranking decision keys must be unique.")
    if (
        _int_from_json(
            provenance_summary,
            "missing_review_ranking_decision_key_count",
        )
        > 0
        or _int_from_json(
            provenance_summary,
            "extra_review_ranking_decision_key_count",
        )
        > 0
    ):
        reasons.append(
            "Source manifest review-ranking decision keys must match the study "
            "review-ranking decisions exactly.",
        )
    return tuple(reasons)


def _source_artifact_kind_counts(
    artifacts: tuple[EvidenceSelectionExpertStudySourceArtifact, ...],
) -> dict[str, int]:
    return {
        artifact_kind: sum(
            1 for artifact in artifacts if artifact.artifact_kind == artifact_kind
        )
        for artifact_kind in _SOURCE_ARTIFACT_KINDS
    }


def _empty_source_artifact_kind_counts() -> dict[str, int]:
    return dict.fromkeys(_SOURCE_ARTIFACT_KINDS, 0)


def _duplicate_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen:
            duplicates.append(value)
            continue
        seen.add(value)
    return tuple(dict.fromkeys(duplicates))


def _duplicate_uuid_strings(values: tuple[UUID, ...]) -> tuple[str, ...]:
    return _duplicate_strings(tuple(str(value) for value in values))


def _strip_nonblank_text(value: str) -> str:
    stripped_value = value.strip()
    if not stripped_value:
        msg = "value must not be blank"
        raise ValueError(msg)
    return stripped_value


def _int_from_json(payload: JSONObject, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _string_tuple_from_json_list(payload: JSONObject, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


__all__ = [
    "EvidenceSelectionExpertStudySourceArtifact",
    "EvidenceSelectionExpertStudySourceManifest",
    "build_evidence_selection_provenance_summary",
    "parse_canonical_source_exported_at",
    "source_manifest_blocking_reasons",
    "validate_source_identity_text",
]
