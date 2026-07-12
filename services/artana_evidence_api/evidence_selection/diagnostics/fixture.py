"""Strict fixture contract for semantic evidence-selection diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EvidenceSelectionSemanticExpectedLabel = Literal["select", "reject"]
EvidenceSelectionSemanticEvaluationRole = Literal["primary", "canary"]
_MIN_PRIMARY_CASE_COUNT = 3
_MIN_DUPLICATE_GROUP_SIZE = 2


class EvidenceSelectionSemanticDiagnosticRecord(BaseModel):
    """One source candidate with an AI-adjudicated diagnostic label."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_id: str = Field(min_length=1)
    source_key: Literal["pubmed"]
    source_record_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    evidence_excerpt: str = Field(min_length=1)
    expected_label: EvidenceSelectionSemanticExpectedLabel
    expected_reason: str = Field(min_length=1)
    failure_tags: tuple[str, ...] = Field(min_length=1)
    duplicate_group: str | None = Field(default=None, min_length=1)

    @field_validator("failure_tags", mode="before")
    @classmethod
    def _accept_json_failure_tags(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator(
        "record_id",
        "source_record_id",
        "title",
        "evidence_excerpt",
        "expected_reason",
        "duplicate_group",
    )
    @classmethod
    def _require_literal_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _literal_nonblank(value)

    @field_validator("failure_tags")
    @classmethod
    def _validate_failure_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_literal_nonblank(tag) for tag in value)
        if len(set(normalized)) != len(normalized):
            msg = "failure_tags must be unique within a record"
            raise ValueError(msg)
        return normalized


class EvidenceSelectionSemanticDiagnosticCase(BaseModel):
    """One research objective and its candidate-level diagnostic labels."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    evaluation_role: EvidenceSelectionSemanticEvaluationRole
    source_run_id: str = Field(
        pattern=r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
    )
    source_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_artifact_path: str = Field(min_length=1)
    upstream_source_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    goal: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    inclusion_criteria: tuple[str, ...] = Field(min_length=1)
    exclusion_criteria: tuple[str, ...]
    records: tuple[EvidenceSelectionSemanticDiagnosticRecord, ...] = Field(min_length=1)

    @field_validator(
        "inclusion_criteria",
        "exclusion_criteria",
        "records",
        mode="before",
    )
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator(
        "case_id",
        "display_name",
        "source_run_id",
        "source_artifact_sha256",
        "source_artifact_path",
        "upstream_source_artifact_sha256",
        "goal",
        "instructions",
    )
    @classmethod
    def _require_literal_case_text(cls, value: str) -> str:
        return _literal_nonblank(value)

    @field_validator("inclusion_criteria", "exclusion_criteria")
    @classmethod
    def _validate_criteria(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_literal_nonblank(criterion) for criterion in value)
        if len(set(normalized)) != len(normalized):
            msg = "criteria must be unique within a case"
            raise ValueError(msg)
        return normalized

    @model_validator(mode="after")
    def _record_ids_must_be_unique(self) -> EvidenceSelectionSemanticDiagnosticCase:
        record_ids = [record.record_id for record in self.records]
        if len(set(record_ids)) != len(record_ids):
            msg = "record_id values must be unique within each case"
            raise ValueError(msg)
        source_groups: dict[
            tuple[str, str], list[EvidenceSelectionSemanticDiagnosticRecord]
        ] = {}
        duplicate_groups: dict[
            str, list[EvidenceSelectionSemanticDiagnosticRecord]
        ] = {}
        for record in self.records:
            source_groups.setdefault(
                (record.source_key, record.source_record_id),
                [],
            ).append(record)
            if record.duplicate_group is not None:
                duplicate_groups.setdefault(record.duplicate_group, []).append(record)
        for records in source_groups.values():
            if len(records) > 1 and (
                records[0].duplicate_group is None
                or len({record.duplicate_group for record in records}) != 1
            ):
                msg = "repeated source records must share one duplicate_group"
                raise ValueError(msg)
        for records in duplicate_groups.values():
            source_ids = {
                (record.source_key, record.source_record_id) for record in records
            }
            if len(records) < _MIN_DUPLICATE_GROUP_SIZE or len(source_ids) != 1:
                msg = "duplicate_group must identify at least two copies of one source record"
                raise ValueError(msg)
        return self


class EvidenceSelectionSemanticDiagnosticFixture(BaseModel):
    """Versioned AI-diagnostic corpus that cannot claim expert provenance."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_diagnostic.v1"]
    benchmark_name: str = Field(min_length=1)
    provenance: Literal["ai_adjudicated_diagnostic"]
    adjudication_scope: str = Field(min_length=1)
    baseline_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    baseline_model: str = Field(min_length=1)
    cases: tuple[EvidenceSelectionSemanticDiagnosticCase, ...] = Field(min_length=4)

    @field_validator("cases", mode="before")
    @classmethod
    def _accept_json_cases(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("benchmark_name", "adjudication_scope", "baseline_model")
    @classmethod
    def _require_literal_fixture_text(cls, value: str) -> str:
        return _literal_nonblank(value)

    @model_validator(mode="after")
    def _validate_fixture_inventory(self) -> EvidenceSelectionSemanticDiagnosticFixture:
        case_ids = [case.case_id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            msg = "case_id values must be unique"
            raise ValueError(msg)
        record_ids = [
            record.record_id for case in self.cases for record in case.records
        ]
        if len(set(record_ids)) != len(record_ids):
            msg = "record_id values must be unique across the fixture"
            raise ValueError(msg)
        run_ids = [case.source_run_id for case in self.cases]
        if len(set(run_ids)) != len(run_ids):
            msg = "source_run_id values must be unique"
            raise ValueError(msg)
        artifact_hashes = [case.source_artifact_sha256 for case in self.cases]
        if len(set(artifact_hashes)) != len(artifact_hashes):
            msg = "source_artifact_sha256 values must be unique"
            raise ValueError(msg)
        primary_count = sum(case.evaluation_role == "primary" for case in self.cases)
        canary_count = sum(case.evaluation_role == "canary" for case in self.cases)
        if primary_count < _MIN_PRIMARY_CASE_COUNT:
            msg = "fixture must include at least three primary cases"
            raise ValueError(msg)
        if canary_count < 1:
            msg = "fixture must include at least one canary case"
            raise ValueError(msg)
        return self


def load_semantic_diagnostic_fixture(
    path: Path,
) -> EvidenceSelectionSemanticDiagnosticFixture:
    """Load and validate one semantic diagnostic fixture from JSON."""

    return EvidenceSelectionSemanticDiagnosticFixture.model_validate_json(
        path.read_text(encoding="utf-8"),
    )


def _literal_nonblank(value: str) -> str:
    if not value.strip():
        msg = "diagnostic text fields must be nonblank"
        raise ValueError(msg)
    if value != value.strip():
        msg = "diagnostic text fields must not have leading or trailing whitespace"
        raise ValueError(msg)
    return value


__all__ = [
    "EvidenceSelectionSemanticDiagnosticCase",
    "EvidenceSelectionSemanticDiagnosticFixture",
    "EvidenceSelectionSemanticDiagnosticRecord",
    "EvidenceSelectionSemanticEvaluationRole",
    "EvidenceSelectionSemanticExpectedLabel",
    "load_semantic_diagnostic_fixture",
]
