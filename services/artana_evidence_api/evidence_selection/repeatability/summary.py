"""Deterministic quality, stability, and runtime summaries for model runs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from statistics import fmean, pvariance
from typing import Literal

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

    precision_values = tuple(run.score.micro.precision for run in runs)
    recall_values = tuple(run.score.micro.end_to_end_recall for run in runs)
    coverage_values = tuple(run.score.micro.decision_coverage for run in runs)
    abstention_values = tuple(run.score.micro.abstention_rate for run in runs)
    case_results = tuple(
        case_result for run in runs for case_result in run.score.case_results
    )
    primary_case_results = tuple(
        case_result
        for case_result in case_results
        if case_result.evaluation_role == "primary"
    )
    minimum_case_precision = min(result.precision for result in primary_case_results)
    minimum_case_recall = min(
        result.end_to_end_recall for result in primary_case_results
    )
    minimum_case_decision_coverage = min(
        result.decision_coverage for result in case_results
    )
    record_consensus = _record_consensus(runs)
    unstable_record_count = sum(not item.stable for item in record_consensus)
    decision_counts = _decision_counts(
        decision.decision for run in runs for decision in run.record_decisions
    )
    telemetry_complete = all(run.telemetry.ledger.status == "available" for run in runs)
    invalid_agent_count = sum(run.score.micro.invalid_agent_count for run in runs)
    all_canaries_passed = all(run.canary_passed for run in runs)
    thresholds = protocol.thresholds
    quality_gate_passed = (
        len(runs) >= thresholds.minimum_runs_per_model
        and min(precision_values) >= thresholds.minimum_worst_precision
        and min(recall_values) >= thresholds.minimum_worst_recall
        and minimum_case_precision >= thresholds.minimum_case_precision
        and minimum_case_recall >= thresholds.minimum_case_recall
        and min(coverage_values) >= thresholds.minimum_worst_decision_coverage
        and minimum_case_decision_coverage >= thresholds.minimum_case_decision_coverage
        and unstable_record_count == 0
        and invalid_agent_count == 0
        and all_canaries_passed
        and all(run.deterministic_fallback_count == 0 for run in runs)
    )
    return SemanticModelRunSummary(
        model_id=runs[0].model_id,
        run_count=len(runs),
        quality_gate_passed=quality_gate_passed,
        worst_precision=min(precision_values),
        worst_recall=min(recall_values),
        minimum_case_precision=minimum_case_precision,
        minimum_case_recall=minimum_case_recall,
        minimum_case_decision_coverage=minimum_case_decision_coverage,
        mean_precision=fmean(precision_values),
        mean_recall=fmean(recall_values),
        precision_variance=pvariance(precision_values),
        recall_variance=pvariance(recall_values),
        worst_decision_coverage=min(coverage_values),
        mean_abstention_rate=fmean(abstention_values),
        invalid_agent_count=invalid_agent_count,
        deterministic_fallback_count=0,
        all_canaries_passed=all_canaries_passed,
        decision_counts=decision_counts,
        unstable_record_count=unstable_record_count,
        record_consensus=record_consensus,
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
) -> tuple[SemanticRecordConsensus, ...]:
    decisions_by_key: dict[tuple[str, str], list[SemanticDecision]] = {}
    for run in runs:
        for record_decision in run.record_decisions:
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
