"""Deterministic quality, stability, and runtime summaries for model runs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from statistics import fmean, pvariance
from typing import Literal

from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.contracts import (
    EvidenceSelectionBenchmarkRecordOutcome,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.scoring import (
    metrics_for_outcomes,
)

from .contracts import (
    SemanticDecision,
    SemanticDecisionCounts,
    SemanticModelComparisonProtocol,
    SemanticModelEvaluationRun,
    SemanticModelRunSummary,
    SemanticRecordConsensus,
)


def summarize_semantic_model_runs(
    *,
    runs: tuple[SemanticModelEvaluationRun, ...],
    protocol: SemanticModelComparisonProtocol,
) -> SemanticModelRunSummary:
    """Compute repeatability metrics from already validated categorical runs."""

    adoption_metrics = tuple(run.adoption_score.adoption_metrics for run in runs)
    metrics_available = all(metrics is not None for metrics in adoption_metrics)
    available_metrics = tuple(
        metrics for metrics in adoption_metrics if metrics is not None
    )
    precision_values = tuple(metrics.precision for metrics in available_metrics)
    recall_values = tuple(metrics.end_to_end_recall for metrics in available_metrics)
    coverage_values = tuple(metrics.decision_coverage for metrics in available_metrics)
    abstention_values = tuple(
        metrics.abstention_count / metrics.record_count for metrics in available_metrics
    )
    primary_case_metrics = tuple(
        metrics_for_outcomes(case_outcomes)
        for run in runs
        for case_outcomes in _eligible_primary_outcomes_by_case(run).values()
    )
    minimum_case_precision = (
        min(result.precision for result in primary_case_metrics)
        if primary_case_metrics
        else None
    )
    minimum_case_recall = (
        min(result.end_to_end_recall for result in primary_case_metrics)
        if primary_case_metrics
        else None
    )
    minimum_case_decision_coverage = (
        min(result.decision_coverage for result in primary_case_metrics)
        if primary_case_metrics
        else None
    )
    eligible_record_ids = {
        record.record_id
        for record in protocol.benchmark_evaluation.records
        if record.score_eligible
    }
    record_consensus = _record_consensus(runs, eligible_record_ids=eligible_record_ids)
    unstable_record_count = sum(not item.stable for item in record_consensus)
    decision_counts = _decision_counts(
        decision.decision
        for run in runs
        for decision in run.record_decisions
        if decision.record_id in eligible_record_ids
    )
    telemetry_complete = all(run.telemetry.ledger.status == "available" for run in runs)
    invalid_agent_count = sum(
        metrics.invalid_agent_count for metrics in available_metrics
    )
    canary_statuses = {run.adoption_score.canary_gate_status for run in runs}
    canary_gate_status = (
        next(iter(canary_statuses)) if len(canary_statuses) == 1 else "failed"
    )
    model_attempts = tuple(
        attempt
        for run in runs
        for attempt in run.telemetry.ledger.model_attempts
    )
    thresholds = protocol.thresholds
    quality_gate_passed = (
        len(runs) >= thresholds.minimum_runs_per_model
        and metrics_available
        and bool(precision_values)
        and min(precision_values) >= thresholds.minimum_worst_precision
        and min(recall_values) >= thresholds.minimum_worst_recall
        and minimum_case_precision is not None
        and minimum_case_precision >= thresholds.minimum_case_precision
        and minimum_case_recall is not None
        and minimum_case_recall >= thresholds.minimum_case_recall
        and min(coverage_values) >= thresholds.minimum_worst_decision_coverage
        and minimum_case_decision_coverage is not None
        and minimum_case_decision_coverage >= thresholds.minimum_case_decision_coverage
        and unstable_record_count == 0
        and invalid_agent_count == 0
        and canary_gate_status == "passed"
        and all(run.deterministic_fallback_count == 0 for run in runs)
    )
    return SemanticModelRunSummary(
        model_id=runs[0].model_id,
        run_count=len(runs),
        quality_gate_passed=quality_gate_passed,
        adoption_metrics_status="available" if metrics_available else "unavailable",
        canary_gate_status=canary_gate_status,
        worst_precision=min(precision_values) if precision_values else None,
        worst_recall=min(recall_values) if recall_values else None,
        minimum_case_precision=minimum_case_precision,
        minimum_case_recall=minimum_case_recall,
        minimum_case_decision_coverage=minimum_case_decision_coverage,
        mean_precision=fmean(precision_values) if precision_values else None,
        mean_recall=fmean(recall_values) if recall_values else None,
        precision_variance=pvariance(precision_values) if precision_values else None,
        recall_variance=pvariance(recall_values) if recall_values else None,
        worst_decision_coverage=min(coverage_values) if coverage_values else None,
        mean_abstention_rate=fmean(abstention_values) if abstention_values else None,
        invalid_agent_count=invalid_agent_count,
        deterministic_fallback_count=0,
        decision_counts=decision_counts,
        unstable_record_count=unstable_record_count,
        record_consensus=record_consensus,
        model_attempt_count=len(model_attempts),
        failed_attempt_count=sum(
            attempt.status in {"failed", "telemetry_unavailable"}
            for attempt in model_attempts
        ),
        rejected_attempt_count=sum(
            attempt.status == "rejected" for attempt in model_attempts
        ),
        schema_validation_failure_count=sum(
            attempt.failure_stage == "output_schema_validation"
            for attempt in model_attempts
        ),
        usage_unavailable_attempt_count=sum(
            attempt.token_usage_provenance == "unavailable"
            or attempt.cost_usage_provenance == "unavailable"
            for attempt in model_attempts
        ),
        telemetry_complete=telemetry_complete,
        total_prompt_tokens=_sum_complete_ledger_int(runs, "prompt_tokens"),
        total_completion_tokens=_sum_complete_ledger_int(runs, "completion_tokens"),
        total_tokens=_sum_complete_ledger_int(runs, "total_tokens"),
        total_cost_usd=_sum_complete_ledger_float(runs, "cost_usd"),
        total_model_latency_seconds=_sum_complete_ledger_float(
            runs,
            "model_latency_seconds",
        ),
        total_wall_latency_seconds=sum(
            run.telemetry.wall_clock.elapsed_seconds for run in runs
        ),
    )


def cross_model_disagreement_count(
    *,
    current: SemanticModelRunSummary,
    candidate: SemanticModelRunSummary,
) -> int:
    """Count records whose repeated-run categorical consensus differs."""

    current_by_key = {
        (item.case_id, item.record_id): item.consensus_decision
        for item in current.record_consensus
    }
    candidate_by_key = {
        (item.case_id, item.record_id): item.consensus_decision
        for item in candidate.record_consensus
    }
    return sum(
        current_by_key[key] != candidate_by_key[key]
        for key in current_by_key.keys() & candidate_by_key.keys()
    )


def _record_consensus(
    runs: tuple[SemanticModelEvaluationRun, ...],
    *,
    eligible_record_ids: set[str],
) -> tuple[SemanticRecordConsensus, ...]:
    decisions_by_key: dict[tuple[str, str], list[SemanticDecision]] = {}
    for run in runs:
        for record_decision in run.record_decisions:
            if record_decision.record_id not in eligible_record_ids:
                continue
            decisions_by_key.setdefault(
                (record_decision.case_id, record_decision.record_id),
                [],
            ).append(record_decision.decision)
    results: list[SemanticRecordConsensus] = []
    for (case_id, record_id), decisions in sorted(decisions_by_key.items()):
        counts = _decision_counts(decisions)
        counter = Counter(decisions)
        winner, winner_count = counter.most_common()[0]
        consensus: SemanticDecision | Literal["no_consensus"] = (
            winner if winner_count > len(decisions) / 2 else "no_consensus"
        )
        results.append(
            SemanticRecordConsensus(
                case_id=case_id,
                record_id=record_id,
                counts=counts,
                consensus_decision=consensus,
                stable=len(counter) == 1,
            ),
        )
    return tuple(results)


def _eligible_primary_outcomes_by_case(
    run: SemanticModelEvaluationRun,
) -> dict[str, tuple[EvidenceSelectionBenchmarkRecordOutcome, ...]]:
    grouped: dict[str, list[EvidenceSelectionBenchmarkRecordOutcome]] = {}
    for outcome in run.adoption_score.record_outcomes:
        if outcome.score_eligible and outcome.evaluation_role == "primary":
            grouped.setdefault(outcome.case_id, []).append(outcome)
    return {case_id: tuple(outcomes) for case_id, outcomes in grouped.items()}


def _decision_counts(
    decisions: Iterable[SemanticDecision],
) -> SemanticDecisionCounts:
    counter = Counter(decisions)
    return SemanticDecisionCounts(
        select=counter["select"],
        reject=counter["reject"],
        abstain=counter["abstain"],
        invalid_agent=counter["invalid_agent"],
    )


def _sum_complete_ledger_int(
    runs: tuple[SemanticModelEvaluationRun, ...],
    field_name: str,
) -> int | None:
    values = tuple(getattr(run.telemetry.ledger, field_name) for run in runs)
    if any(not isinstance(value, int) for value in values):
        return None
    return sum(value for value in values if isinstance(value, int))


def _sum_complete_ledger_float(
    runs: tuple[SemanticModelEvaluationRun, ...],
    field_name: str,
) -> float | None:
    values = tuple(getattr(run.telemetry.ledger, field_name) for run in runs)
    if any(not isinstance(value, int | float) for value in values):
        return None
    return sum(float(value) for value in values if isinstance(value, int | float))


__all__ = ["cross_model_disagreement_count", "summarize_semantic_model_runs"]
