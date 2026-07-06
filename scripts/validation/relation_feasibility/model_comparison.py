"""Controlled model comparison for relation feasibility reports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.relation_feasibility.readiness import (
    ReadinessThresholds,
    build_readiness_report,
)

JSONObject = dict[str, object]

_HARD_FAILURE_KEYS = (
    "fallback_case_count",
    "invalid_agent_case_count",
    "negative_control_leakage_count",
    "raw_unknown_relation_type_count",
    "raw_unknown_relation_type_surface_count",
    "wrong_verified_curie_link_count",
    "weak_claim_trusted_leakage_count",
    "review_only_gold_trusted_leakage_count",
)
_COMPARISON_METRIC_KEYS = (
    "trusted_candidate_precision_against_gold",
    "completed_agent_precision_against_gold",
    "completed_agent_recall_against_gold",
    "trusted_eligible_high_value_recall",
    "high_value_recall",
    "trusted_high_value_recall",
    "low_value_review_recall",
    "low_value_review_curie_endpoint_capture_rate",
    "trusted_candidate_valuable_rate",
    "completed_agent_valuable_candidate_rate",
    "trusted_candidate_generic_relation_rate",
    "generic_relation_rate",
    "trusted_eligible_curie_linked_gold_endpoint_rate",
    "curie_linked_gold_endpoint_rate",
    "verified_curie_match_rate",
    "entailment_checked_rate",
)


@dataclass(frozen=True, slots=True)
class ModelComparisonDecision:
    """Decision envelope for whether a candidate model can be adopted."""

    adopted_model_label: str | None
    blocking_reasons: tuple[str, ...]
    metric_deltas: Mapping[str, float]
    safety_failures: tuple[str, ...]


def compare_model_reports(  # noqa: PLR0913
    *,
    current_model_label: str,
    candidate_model_label: str,
    current_report_paths: Sequence[Path],
    candidate_report_paths: Sequence[Path],
    min_runs: int = 3,
    thresholds: ReadinessThresholds | None = None,
) -> ModelComparisonDecision:
    """Compare current and candidate model report groups using worst-run gates."""

    report = build_model_comparison_report(
        current_model_label=current_model_label,
        candidate_model_label=candidate_model_label,
        current_report_paths=current_report_paths,
        candidate_report_paths=candidate_report_paths,
        min_runs=min_runs,
        thresholds=thresholds,
    )
    return _decision_from_json(report["decision"])


def build_model_comparison_report(  # noqa: PLR0913
    *,
    current_model_label: str,
    candidate_model_label: str,
    current_report_paths: Sequence[Path],
    candidate_report_paths: Sequence[Path],
    min_runs: int = 3,
    thresholds: ReadinessThresholds | None = None,
) -> JSONObject:
    """Build a JSON-serializable current-vs-candidate model comparison report."""

    _validate_model_labels(
        current_model_label=current_model_label,
        candidate_model_label=candidate_model_label,
    )
    current_readiness = build_readiness_report(
        report_paths=current_report_paths,
        min_runs=min_runs,
        thresholds=thresholds,
    )
    candidate_readiness = build_readiness_report(
        report_paths=candidate_report_paths,
        min_runs=min_runs,
        thresholds=thresholds,
    )
    decision = _build_decision(
        candidate_model_label=candidate_model_label,
        current_readiness=current_readiness,
        candidate_readiness=candidate_readiness,
    )
    return {
        "current_model_label": current_model_label,
        "candidate_model_label": candidate_model_label,
        "current_readiness": current_readiness,
        "candidate_readiness": candidate_readiness,
        "decision": _decision_to_json(decision),
    }


def render_model_comparison_markdown(report: JSONObject) -> str:
    """Render a compact model comparison report."""

    decision = _object_dict(report.get("decision"))
    adopted_model_label = _optional_string(decision.get("adopted_model_label"))
    decision_status = "ADOPT_CANDIDATE" if adopted_model_label else "KEEP_CURRENT"
    lines = [
        "# Relation Model Comparison",
        "",
        f"- Current model: `{report.get('current_model_label')}`",
        f"- Candidate model: `{report.get('candidate_model_label')}`",
        f"- Decision: **{decision_status}**",
        "",
        "## Blocking Reasons",
        "",
    ]
    blocking_reasons = _string_list(decision.get("blocking_reasons"))
    if blocking_reasons:
        lines.extend(f"- {reason}" for reason in blocking_reasons)
    else:
        lines.append("- none")
    lines.extend(["", "## Safety Failures", ""])
    safety_failures = _string_list(decision.get("safety_failures"))
    if safety_failures:
        lines.extend(f"- {failure}" for failure in safety_failures)
    else:
        lines.append("- none")
    lines.extend(["", "## Metric Deltas", ""])
    lines.extend(_metric_lines(decision.get("metric_deltas")))
    lines.extend(["", "## Current Worst Metrics", ""])
    lines.extend(
        _metric_lines(_readiness_worst_metrics(report.get("current_readiness"))),
    )
    lines.extend(["", "## Candidate Worst Metrics", ""])
    lines.extend(
        _metric_lines(_readiness_worst_metrics(report.get("candidate_readiness"))),
    )
    return "\n".join(lines) + "\n"


def write_model_comparison_report(*, report: JSONObject, output_dir: Path) -> JSONObject:
    """Write model comparison JSON and Markdown artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "relation_model_comparison_report.json"
    markdown_path = output_dir / "relation_model_comparison_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(render_model_comparison_markdown(report))
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def _build_decision(
    *,
    candidate_model_label: str,
    current_readiness: JSONObject,
    candidate_readiness: JSONObject,
) -> ModelComparisonDecision:
    metric_deltas = _metric_deltas(
        current_readiness=current_readiness,
        candidate_readiness=candidate_readiness,
    )
    safety_failures = _candidate_safety_failures(candidate_readiness)
    blocking_reasons: list[str] = []
    if candidate_readiness.get("trusted_graph_ready") is not True:
        blocking_reasons.append("candidate readiness gate is not ready.")
        blocking_reasons.extend(
            f"candidate: {reason}"
            for reason in _string_list(candidate_readiness.get("blocking_reasons"))
        )
    if safety_failures:
        blocking_reasons.append("candidate safety failures were observed.")
    if _trusted_endpoint_regressed(
        current_readiness=current_readiness,
        candidate_readiness=candidate_readiness,
    ):
        blocking_reasons.append(
            "candidate trusted-eligible endpoint recovery regressed.",
        )
    adopted_model_label = candidate_model_label if not blocking_reasons else None
    return ModelComparisonDecision(
        adopted_model_label=adopted_model_label,
        blocking_reasons=tuple(blocking_reasons),
        metric_deltas=metric_deltas,
        safety_failures=safety_failures,
    )


def _metric_deltas(
    *,
    current_readiness: JSONObject,
    candidate_readiness: JSONObject,
) -> dict[str, float]:
    current_worst = _readiness_worst_metrics(current_readiness)
    candidate_worst = _readiness_worst_metrics(candidate_readiness)
    return {
        f"worst_{key}": _round_metric(
            _float_value(candidate_worst.get(key))
            - _float_value(current_worst.get(key)),
        )
        for key in _COMPARISON_METRIC_KEYS
    }


def _candidate_safety_failures(candidate_readiness: JSONObject) -> tuple[str, ...]:
    hard_failure_counts = _object_dict(candidate_readiness.get("hard_failure_counts"))
    return tuple(
        f"candidate {key}={count}"
        for key in _HARD_FAILURE_KEYS
        if (count := _int_value(hard_failure_counts.get(key))) > 0
    )


def _trusted_endpoint_regressed(
    *,
    current_readiness: JSONObject,
    candidate_readiness: JSONObject,
) -> bool:
    key = "trusted_eligible_curie_linked_gold_endpoint_rate"
    current_rate = _float_value(_readiness_worst_metrics(current_readiness).get(key))
    candidate_rate = _float_value(
        _readiness_worst_metrics(candidate_readiness).get(key),
    )
    return candidate_rate < current_rate


def _decision_to_json(decision: ModelComparisonDecision) -> JSONObject:
    return {
        "adopted_model_label": decision.adopted_model_label,
        "blocking_reasons": list(decision.blocking_reasons),
        "metric_deltas": dict(decision.metric_deltas),
        "safety_failures": list(decision.safety_failures),
    }


def _decision_from_json(value: object) -> ModelComparisonDecision:
    payload = _object_dict(value)
    return ModelComparisonDecision(
        adopted_model_label=_optional_string(payload.get("adopted_model_label")),
        blocking_reasons=tuple(_string_list(payload.get("blocking_reasons"))),
        metric_deltas={
            str(key): _float_value(metric_value)
            for key, metric_value in _object_dict(payload.get("metric_deltas")).items()
        },
        safety_failures=tuple(_string_list(payload.get("safety_failures"))),
    )


def _validate_model_labels(
    *,
    current_model_label: str,
    candidate_model_label: str,
) -> None:
    if not current_model_label.strip():
        msg = "current model label is required"
        raise ValueError(msg)
    if not candidate_model_label.strip():
        msg = "candidate model label is required"
        raise ValueError(msg)
    if current_model_label == candidate_model_label:
        msg = "model comparison requires distinct model labels"
        raise ValueError(msg)


def _readiness_worst_metrics(value: object) -> JSONObject:
    readiness = _object_dict(value)
    return _object_dict(readiness.get("worst_metrics"))


def _metric_lines(value: object) -> list[str]:
    metrics = _object_dict(value)
    if not metrics:
        return ["- none"]
    return [f"- {key}: {metric_value}" for key, metric_value in sorted(metrics.items())]


def _object_dict(value: object) -> JSONObject:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _float_value(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _round_metric(value: float) -> float:
    return round(value, 4)


__all__ = [
    "ModelComparisonDecision",
    "build_model_comparison_report",
    "compare_model_reports",
    "render_model_comparison_markdown",
    "write_model_comparison_report",
]
