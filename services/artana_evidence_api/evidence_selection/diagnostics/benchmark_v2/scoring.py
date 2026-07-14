"""Deterministic eligible-only scoring for semantic benchmark v2."""

from __future__ import annotations

from typing import Literal

from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    EvidenceSelectionSemanticPrediction,
)

from .contracts import (
    EvidenceSelectionBenchmarkEvaluation,
    EvidenceSelectionBenchmarkMetrics,
    EvidenceSelectionBenchmarkRecordOutcome,
    EvidenceSelectionBenchmarkV2Score,
)


def score_benchmark_v2(
    *,
    evaluation: EvidenceSelectionBenchmarkEvaluation,
    predictions: tuple[EvidenceSelectionSemanticPrediction, ...],
) -> EvidenceSelectionBenchmarkV2Score:
    """Compute metrics only from deterministically score-eligible expert labels."""

    prediction_by_id = _prediction_map(evaluation=evaluation, predictions=predictions)
    outcomes = tuple(
        EvidenceSelectionBenchmarkRecordOutcome(
            case_id=record.case_id,
            record_id=record.record_id,
            evaluation_role=record.evaluation_role,
            diagnostic_decision=record.diagnostic_decision,
            prediction_decision=prediction_by_id[record.record_id].decision,
            eligibility_status=record.eligibility_status,
            score_eligible=record.score_eligible,
            expert_label=record.expert_label,
        )
        for record in evaluation.records
    )
    eligible_primary = tuple(
        outcome
        for outcome in outcomes
        if outcome.score_eligible and outcome.evaluation_role == "primary"
    )
    eligible_canaries = tuple(
        outcome
        for outcome in outcomes
        if outcome.score_eligible and outcome.evaluation_role == "canary"
    )
    eligible_count = sum(outcome.score_eligible for outcome in outcomes)
    return EvidenceSelectionBenchmarkV2Score(
        total_record_count=len(outcomes),
        score_eligible_record_count=eligible_count,
        excluded_record_count=len(outcomes) - eligible_count,
        ambiguous_record_count=sum(
            outcome.eligibility_status == "ambiguous_pending_expert"
            for outcome in outcomes
        ),
        pending_expert_record_count=sum(
            outcome.eligibility_status == "pending_expert" for outcome in outcomes
        ),
        adoption_metrics=(
            metrics_for_outcomes(eligible_primary) if eligible_primary else None
        ),
        canary_gate_status=_canary_gate_status(eligible_canaries),
        record_outcomes=outcomes,
    )


def _prediction_map(
    *,
    evaluation: EvidenceSelectionBenchmarkEvaluation,
    predictions: tuple[EvidenceSelectionSemanticPrediction, ...],
) -> dict[str, EvidenceSelectionSemanticPrediction]:
    by_id: dict[str, EvidenceSelectionSemanticPrediction] = {}
    for prediction in predictions:
        if prediction.record_id in by_id:
            raise ValueError(f"duplicate prediction for record: {prediction.record_id}")
        by_id[prediction.record_id] = prediction
    expected = {record.record_id for record in evaluation.records}
    if set(by_id) != expected:
        missing = sorted(expected - set(by_id))
        unknown = sorted(set(by_id) - expected)
        raise ValueError(
            f"prediction inventory mismatch; missing={missing}, unknown={unknown}",
        )
    return by_id


def metrics_for_outcomes(
    outcomes: tuple[EvidenceSelectionBenchmarkRecordOutcome, ...],
) -> EvidenceSelectionBenchmarkMetrics:
    true_positive = sum(
        outcome.expert_label == "select" and outcome.prediction_decision == "select"
        for outcome in outcomes
    )
    false_positive = sum(
        outcome.expert_label == "reject" and outcome.prediction_decision == "select"
        for outcome in outcomes
    )
    false_negative = sum(
        outcome.expert_label == "select" and outcome.prediction_decision == "reject"
        for outcome in outcomes
    )
    true_negative = sum(
        outcome.expert_label == "reject" and outcome.prediction_decision == "reject"
        for outcome in outcomes
    )
    abstentions = sum(outcome.prediction_decision == "abstain" for outcome in outcomes)
    invalid = sum(
        outcome.prediction_decision == "invalid_agent" for outcome in outcomes
    )
    expected_positive = sum(outcome.expert_label == "select" for outcome in outcomes)
    selected = true_positive + false_positive
    decided = true_positive + false_positive + false_negative + true_negative
    return EvidenceSelectionBenchmarkMetrics(
        record_count=len(outcomes),
        true_positive_count=true_positive,
        false_positive_count=false_positive,
        false_negative_count=false_negative,
        true_negative_count=true_negative,
        abstention_count=abstentions,
        invalid_agent_count=invalid,
        abstained_expected_positive_count=sum(
            outcome.expert_label == "select"
            and outcome.prediction_decision == "abstain"
            for outcome in outcomes
        ),
        invalid_expected_positive_count=sum(
            outcome.expert_label == "select"
            and outcome.prediction_decision == "invalid_agent"
            for outcome in outcomes
        ),
        precision=true_positive / selected if selected else 0.0,
        end_to_end_recall=(
            true_positive / expected_positive if expected_positive else 0.0
        ),
        decision_coverage=decided / len(outcomes),
    )


def _canary_gate_status(
    outcomes: tuple[EvidenceSelectionBenchmarkRecordOutcome, ...],
) -> Literal["passed", "failed", "unavailable"]:
    if not outcomes:
        return "unavailable"
    passed = all(
        outcome.prediction_decision == outcome.expert_label for outcome in outcomes
    )
    return "passed" if passed else "failed"


__all__ = ["metrics_for_outcomes", "score_benchmark_v2"]
