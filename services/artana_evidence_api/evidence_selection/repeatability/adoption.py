"""Versioned deterministic adoption policy for semantic selector models."""

from __future__ import annotations

from .contracts import (
    SemanticAdoptionReason,
    SemanticModelAdoptionDecision,
    SemanticModelComparisonProtocol,
    SemanticModelMetricDeltas,
    SemanticModelRunSummary,
)


def semantic_model_adoption_decision(
    *,
    protocol: SemanticModelComparisonProtocol,
    current: SemanticModelRunSummary,
    candidate: SemanticModelRunSummary,
) -> SemanticModelAdoptionDecision:
    """Select a model only through the frozen quality and resource policy."""

    deltas = _metric_deltas(current=current, candidate=candidate)
    availability_decision = _benchmark_availability_decision(
        current=current,
        candidate=candidate,
        deltas=deltas,
    )
    if availability_decision is not None:
        return availability_decision
    telemetry_decision = _telemetry_availability_decision(
        current=current,
        candidate=candidate,
        deltas=deltas,
    )
    if telemetry_decision is not None:
        return telemetry_decision
    reliability_decision = _candidate_reliability_decision(
        current=current,
        candidate=candidate,
        deltas=deltas,
    )
    if reliability_decision is not None:
        return reliability_decision
    precondition_decision = _precondition_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
        deltas=deltas,
    )
    if precondition_decision is not None:
        return precondition_decision
    return _candidate_benefit_decision(
        protocol=protocol,
        current=current,
        candidate=candidate,
        deltas=deltas,
    )


def _benchmark_availability_decision(
    *,
    current: SemanticModelRunSummary,
    candidate: SemanticModelRunSummary,
    deltas: SemanticModelMetricDeltas,
) -> SemanticModelAdoptionDecision | None:
    if (
        current.adoption_metrics_status == "unavailable"
        or candidate.adoption_metrics_status == "unavailable"
        or current.canary_gate_status == "unavailable"
        or candidate.canary_gate_status == "unavailable"
    ):
        return _decision(
            outcome="inconclusive",
            selected_model_id=None,
            reasons=["benchmark_adoption_metrics_unavailable"],
            blocking=[
                "Model adoption is unavailable until score-eligible primary and "
                "canary records have independently attested expert labels.",
            ],
            deltas=deltas,
        )
    return None


def _telemetry_availability_decision(
    *,
    current: SemanticModelRunSummary,
    candidate: SemanticModelRunSummary,
    deltas: SemanticModelMetricDeltas,
) -> SemanticModelAdoptionDecision | None:
    if current.telemetry_complete and candidate.telemetry_complete:
        return None
    return _decision(
        outcome="inconclusive",
        selected_model_id=None,
        reasons=["runtime_telemetry_incomplete"],
        blocking=[
            "Model adoption requires complete token, cost, and latency observations.",
        ],
        deltas=deltas,
    )


def _precondition_decision(
    *,
    protocol: SemanticModelComparisonProtocol,
    current: SemanticModelRunSummary,
    candidate: SemanticModelRunSummary,
    deltas: SemanticModelMetricDeltas,
) -> SemanticModelAdoptionDecision | None:
    reasons: list[SemanticAdoptionReason] = []
    blocking: list[str] = []
    if not current.quality_gate_passed and not candidate.quality_gate_passed:
        reasons.append("current_and_candidate_quality_gates_failed")
        blocking.append("Neither model passed the repeated source-locked quality gate.")
        return _decision(
            outcome="inconclusive",
            selected_model_id=None,
            reasons=reasons,
            blocking=blocking,
            deltas=deltas,
        )
    if not candidate.quality_gate_passed:
        reasons.append("candidate_quality_gate_failed")
        blocking.append("The candidate model failed the repeated quality gate.")
        return _decision(
            outcome="keep_current",
            selected_model_id=current.model_id,
            reasons=reasons,
            blocking=blocking,
            deltas=deltas,
        )
    thresholds = protocol.thresholds
    worst_metric_regressed = (
        _required_delta(deltas.worst_precision)
        < -thresholds.maximum_worst_metric_regression
        or _required_delta(deltas.worst_recall)
        < -thresholds.maximum_worst_metric_regression
    )
    if worst_metric_regressed:
        reasons.append("candidate_worst_run_metric_regressed")
        blocking.append("The candidate regressed a worst-run quality metric.")
        return _decision(
            outcome=(
                "inconclusive" if not current.quality_gate_passed else "keep_current"
            ),
            selected_model_id=(
                current.model_id if current.quality_gate_passed else None
            ),
            reasons=reasons,
            blocking=blocking,
            deltas=deltas,
        )
    if not current.quality_gate_passed:
        return _current_quality_failure_decision(
            protocol=protocol,
            candidate=candidate,
            deltas=deltas,
        )
    return None


def _candidate_reliability_decision(
    *,
    current: SemanticModelRunSummary,
    candidate: SemanticModelRunSummary,
    deltas: SemanticModelMetricDeltas,
) -> SemanticModelAdoptionDecision | None:
    if candidate.attempt_reliability_passed:
        return None
    current_is_selectable = (
        current.quality_gate_passed and current.attempt_reliability_passed
    )
    return _decision(
        outcome="keep_current" if current_is_selectable else "inconclusive",
        selected_model_id=current.model_id if current_is_selectable else None,
        reasons=["candidate_attempt_reliability_failed"],
        blocking=[
            "Candidate adoption requires zero failed, locally rejected, abandoned, "
            "or unobserved attempts under policy 1.3.0.",
        ],
        deltas=deltas,
    )


def _current_quality_failure_decision(
    *,
    protocol: SemanticModelComparisonProtocol,
    candidate: SemanticModelRunSummary,
    deltas: SemanticModelMetricDeltas,
) -> SemanticModelAdoptionDecision:
    if _resource_ratio_undefined(deltas):
        return _undefined_resource_ratio_decision(
            current_model_id=None,
            deltas=deltas,
        )
    if _candidate_exceeds_maximum_resource_ratio(
        protocol=protocol,
        deltas=deltas,
    ):
        return _decision(
            outcome="inconclusive",
            selected_model_id=None,
            reasons=["candidate_exceeds_maximum_resource_ratio"],
            blocking=[
                "The only model passing quality exceeds the absolute cost or latency "
                "ratio allowed by the frozen policy.",
            ],
            deltas=deltas,
        )
    if _candidate_resource_cost_not_justified(
        protocol=protocol,
        deltas=deltas,
    ):
        return _decision(
            outcome="inconclusive",
            selected_model_id=None,
            reasons=["candidate_resource_cost_not_justified"],
            blocking=[
                "The only model passing quality exceeds the expensive-model ratio "
                "without the required worst-run improvement.",
            ],
            deltas=deltas,
        )
    return _decision(
        outcome="adopt_candidate",
        selected_model_id=candidate.model_id,
        reasons=["candidate_is_only_model_passing_quality_gate"],
        blocking=[],
        deltas=deltas,
    )


def _candidate_benefit_decision(
    *,
    protocol: SemanticModelComparisonProtocol,
    current: SemanticModelRunSummary,
    candidate: SemanticModelRunSummary,
    deltas: SemanticModelMetricDeltas,
) -> SemanticModelAdoptionDecision:
    if _resource_ratio_undefined(deltas):
        return _undefined_resource_ratio_decision(
            current_model_id=current.model_id,
            deltas=deltas,
        )
    reasons: list[SemanticAdoptionReason] = []
    blocking: list[str] = []
    thresholds = protocol.thresholds
    if _candidate_exceeds_maximum_resource_ratio(
        protocol=protocol,
        deltas=deltas,
    ):
        return _decision(
            outcome="keep_current",
            selected_model_id=current.model_id,
            reasons=["candidate_exceeds_maximum_resource_ratio"],
            blocking=[
                "The candidate exceeds the absolute cost or latency ratio allowed "
                "by the frozen policy.",
            ],
            deltas=deltas,
        )
    best_worst_improvement = max(
        _required_delta(deltas.worst_precision),
        _required_delta(deltas.worst_recall),
    )
    material_improvement = (
        best_worst_improvement >= thresholds.material_worst_metric_improvement
    )
    if _candidate_resource_cost_not_justified(
        protocol=protocol,
        deltas=deltas,
    ):
        reasons.append("candidate_resource_cost_not_justified")
        blocking.append(
            "The candidate exceeds the expensive-model ratio without the required "
            "worst-run improvement.",
        )
        return _decision(
            outcome="keep_current",
            selected_model_id=current.model_id,
            reasons=reasons,
            blocking=blocking,
            deltas=deltas,
        )
    if material_improvement:
        reasons.append("candidate_materially_improves_worst_run_quality")
        return _decision(
            outcome="adopt_candidate",
            selected_model_id=candidate.model_id,
            reasons=reasons,
            blocking=blocking,
            deltas=deltas,
        )
    reasons.append("candidate_has_no_material_benefit")
    blocking.append(
        "The candidate does not materially improve worst-run quality enough to "
        "justify a model switch.",
    )
    return _decision(
        outcome="keep_current",
        selected_model_id=current.model_id,
        reasons=reasons,
        blocking=blocking,
        deltas=deltas,
    )


def _resource_ratio_undefined(deltas: SemanticModelMetricDeltas) -> bool:
    return deltas.cost_ratio is None or deltas.model_latency_ratio is None


def _undefined_resource_ratio_decision(
    *,
    current_model_id: str | None,
    deltas: SemanticModelMetricDeltas,
) -> SemanticModelAdoptionDecision:
    return _decision(
        outcome="keep_current" if current_model_id is not None else "inconclusive",
        selected_model_id=current_model_id,
        reasons=["runtime_resource_ratio_undefined"],
        blocking=[
            "Candidate adoption requires defined cost and latency ratios; a positive "
            "candidate observation cannot be divided by a zero current observation.",
        ],
        deltas=deltas,
    )


def _candidate_resource_cost_not_justified(
    *,
    protocol: SemanticModelComparisonProtocol,
    deltas: SemanticModelMetricDeltas,
) -> bool:
    thresholds = protocol.thresholds
    expensive_candidate = _ratio_above(
        deltas.cost_ratio, thresholds.expensive_candidate_ratio
    ) or _ratio_above(
        deltas.model_latency_ratio,
        thresholds.expensive_candidate_ratio,
    )
    best_worst_improvement = max(
        _required_delta(deltas.worst_precision),
        _required_delta(deltas.worst_recall),
    )
    return (
        expensive_candidate
        and best_worst_improvement < thresholds.expensive_candidate_minimum_improvement
    )


def _candidate_exceeds_maximum_resource_ratio(
    *,
    protocol: SemanticModelComparisonProtocol,
    deltas: SemanticModelMetricDeltas,
) -> bool:
    maximum = protocol.thresholds.maximum_candidate_resource_ratio
    return _ratio_above(deltas.cost_ratio, maximum) or _ratio_above(
        deltas.model_latency_ratio,
        maximum,
    )


def _decision(
    *,
    outcome: str,
    selected_model_id: str | None,
    reasons: list[SemanticAdoptionReason],
    blocking: list[str],
    deltas: SemanticModelMetricDeltas,
) -> SemanticModelAdoptionDecision:
    if outcome not in {"adopt_candidate", "keep_current", "inconclusive"}:
        raise ValueError("unsupported model-adoption outcome")
    return SemanticModelAdoptionDecision.model_validate(
        {
            "outcome": outcome,
            "selected_model_id": selected_model_id,
            "reason_codes": tuple(reasons),
            "blocking_reasons": tuple(blocking),
            "metric_deltas": deltas,
        },
    )


def _metric_deltas(
    *,
    current: SemanticModelRunSummary,
    candidate: SemanticModelRunSummary,
) -> SemanticModelMetricDeltas:
    return SemanticModelMetricDeltas(
        worst_precision=_difference(candidate.worst_precision, current.worst_precision),
        worst_recall=_difference(candidate.worst_recall, current.worst_recall),
        combined_variance=_combined_variance_delta(
            current=current, candidate=candidate
        ),
        cost_ratio=_ratio(candidate.total_cost_usd, current.total_cost_usd),
        model_latency_ratio=_ratio(
            candidate.total_model_latency_seconds,
            current.total_model_latency_seconds,
        ),
    )


def _difference(candidate: float | None, current: float | None) -> float | None:
    if candidate is None or current is None:
        return None
    return candidate - current


def _combined_variance_delta(
    *, current: SemanticModelRunSummary, candidate: SemanticModelRunSummary
) -> float | None:
    values = (
        current.precision_variance,
        current.recall_variance,
        candidate.precision_variance,
        candidate.recall_variance,
    )
    if any(value is None for value in values):
        return None
    return (
        _required_delta(candidate.precision_variance)
        + _required_delta(candidate.recall_variance)
        - _required_delta(current.precision_variance)
        - _required_delta(current.recall_variance)
    )


def _required_delta(value: float | None) -> float:
    if value is None:
        raise ValueError("adoption metric is unavailable")
    return value


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0.0:
        return None
    return numerator / denominator


def _ratio_above(value: float | None, threshold: float) -> bool:
    return value is not None and value > threshold


__all__ = ["semantic_model_adoption_decision"]
