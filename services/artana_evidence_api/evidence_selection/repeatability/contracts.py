"""Typed contracts for semantic-selector repeatability evidence."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.contracts import (
    EvidenceSelectionBenchmarkEvaluation,
    EvidenceSelectionBenchmarkV2Score,
)
from artana_evidence_api.evidence_selection.diagnostics.scoring import (
    EvidenceSelectionSemanticDiagnosticScore,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

SemanticDecision = Literal["select", "reject", "abstain", "invalid_agent"]
SemanticModelRole = Literal["current", "candidate"]
SemanticAttemptStatus = Literal[
    "completed",
    "failed",
    "abandoned",
    "rejected",
    "telemetry_unavailable",
]
SemanticTerminalOutcome = Literal[
    "completed",
    "failed",
    "timeout",
    "cancelled",
    "abandoned",
]
SemanticFailureStage = Literal[
    "output_schema_validation",
    "semantic_batch_validation",
    "evidence_reference_validation",
    "service_run_identity_validation",
    "provider_call",
    "provider_response",
    "runtime_execution",
    "telemetry_collection",
]
SemanticFailureCause = Literal[
    "schema_contract_rejected",
    "record_coverage_mismatch",
    "evidence_reference_invalid",
    "agent_run_identity_missing",
    "unexpected_local_validation_error",
    "timeout",
    "cancelled",
    "abandoned",
    "provider_refusal",
    "provider_client_error",
    "provider_server_error",
    "provider_transient_error",
    "provider_permanent_error",
    "network_error",
    "internal_error",
    "model_terminal_event_missing",
]
SemanticUsageProvenance = Literal[
    "artana_model_terminal",
    "unavailable",
]
SemanticTelemetryUnavailableReason = Literal[
    "artana_exception_did_not_preserve_provider_usage",
    "artana_terminal_missing_token_usage",
    "artana_terminal_partial_token_usage",
    "artana_terminal_missing_cost_usage",
    "model_terminal_event_missing",
    "no_model_attempts",
]
SemanticRepositorySourceRole = Literal[
    "baseline_predictions",
    "sanitized_source_snapshot",
    "benchmark_fixture",
    "benchmark_packet_manifest",
    "historical_fixture",
    "expert_study_bundle",
    "expert_study_source_artifact",
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
    policy_version: Literal["1.3.0"] = "1.3.0"
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
    maximum_adoption_failed_attempts: Literal[0] = 0
    maximum_adoption_rejected_attempts: Literal[0] = 0
    maximum_adoption_abandoned_attempts: Literal[0] = 0
    maximum_adoption_telemetry_unavailable_attempts: Literal[0] = 0


class SemanticModelComparisonProtocol(BaseModel):
    """Frozen inputs and policy for one controlled model comparison."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_model_protocol.v4"]
    generated_at: datetime
    evaluated_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    trusted_mainline_ref: str = Field(min_length=1)
    trusted_mainline_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    required_mainline_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    fixture_path: str = Field(min_length=1)
    fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fixture_provenance: Literal["ai_adjudicated_diagnostic"]
    benchmark_fixture_path: str = Field(min_length=1)
    benchmark_fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    benchmark_evaluation: EvidenceSelectionBenchmarkEvaluation
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
        if self.benchmark_evaluation.fixture_sha256 != self.benchmark_fixture_sha256:
            raise ValueError(
                "benchmark evaluation must match the frozen benchmark fixture"
            )
        if self.benchmark_evaluation.historical_v1_sha256 != self.fixture_sha256:
            raise ValueError(
                "benchmark evaluation must match the frozen historical fixture"
            )
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
        if (
            sum(
                source.role == "benchmark_fixture"
                for source in self.repository_source_files
            )
            != 1
        ):
            raise ValueError("protocol requires one benchmark-v2 fixture")
        if (
            sum(
                source.role == "benchmark_packet_manifest"
                for source in self.repository_source_files
            )
            != 1
        ):
            raise ValueError("protocol requires one benchmark-v2 packet manifest")
        if (
            sum(
                source.role == "historical_fixture"
                for source in self.repository_source_files
            )
            != 1
        ):
            raise ValueError("protocol requires one immutable historical fixture")
        return self


class SemanticRuntimeModelAttempt(BaseModel):
    """One semantic attempt joined to its Artana terminal event when present."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    execution_id: str = Field(min_length=1)
    batch_id: str = Field(pattern=r"^semantic_batch_[a-f0-9]{32}$")
    governed_context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt_sequence: int = Field(ge=1)
    batch_attempt_number: int = Field(ge=1)
    source_key: str = Field(min_length=1)
    search_id: str = Field(min_length=1)
    record_references: tuple[str, ...] = Field(min_length=1)
    step_key: str = Field(min_length=1)
    status: SemanticAttemptStatus
    terminal_outcome: SemanticTerminalOutcome | None = None
    model_id: str = Field(min_length=1)
    model_cycle_id: str | None = Field(default=None, min_length=1)
    source_model_requested_event_id: str | None = Field(default=None, min_length=1)
    model_requested_event_seq: int | None = Field(default=None, ge=1)
    model_requested_event_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    terminal_event_id: str | None = Field(default=None, min_length=1)
    terminal_event_seq: int | None = Field(default=None, ge=1)
    terminal_event_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    failure_stage: SemanticFailureStage | None = None
    failure_cause: SemanticFailureCause | None = None
    error_category: str | None = None
    error_class: str | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    token_usage_provenance: SemanticUsageProvenance
    token_usage_unavailable_reason: SemanticTelemetryUnavailableReason | None = None
    cost_usage_provenance: SemanticUsageProvenance
    cost_usage_unavailable_reason: SemanticTelemetryUnavailableReason | None = None

    @model_validator(mode="after")
    def _terminal_identity_must_be_consistent(self) -> SemanticRuntimeModelAttempt:
        terminal_fields = (
            self.terminal_outcome,
            self.model_cycle_id,
            self.source_model_requested_event_id,
            self.model_requested_event_seq,
            self.model_requested_event_hash,
            self.terminal_event_id,
            self.terminal_event_seq,
            self.terminal_event_hash,
            self.elapsed_ms,
        )
        has_terminal = self.terminal_outcome is not None
        if has_terminal != all(value is not None for value in terminal_fields):
            raise ValueError("attempt terminal identity must be complete or unavailable")
        if (
            self.model_requested_event_seq is not None
            and self.terminal_event_seq is not None
            and self.model_requested_event_seq >= self.terminal_event_seq
        ):
            raise ValueError("model request must precede its terminal event")
        return self

    @model_validator(mode="after")
    def _status_must_match_terminal_outcome(self) -> SemanticRuntimeModelAttempt:
        has_terminal = self.terminal_outcome is not None
        if self.status == "completed" and self.terminal_outcome != "completed":
            raise ValueError("completed attempt requires a completed terminal event")
        if self.status == "rejected" and self.terminal_outcome != "completed":
            raise ValueError("locally rejected attempt requires a completed terminal event")
        if self.status == "failed" and self.terminal_outcome not in {
            "failed",
            "timeout",
            "cancelled",
        }:
            raise ValueError("failed attempt requires a failed terminal event")
        if self.status == "abandoned" and self.terminal_outcome != "abandoned":
            raise ValueError("abandoned attempt requires an abandoned terminal event")
        if self.status == "telemetry_unavailable" and has_terminal:
            raise ValueError("telemetry-unavailable attempt cannot contain a terminal event")
        return self

    @model_validator(mode="after")
    def _failure_and_usage_must_be_consistent(self) -> SemanticRuntimeModelAttempt:
        has_failure = self.failure_stage is not None and self.failure_cause is not None
        if (self.status != "completed") != has_failure:
            raise ValueError("non-completed attempt requires typed failure stage and cause")
        if (self.failure_stage is None) != (self.failure_cause is None):
            raise ValueError("failure stage and cause must be declared together")
        if len(set(self.record_references)) != len(self.record_references):
            raise ValueError("attempt record references must be unique")
        complete_tokens = (
            self.prompt_tokens is not None and self.completion_tokens is not None
        )
        if complete_tokens != (self.token_usage_provenance == "artana_model_terminal"):
            raise ValueError("token values must match their Artana provenance")
        if complete_tokens != (self.token_usage_unavailable_reason is None):
            raise ValueError("token availability must have explicit provenance")
        cost_available = self.cost_usd is not None
        if cost_available != (self.cost_usage_provenance == "artana_model_terminal"):
            raise ValueError("cost value must match its Artana provenance")
        if cost_available != (self.cost_usage_unavailable_reason is None):
            raise ValueError("cost availability must have explicit provenance")
        return self


class SemanticRuntimeLedgerObservation(BaseModel):
    """Observed model attempts bound to semantic batches and Artana events."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    numeric_origin: Literal["runtime_observation"] = "runtime_observation"
    runtime_source: Literal["artana_event_ledger"] = "artana_event_ledger"
    collection_method: Literal["model_attempt_event_join"] = (
        "model_attempt_event_join"
    )
    status: Literal["available", "partial", "unavailable"]
    expected_model_id: str = Field(min_length=1)
    execution_ids: tuple[str, ...]
    model_attempt_count: int = Field(ge=0)
    model_terminal_count: int = Field(ge=0)
    model_attempts: tuple[SemanticRuntimeModelAttempt, ...]
    model_attempts_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    model_latency_seconds: float | None = Field(default=None, ge=0.0)
    token_unit: Literal["tokens"] = "tokens"
    cost_unit: Literal["USD"] = "USD"
    latency_unit: Literal["seconds"] = "seconds"
    token_usage_provenance: SemanticUsageProvenance
    cost_usage_provenance: SemanticUsageProvenance
    unavailable_reasons: tuple[SemanticTelemetryUnavailableReason, ...]

    @model_validator(mode="after")
    def _validate_observation(self) -> SemanticRuntimeLedgerObservation:
        from .runtime.ledger import (
            aggregate_semantic_model_attempts,
            semantic_ledger_status,
            semantic_model_attempts_sha256,
            validate_semantic_attempt_order,
        )

        validate_semantic_attempt_order(self.model_attempts)
        if self.model_attempt_count != len(self.model_attempts):
            raise ValueError("model attempt count must match the ledger snapshot")
        if self.model_terminal_count != sum(
            attempt.terminal_outcome is not None for attempt in self.model_attempts
        ):
            raise ValueError("model terminal count must match observed attempts")
        if self.model_attempts_sha256 != semantic_model_attempts_sha256(
            self.model_attempts,
        ):
            raise ValueError("runtime model-attempt snapshot digest does not match")
        attempt_execution_ids = tuple(
            attempt.execution_id for attempt in self.model_attempts
        )
        if attempt_execution_ids != self.execution_ids:
            raise ValueError("runtime attempts must preserve execution order")
        if any(
            attempt.model_id != self.expected_model_id for attempt in self.model_attempts
        ):
            raise ValueError("runtime ledger snapshot contains the wrong model")
        aggregate = aggregate_semantic_model_attempts(self.model_attempts)
        declared_aggregate = (
            self.prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
            self.cost_usd,
            self.model_latency_seconds,
            self.token_usage_provenance,
            self.cost_usage_provenance,
            self.unavailable_reasons,
        )
        recomputed_aggregate = (
            aggregate.prompt_tokens,
            aggregate.completion_tokens,
            aggregate.total_tokens,
            aggregate.cost_usd,
            aggregate.model_latency_seconds,
            aggregate.token_usage_provenance,
            aggregate.cost_usage_provenance,
            aggregate.unavailable_reasons,
        )
        if declared_aggregate != recomputed_aggregate:
            raise ValueError(
                "runtime telemetry aggregate does not match terminal events"
            )
        expected_status = semantic_ledger_status(self.model_attempts)
        if self.status != expected_status:
            raise ValueError("runtime telemetry status does not match model attempts")
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
    attempt_manifest_path: str = Field(min_length=1)
    attempt_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
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
    adoption_score: EvidenceSelectionBenchmarkV2Score
    record_decisions: tuple[SemanticRecordDecision, ...]
    telemetry: SemanticRunTelemetry
    calibration_status: Literal["unavailable"] = "unavailable"
    calibration_ece: None = None
    production_readiness_claim: Literal[False]

    @model_validator(mode="after")
    def _run_identity_must_be_complete(self) -> SemanticModelEvaluationRun:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("model run generated_at must include a timezone")
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
    adoption_metrics_status: Literal["available", "unavailable"]
    canary_gate_status: Literal["passed", "failed", "unavailable"]
    worst_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    worst_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    minimum_case_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    minimum_case_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    minimum_case_decision_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    precision_variance: float | None = Field(default=None, ge=0.0)
    recall_variance: float | None = Field(default=None, ge=0.0)
    worst_decision_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_abstention_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    invalid_agent_count: int = Field(ge=0)
    deterministic_fallback_count: Literal[0]
    decision_counts: SemanticDecisionCounts
    unstable_record_count: int = Field(ge=0)
    record_consensus: tuple[SemanticRecordConsensus, ...]
    model_attempt_count: int = Field(ge=0)
    failed_attempt_count: int = Field(ge=0)
    rejected_attempt_count: int = Field(ge=0)
    abandoned_attempt_count: int = Field(ge=0)
    telemetry_unavailable_attempt_count: int = Field(ge=0)
    schema_validation_failure_count: int = Field(ge=0)
    usage_unavailable_attempt_count: int = Field(ge=0)
    telemetry_complete: bool
    attempt_reliability_passed: bool
    total_prompt_tokens: int | None = Field(default=None, ge=0)
    total_completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    total_cost_usd: float | None = Field(default=None, ge=0.0)
    total_model_latency_seconds: float | None = Field(default=None, ge=0.0)
    total_wall_latency_seconds: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _availability_must_match_fields(self) -> SemanticModelRunSummary:
        metric_values = (
            self.worst_precision,
            self.worst_recall,
            self.minimum_case_precision,
            self.minimum_case_recall,
            self.minimum_case_decision_coverage,
            self.mean_precision,
            self.mean_recall,
            self.precision_variance,
            self.recall_variance,
            self.worst_decision_coverage,
            self.mean_abstention_rate,
        )
        if (self.adoption_metrics_status == "unavailable") != all(
            value is None for value in metric_values
        ):
            raise ValueError("summary metric fields must follow adoption availability")
        if self.adoption_metrics_status == "unavailable" and self.quality_gate_passed:
            raise ValueError("unavailable adoption metrics cannot pass quality")
        if self.canary_gate_status != "passed" and self.quality_gate_passed:
            raise ValueError("quality requires a passed eligible canary gate")
        return self


class SemanticModelMetricDeltas(BaseModel):
    """Candidate minus current deterministic comparison metrics."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    worst_precision: float | None
    worst_recall: float | None
    combined_variance: float | None
    cost_ratio: float | None = Field(default=None, ge=0.0)
    model_latency_ratio: float | None = Field(default=None, ge=0.0)


SemanticAdoptionReason = Literal[
    "candidate_is_only_model_passing_quality_gate",
    "candidate_materially_improves_worst_run_quality",
    "candidate_quality_gate_failed",
    "current_and_candidate_quality_gates_failed",
    "runtime_telemetry_incomplete",
    "candidate_attempt_reliability_failed",
    "runtime_resource_ratio_undefined",
    "candidate_exceeds_maximum_resource_ratio",
    "candidate_worst_run_metric_regressed",
    "candidate_resource_cost_not_justified",
    "candidate_has_no_material_benefit",
    "benchmark_adoption_metrics_unavailable",
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

    schema_version: Literal["evidence_selection_semantic_model_comparison.v5"]
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
        unavailable = (
            self.current_summary.adoption_metrics_status == "unavailable"
            or self.candidate_summary.adoption_metrics_status == "unavailable"
        )
        if unavailable and (
            self.decision.outcome != "inconclusive"
            or self.decision.selected_model_id is not None
            or self.selected_model_repeatability_passed
        ):
            raise ValueError(
                "unavailable adoption evidence must fail comparison closed"
            )
        return self


__all__ = [
    "SemanticAttemptStatus",
    "SemanticDecision",
    "SemanticDecisionCounts",
    "SemanticFailureCause",
    "SemanticFailureStage",
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
    "SemanticRuntimeLedgerObservation",
    "SemanticRuntimeModelAttempt",
    "SemanticTelemetryUnavailableReason",
    "SemanticTerminalOutcome",
    "SemanticUsageProvenance",
    "SemanticWallClockObservation",
]
