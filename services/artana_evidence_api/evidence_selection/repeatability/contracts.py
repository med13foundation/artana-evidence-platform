"""Typed contracts for semantic-selector repeatability evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from artana_evidence_api.evidence_selection.diagnostics.scoring import (
    EvidenceSelectionSemanticDiagnosticScore,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

SemanticDecision = Literal["select", "reject", "abstain", "invalid_agent"]
SemanticModelRole = Literal["current", "candidate"]
SemanticTerminalCostDerivation = Literal[
    "provider_reported",
    "token_pricing",
    "unavailable",
]
SemanticCostDerivation = Literal[
    "provider_reported",
    "token_pricing",
    "mixed",
    "unavailable",
]
SemanticRepositorySourceRole = Literal[
    "baseline_predictions",
    "sanitized_source_snapshot",
]


class SemanticRepositorySourceFile(BaseModel):
    """One repository-relative source file frozen into the comparison protocol."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    role: SemanticRepositorySourceRole
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _path_must_be_canonical_and_relative(self) -> SemanticRepositorySourceFile:
        path = PurePosixPath(self.relative_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or self.relative_path != path.as_posix()
        ):
            raise ValueError("repository source paths must be canonical and relative")
        return self


class SemanticModelComparisonThresholds(BaseModel):
    """Versioned deterministic model-adoption policy."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    policy_id: Literal["evidence_selection.semantic_model_adoption"] = (
        "evidence_selection.semantic_model_adoption"
    )
    policy_version: Literal["1.2.0"] = "1.2.0"
    minimum_runs_per_model: int = Field(default=3, ge=3)
    minimum_worst_precision: float = Field(default=0.8, ge=0.8, le=1.0)
    minimum_worst_recall: float = Field(default=0.8, ge=0.8, le=1.0)
    minimum_case_precision: float = Field(default=0.7, ge=0.7, le=1.0)
    minimum_case_recall: float = Field(default=0.7, ge=0.7, le=1.0)
    minimum_worst_decision_coverage: float = Field(default=0.8, ge=0.8, le=1.0)
    minimum_case_decision_coverage: float = Field(default=0.7, ge=0.7, le=1.0)
    material_worst_metric_improvement: float = Field(
        default=0.02,
        ge=0.02,
        le=1.0,
    )
    maximum_worst_metric_regression: float = Field(
        default=0.0,
        ge=0.0,
        le=0.02,
    )
    expensive_candidate_ratio: float = Field(default=2.0, ge=1.0, le=2.0)
    expensive_candidate_minimum_improvement: float = Field(
        default=0.05,
        ge=0.05,
        le=1.0,
    )
    maximum_candidate_resource_ratio: float = Field(
        default=10.0,
        ge=2.0,
        le=100.0,
    )


class SemanticModelComparisonProtocol(BaseModel):
    """Frozen inputs and policy for one controlled model comparison."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_model_protocol.v3"]
    generated_at: datetime
    evaluated_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    trusted_mainline_ref: str = Field(min_length=1)
    trusted_mainline_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    required_mainline_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    fixture_path: str = Field(min_length=1)
    fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fixture_provenance: Literal["ai_adjudicated_diagnostic"]
    baseline_report_path: str = Field(min_length=1)
    baseline_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    repository_source_files: tuple[SemanticRepositorySourceFile, ...] = Field(
        min_length=2,
    )
    current_model_id: str = Field(min_length=1)
    candidate_model_id: str = Field(min_length=1)
    runs_per_model: int = Field(ge=3)
    thresholds: SemanticModelComparisonThresholds
    source_lock_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    production_readiness_claim: Literal[False]

    @model_validator(mode="after")
    def _models_and_runs_must_match_policy(self) -> SemanticModelComparisonProtocol:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("comparison protocol generated_at must include a timezone")
        if self.current_model_id == self.candidate_model_id:
            raise ValueError("model comparison requires distinct model IDs")
        if self.runs_per_model < self.thresholds.minimum_runs_per_model:
            raise ValueError("runs_per_model is below the policy minimum")
        paths = tuple(source.relative_path for source in self.repository_source_files)
        if len(set(paths)) != len(paths):
            raise ValueError("repository source paths must be unique")
        prediction_count = sum(
            source.role == "baseline_predictions"
            for source in self.repository_source_files
        )
        snapshot_count = sum(
            source.role == "sanitized_source_snapshot"
            for source in self.repository_source_files
        )
        if prediction_count != 1 or snapshot_count < 1:
            raise ValueError(
                "protocol requires one baseline prediction file and source snapshots",
            )
        return self


class SemanticRuntimeTerminalEvent(BaseModel):
    """Normalized immutable facts from one Artana model-terminal event."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    execution_id: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_cycle_id: str = Field(min_length=1)
    source_model_requested_event_id: str = Field(min_length=1)
    elapsed_ms: int = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    cost_derivation: SemanticTerminalCostDerivation

    @model_validator(mode="after")
    def _cost_and_derivation_must_match(self) -> SemanticRuntimeTerminalEvent:
        if (self.cost_usd is None) != (self.cost_derivation == "unavailable"):
            raise ValueError("terminal event cost must match its derivation")
        return self


@dataclass(frozen=True)
class SemanticRuntimeEventAggregate:
    """Deterministic aggregates recomputed from terminal events."""

    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    model_latency_seconds: float | None
    cost_derivation: SemanticCostDerivation


def aggregate_semantic_terminal_events(
    events: tuple[SemanticRuntimeTerminalEvent, ...],
) -> SemanticRuntimeEventAggregate:
    """Derive usage totals solely from the embedded immutable event facts."""

    if not events:
        return SemanticRuntimeEventAggregate(
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            cost_usd=None,
            model_latency_seconds=None,
            cost_derivation="unavailable",
        )
    prompt_tokens = _complete_int_sum(
        tuple(event.prompt_tokens for event in events),
    )
    completion_tokens = _complete_int_sum(
        tuple(event.completion_tokens for event in events),
    )
    total_tokens = (
        prompt_tokens + completion_tokens
        if prompt_tokens is not None and completion_tokens is not None
        else None
    )
    cost_values = tuple(event.cost_usd for event in events)
    cost_usd = (
        round(sum(value for value in cost_values if value is not None), 8)
        if all(value is not None for value in cost_values)
        else None
    )
    cost_derivation = _aggregate_cost_derivation(
        frozenset(event.cost_derivation for event in events),
    )
    return SemanticRuntimeEventAggregate(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        model_latency_seconds=round(
            sum(event.elapsed_ms for event in events) / 1000.0,
            6,
        ),
        cost_derivation=cost_derivation,
    )


def _complete_int_sum(values: tuple[int | None, ...]) -> int | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _aggregate_cost_derivation(
    methods: frozenset[SemanticTerminalCostDerivation],
) -> SemanticCostDerivation:
    if "unavailable" in methods:
        return "unavailable"
    if methods == {"provider_reported"}:
        return "provider_reported"
    if methods == {"token_pricing"}:
        return "token_pricing"
    return "mixed"


def semantic_terminal_events_sha256(
    events: tuple[SemanticRuntimeTerminalEvent, ...],
) -> str:
    """Hash the complete normalized runtime-ledger snapshot."""

    payload = json.dumps(
        [event.model_dump(mode="json") for event in events],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class SemanticRuntimeLedgerObservation(BaseModel):
    """Observed model-terminal usage bound to exact Artana run IDs."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    numeric_origin: Literal["runtime_observation"] = "runtime_observation"
    runtime_source: Literal["artana_event_ledger"] = "artana_event_ledger"
    collection_method: Literal["model_terminal_event_aggregation"] = (
        "model_terminal_event_aggregation"
    )
    status: Literal["available", "partial", "unavailable"]
    expected_model_id: str = Field(min_length=1)
    execution_ids: tuple[str, ...]
    model_terminal_count: int = Field(ge=0)
    terminal_events: tuple[SemanticRuntimeTerminalEvent, ...]
    terminal_events_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    model_latency_seconds: float | None = Field(default=None, ge=0.0)
    token_unit: Literal["tokens"] = "tokens"
    cost_unit: Literal["USD"] = "USD"
    latency_unit: Literal["seconds"] = "seconds"
    cost_derivation: SemanticCostDerivation

    @model_validator(mode="after")
    def _validate_observation(self) -> SemanticRuntimeLedgerObservation:
        if len(set(self.execution_ids)) != len(self.execution_ids):
            raise ValueError("runtime execution IDs must be unique")
        if self.model_terminal_count != len(self.terminal_events):
            raise ValueError("model terminal count must match the ledger snapshot")
        if self.terminal_events_sha256 != semantic_terminal_events_sha256(
            self.terminal_events,
        ):
            raise ValueError("runtime ledger snapshot digest does not match")
        if any(
            event.execution_id not in self.execution_ids
            for event in self.terminal_events
        ):
            raise ValueError("runtime ledger snapshot contains an unknown execution")
        if any(
            event.model_id != self.expected_model_id for event in self.terminal_events
        ):
            raise ValueError("runtime ledger snapshot contains the wrong model")
        aggregate = aggregate_semantic_terminal_events(self.terminal_events)
        declared_aggregate = (
            self.prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
            self.cost_usd,
            self.model_latency_seconds,
            self.cost_derivation,
        )
        recomputed_aggregate = (
            aggregate.prompt_tokens,
            aggregate.completion_tokens,
            aggregate.total_tokens,
            aggregate.cost_usd,
            aggregate.model_latency_seconds,
            aggregate.cost_derivation,
        )
        if declared_aggregate != recomputed_aggregate:
            raise ValueError(
                "runtime telemetry aggregate does not match terminal events"
            )
        covered_execution_ids = {event.execution_id for event in self.terminal_events}
        if self.status == "available" and (
            not self.execution_ids or covered_execution_ids != set(self.execution_ids)
        ):
            raise ValueError("available runtime telemetry must cover every execution")
        if self.prompt_tokens is not None and self.completion_tokens is not None:
            expected_total = self.prompt_tokens + self.completion_tokens
            if self.total_tokens != expected_total:
                raise ValueError("total_tokens must equal prompt plus completion")
        if self.status == "available" and any(
            value is None
            for value in (
                self.prompt_tokens,
                self.completion_tokens,
                self.total_tokens,
                self.cost_usd,
                self.model_latency_seconds,
            )
        ):
            raise ValueError("available runtime telemetry must be complete")
        if self.status == "unavailable" and any(
            value is not None
            for value in (
                self.prompt_tokens,
                self.completion_tokens,
                self.total_tokens,
                self.cost_usd,
                self.model_latency_seconds,
            )
        ):
            raise ValueError("unavailable runtime telemetry cannot contain values")
        if self.status == "unavailable" and self.terminal_events:
            raise ValueError("unavailable runtime telemetry cannot contain events")
        return self


class SemanticWallClockObservation(BaseModel):
    """Wall-clock duration measured independently of provider telemetry."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    numeric_origin: Literal["runtime_observation"] = "runtime_observation"
    runtime_source: Literal["process_monotonic_clock"] = "process_monotonic_clock"
    collection_method: Literal["perf_counter_elapsed"] = "perf_counter_elapsed"
    execution_ids: tuple[str, ...]
    elapsed_seconds: float = Field(ge=0.0)
    unit: Literal["seconds"] = "seconds"


class SemanticRunTelemetry(BaseModel):
    """Complete runtime observations for one semantic evaluation run."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    ledger: SemanticRuntimeLedgerObservation
    wall_clock: SemanticWallClockObservation

    @model_validator(mode="after")
    def _execution_ids_must_match(self) -> SemanticRunTelemetry:
        if self.ledger.execution_ids != self.wall_clock.execution_ids:
            raise ValueError("ledger and wall-clock execution IDs must match")
        return self


class SemanticRecordDecision(BaseModel):
    """One categorical output used for disagreement analysis."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    decision: SemanticDecision


class SemanticModelEvaluationRun(BaseModel):
    """One immutable live evaluation plus its runtime observations."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    model_role: SemanticModelRole
    run_index: int = Field(ge=1)
    evaluation_path: str = Field(min_length=1)
    evaluation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    generated_at: datetime
    evaluated_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    model_id: str = Field(min_length=1)
    fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fixture_provenance: Literal["ai_adjudicated_diagnostic"]
    deterministic_fallback_count: Literal[0]
    score: EvidenceSelectionSemanticDiagnosticScore
    canary_passed: bool
    quality_gate_passed: bool
    agent_run_ids: tuple[str, ...]
    record_decisions: tuple[SemanticRecordDecision, ...]
    telemetry: SemanticRunTelemetry
    calibration_status: Literal["unavailable"] = "unavailable"
    calibration_ece: None = None
    production_readiness_claim: Literal[False]

    @model_validator(mode="after")
    def _run_identity_must_be_complete(self) -> SemanticModelEvaluationRun:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("model run generated_at must include a timezone")
        if len(set(self.agent_run_ids)) != len(self.agent_run_ids):
            raise ValueError("agent run IDs must be unique within an evaluation")
        if self.telemetry.ledger.execution_ids != self.agent_run_ids:
            raise ValueError("runtime telemetry must bind every agent run ID")
        if self.telemetry.ledger.expected_model_id != self.model_id:
            raise ValueError("runtime telemetry model must match the evaluation model")
        decision_keys = tuple(
            (decision.case_id, decision.record_id) for decision in self.record_decisions
        )
        if len(set(decision_keys)) != len(decision_keys):
            raise ValueError("record decisions must have unique case/record keys")
        return self


class SemanticDecisionCounts(BaseModel):
    """Deterministically counted categorical decisions."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    select: int = Field(ge=0)
    reject: int = Field(ge=0)
    abstain: int = Field(ge=0)
    invalid_agent: int = Field(ge=0)


class SemanticRecordConsensus(BaseModel):
    """Repeated categorical decisions for one frozen source record."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    counts: SemanticDecisionCounts
    consensus_decision: SemanticDecision | Literal["no_consensus"]
    stable: bool


class SemanticModelRunSummary(BaseModel):
    """Deterministic repeatability metrics for one model group."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    model_id: str = Field(min_length=1)
    run_count: int = Field(ge=1)
    quality_gate_passed: bool
    worst_precision: float = Field(ge=0.0, le=1.0)
    worst_recall: float = Field(ge=0.0, le=1.0)
    minimum_case_precision: float = Field(ge=0.0, le=1.0)
    minimum_case_recall: float = Field(ge=0.0, le=1.0)
    minimum_case_decision_coverage: float = Field(ge=0.0, le=1.0)
    mean_precision: float = Field(ge=0.0, le=1.0)
    mean_recall: float = Field(ge=0.0, le=1.0)
    precision_variance: float = Field(ge=0.0)
    recall_variance: float = Field(ge=0.0)
    worst_decision_coverage: float = Field(ge=0.0, le=1.0)
    mean_abstention_rate: float = Field(ge=0.0, le=1.0)
    invalid_agent_count: int = Field(ge=0)
    deterministic_fallback_count: Literal[0]
    all_canaries_passed: bool
    decision_counts: SemanticDecisionCounts
    unstable_record_count: int = Field(ge=0)
    record_consensus: tuple[SemanticRecordConsensus, ...]
    telemetry_complete: bool
    total_prompt_tokens: int | None = Field(default=None, ge=0)
    total_completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    total_cost_usd: float | None = Field(default=None, ge=0.0)
    total_model_latency_seconds: float | None = Field(default=None, ge=0.0)
    total_wall_latency_seconds: float = Field(ge=0.0)


class SemanticModelMetricDeltas(BaseModel):
    """Candidate minus current deterministic comparison metrics."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    worst_precision: float
    worst_recall: float
    combined_variance: float
    cost_ratio: float | None = Field(default=None, ge=0.0)
    model_latency_ratio: float | None = Field(default=None, ge=0.0)


SemanticAdoptionReason = Literal[
    "candidate_is_only_model_passing_quality_gate",
    "candidate_materially_improves_worst_run_quality",
    "candidate_quality_gate_failed",
    "current_and_candidate_quality_gates_failed",
    "runtime_telemetry_incomplete",
    "runtime_resource_ratio_undefined",
    "candidate_exceeds_maximum_resource_ratio",
    "candidate_worst_run_metric_regressed",
    "candidate_resource_cost_not_justified",
    "candidate_has_no_material_benefit",
]


class SemanticModelAdoptionDecision(BaseModel):
    """Categorical adoption result derived by the versioned policy."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    outcome: Literal["adopt_candidate", "keep_current", "inconclusive"]
    selected_model_id: str | None
    reason_codes: tuple[SemanticAdoptionReason, ...]
    blocking_reasons: tuple[str, ...]
    metric_deltas: SemanticModelMetricDeltas


class SemanticModelComparisonReport(BaseModel):
    """Self-contained proof report for selector repeatability and model choice."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_model_comparison.v3"]
    generated_at: datetime
    protocol: SemanticModelComparisonProtocol
    protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    current_runs: tuple[SemanticModelEvaluationRun, ...]
    candidate_runs: tuple[SemanticModelEvaluationRun, ...]
    current_summary: SemanticModelRunSummary
    candidate_summary: SemanticModelRunSummary
    cross_model_disagreement_count: int = Field(ge=0)
    decision: SemanticModelAdoptionDecision
    selected_model_repeatability_passed: bool
    calibration_status: Literal["unavailable"] = "unavailable"
    calibration_ece: None = None
    evidence_provenance: Literal["ai_adjudicated_diagnostic"]
    production_readiness_claim: Literal[False]

    @model_validator(mode="after")
    def _report_timestamp_must_be_aware(self) -> SemanticModelComparisonReport:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("comparison report generated_at must include a timezone")
        return self


__all__ = [
    "SemanticDecision",
    "SemanticDecisionCounts",
    "SemanticModelAdoptionDecision",
    "SemanticModelComparisonProtocol",
    "SemanticModelComparisonReport",
    "SemanticModelComparisonThresholds",
    "SemanticModelEvaluationRun",
    "SemanticModelMetricDeltas",
    "SemanticModelRunSummary",
    "SemanticRecordConsensus",
    "SemanticRecordDecision",
    "SemanticRunTelemetry",
    "SemanticCostDerivation",
    "SemanticRuntimeEventAggregate",
    "SemanticRuntimeLedgerObservation",
    "SemanticRuntimeTerminalEvent",
    "SemanticTerminalCostDerivation",
    "SemanticWallClockObservation",
    "aggregate_semantic_terminal_events",
    "semantic_terminal_events_sha256",
]
