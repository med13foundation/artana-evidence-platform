"""Strict contracts for the semantic diagnostic benchmark v2."""

from __future__ import annotations

from datetime import datetime
from math import isclose
from typing import Literal
from uuid import UUID

from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    EvidenceSelectionSemanticPredictionDecision,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BenchmarkDecision = Literal["select", "reject", "ambiguous"]
BenchmarkEvaluationRole = Literal["primary", "canary"]
BenchmarkEligibilityStatus = Literal[
    "score_eligible",
    "pending_expert",
    "ambiguous_pending_expert",
]


def _literal_nonblank(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError("benchmark text must be literal, nonblank, and trimmed")
    return value


class EvidenceSelectionBenchmarkArtifactRef(BaseModel):
    """Repository-relative immutable artifact identity."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionBenchmarkPacketRef(EvidenceSelectionBenchmarkArtifactRef):
    """One bounded source packet bound to a benchmark case."""

    case_id: str = Field(min_length=1)

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionBenchmarkPacketManifest(BaseModel):
    """Content-addressed inventory of bounded source packets."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_packet_manifest.v1"]
    packets: tuple[EvidenceSelectionBenchmarkPacketRef, ...] = Field(min_length=1)

    @field_validator("packets", mode="before")
    @classmethod
    def _accept_json_packets(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def _packets_must_be_unique(self) -> EvidenceSelectionBenchmarkPacketManifest:
        case_ids = [packet.case_id for packet in self.packets]
        paths = [packet.path for packet in self.packets]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("packet case_id values must be unique")
        if len(set(paths)) != len(paths):
            raise ValueError("packet paths must be unique")
        return self


class EvidenceSelectionBenchmarkEvidenceSpan(BaseModel):
    """Literal bounded evidence supporting an AI diagnostic category."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_locator: str = Field(min_length=1)
    quoted_text: str = Field(min_length=1)

    @field_validator("source_locator", "quoted_text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionBenchmarkAIDiagnostic(BaseModel):
    """Categorical agent adjudication that can never claim expert provenance."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_id: str = Field(min_length=1)
    provenance: Literal["ai_adjudicated_diagnostic"]
    decision: BenchmarkDecision
    rationale: str = Field(min_length=1)
    evidence_spans: tuple[EvidenceSelectionBenchmarkEvidenceSpan, ...] = Field(
        min_length=1,
    )

    @field_validator("evidence_spans", mode="before")
    @classmethod
    def _accept_json_spans(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("record_id", "rationale")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionBenchmarkExpertReviewBinding(BaseModel):
    """Link to one review run inside the existing expert-study bundle."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    review_run_id: UUID

    @field_validator("case_id")
    @classmethod
    def _validate_case_id(cls, value: str) -> str:
        return _literal_nonblank(value)


class EvidenceSelectionBenchmarkV2Fixture(BaseModel):
    """V2 fixture that preserves v1 and delegates human evidence to its gate."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_diagnostic.v2"]
    benchmark_name: str = Field(min_length=1)
    provenance: Literal["ai_adjudicated_diagnostic"]
    historical_v1: EvidenceSelectionBenchmarkArtifactRef
    source_packet_manifest: EvidenceSelectionBenchmarkArtifactRef
    expert_study_bundle: EvidenceSelectionBenchmarkArtifactRef | None
    pending_expert_reason: str | None = Field(default=None, min_length=1)
    expert_review_bindings: tuple[EvidenceSelectionBenchmarkExpertReviewBinding, ...]
    diagnostic_overrides: tuple[EvidenceSelectionBenchmarkAIDiagnostic, ...]

    @field_validator("expert_review_bindings", "diagnostic_overrides", mode="before")
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("benchmark_name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _literal_nonblank(value)

    @field_validator("pending_expert_reason")
    @classmethod
    def _validate_pending_reason(cls, value: str | None) -> str | None:
        return _literal_nonblank(value) if value is not None else None

    @model_validator(mode="after")
    def _expert_link_must_be_coherent(self) -> EvidenceSelectionBenchmarkV2Fixture:
        if self.expert_study_bundle is None:
            if self.pending_expert_reason is None:
                raise ValueError("pending expert benchmark requires an explicit reason")
            if self.expert_review_bindings:
                raise ValueError("expert review bindings require an expert-study bundle")
        elif self.pending_expert_reason is not None:
            raise ValueError("linked expert-study bundle cannot remain globally pending")
        case_ids = [binding.case_id for binding in self.expert_review_bindings]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("expert review case bindings must be unique")
        record_ids = [override.record_id for override in self.diagnostic_overrides]
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("diagnostic override record IDs must be unique")
        return self


class EvidenceSelectionBenchmarkRecordEvaluation(BaseModel):
    """Deterministically derived eligibility and label for one visible record."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str
    display_name: str
    evaluation_role: BenchmarkEvaluationRole
    record_id: str
    diagnostic_decision: BenchmarkDecision
    diagnostic_rationale: str
    eligibility_status: BenchmarkEligibilityStatus
    score_eligible: bool
    expert_label: Literal["select", "reject"] | None
    exclusion_reasons: tuple[str, ...]

    @model_validator(mode="after")
    def _eligibility_fields_must_agree(
        self,
    ) -> EvidenceSelectionBenchmarkRecordEvaluation:
        eligible = self.eligibility_status == "score_eligible"
        if self.score_eligible != eligible or (self.expert_label is not None) != eligible:
            raise ValueError("score eligibility, status, and expert label must agree")
        if eligible and self.exclusion_reasons:
            raise ValueError("score-eligible records cannot have exclusion reasons")
        if not eligible and not self.exclusion_reasons:
            raise ValueError("excluded records require an explicit reason")
        return self


class EvidenceSelectionBenchmarkEvaluation(BaseModel):
    """Complete visible inventory with deterministic eligibility decisions."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    historical_v1_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_packet_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expert_study_status: Literal["pending", "passed_existing_gate"]
    records: tuple[EvidenceSelectionBenchmarkRecordEvaluation, ...]


class EvidenceSelectionBenchmarkMetrics(BaseModel):
    """Counts and deterministic metrics over score-eligible records only."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_count: int = Field(ge=1)
    true_positive_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    true_negative_count: int = Field(ge=0)
    abstention_count: int = Field(ge=0)
    invalid_agent_count: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    end_to_end_recall: float = Field(ge=0.0, le=1.0)
    decision_coverage: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _counts_and_rates_must_agree(self) -> EvidenceSelectionBenchmarkMetrics:
        outcomes = (
            self.true_positive_count
            + self.false_positive_count
            + self.false_negative_count
            + self.true_negative_count
            + self.abstention_count
            + self.invalid_agent_count
        )
        if outcomes != self.record_count:
            raise ValueError("benchmark metric outcomes must partition record_count")
        selected = self.true_positive_count + self.false_positive_count
        expected_positive = self.true_positive_count + self.false_negative_count
        decided = (
            self.true_positive_count
            + self.false_positive_count
            + self.false_negative_count
            + self.true_negative_count
        )
        expected_rates = (
            ("precision", self.true_positive_count / selected if selected else 0.0),
            (
                "end_to_end_recall",
                self.true_positive_count / expected_positive
                if expected_positive
                else 0.0,
            ),
            ("decision_coverage", decided / self.record_count),
        )
        for field_name, expected in expected_rates:
            if not isclose(getattr(self, field_name), expected):
                raise ValueError(f"{field_name} is inconsistent with outcome counts")
        return self


class EvidenceSelectionBenchmarkRecordOutcome(BaseModel):
    """Visible prediction outcome whether or not the record can be scored."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_id: str
    evaluation_role: BenchmarkEvaluationRole
    diagnostic_decision: BenchmarkDecision
    prediction_decision: EvidenceSelectionSemanticPredictionDecision
    eligibility_status: BenchmarkEligibilityStatus
    score_eligible: bool
    expert_label: Literal["select", "reject"] | None


class EvidenceSelectionBenchmarkV2Score(BaseModel):
    """Eligible-only adoption metrics plus the complete diagnostic inventory."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    total_record_count: int = Field(ge=1)
    score_eligible_record_count: int = Field(ge=0)
    excluded_record_count: int = Field(ge=0)
    ambiguous_record_count: int = Field(ge=0)
    pending_expert_record_count: int = Field(ge=0)
    adoption_metrics: EvidenceSelectionBenchmarkMetrics | None
    canary_gate_status: Literal["passed", "failed", "unavailable"]
    record_outcomes: tuple[EvidenceSelectionBenchmarkRecordOutcome, ...]

    @model_validator(mode="after")
    def _inventory_counts_must_agree(self) -> EvidenceSelectionBenchmarkV2Score:
        if len(self.record_outcomes) != self.total_record_count:
            raise ValueError("record outcomes must match total_record_count")
        eligible = sum(outcome.score_eligible for outcome in self.record_outcomes)
        ambiguous = sum(
            outcome.eligibility_status == "ambiguous_pending_expert"
            for outcome in self.record_outcomes
        )
        pending = sum(
            outcome.eligibility_status == "pending_expert"
            for outcome in self.record_outcomes
        )
        if (
            eligible != self.score_eligible_record_count
            or self.excluded_record_count != self.total_record_count - eligible
            or ambiguous != self.ambiguous_record_count
            or pending != self.pending_expert_record_count
        ):
            raise ValueError("benchmark score inventory counts are inconsistent")
        eligible_canary_count = sum(
            outcome.score_eligible and outcome.evaluation_role == "canary"
            for outcome in self.record_outcomes
        )
        if (self.canary_gate_status == "unavailable") != (eligible_canary_count == 0):
            raise ValueError("canary availability must follow eligible canary inventory")
        return self


class EvidenceSelectionBenchmarkV2Report(BaseModel):
    """Honest report that cannot claim expert gold or production readiness."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_benchmark_report.v2"]
    generated_at: datetime
    fixture_path: str
    fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prediction_path: str
    prediction_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fixture_provenance: Literal["ai_adjudicated_diagnostic"]
    expert_study_status: Literal["pending", "passed_existing_gate"]
    production_readiness_claim: Literal[False]
    score: EvidenceSelectionBenchmarkV2Score


__all__ = [
    "BenchmarkDecision",
    "BenchmarkEligibilityStatus",
    "EvidenceSelectionBenchmarkAIDiagnostic",
    "EvidenceSelectionBenchmarkArtifactRef",
    "EvidenceSelectionBenchmarkEvaluation",
    "EvidenceSelectionBenchmarkExpertReviewBinding",
    "EvidenceSelectionBenchmarkMetrics",
    "EvidenceSelectionBenchmarkPacketManifest",
    "EvidenceSelectionBenchmarkRecordEvaluation",
    "EvidenceSelectionBenchmarkV2Fixture",
    "EvidenceSelectionBenchmarkV2Report",
    "EvidenceSelectionBenchmarkV2Score",
]
