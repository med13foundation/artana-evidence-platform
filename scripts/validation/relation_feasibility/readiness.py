"""Repeatability readiness gate for relation feasibility reports."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

JSONObject = dict[str, object]


@dataclass(frozen=True, slots=True)
class ReadinessThresholds:
    """Thresholds for trusted graph repeatability readiness."""

    min_precision: float = 0.8
    min_recall: float = 0.6
    min_high_value_recall: float = 0.85
    min_valuable_rate: float = 0.7
    max_generic_rate: float = 0.05
    min_curie_linked_endpoint_rate: float = 0.95
    min_entailment_checked_rate: float = 1.0
    max_trusted_candidate_score_ece: float = 0.05
    min_trusted_candidate_score_calibration_sample_count: int = 10


@dataclass(frozen=True, slots=True)
class _BlockingReasonContext:
    run_count: int
    min_runs: int
    worst_metrics: JSONObject
    hard_failure_counts: JSONObject
    metric_errors: list[str]
    red_source_report_count: int
    thresholds: ReadinessThresholds


_DEFAULT_THRESHOLDS = ReadinessThresholds()
_LOWER_IS_BETTER_METRICS = (
    "trusted_candidate_score_ece",
    "candidate_score_ece",
    "trusted_candidate_generic_relation_rate",
    "generic_relation_rate",
)
_HIGHER_IS_BETTER_METRICS = (
    "trusted_candidate_precision_against_gold",
    "completed_agent_precision_against_gold",
    "completed_agent_recall_against_gold",
    "trusted_eligible_high_value_recall",
    "high_value_recall",
    "trusted_candidate_valuable_rate",
    "completed_agent_valuable_candidate_rate",
    "trusted_candidate_score_calibration_sample_count",
    "candidate_score_calibration_sample_count",
    "trusted_eligible_curie_linked_gold_endpoint_rate",
    "curie_linked_gold_endpoint_rate",
    "verified_curie_match_rate",
    "entailment_checked_rate",
)
_HARD_FAILURE_COUNT_KEYS = (
    "fallback_case_count",
    "invalid_agent_case_count",
    "negative_control_leakage_count",
    "raw_unknown_relation_type_count",
    "raw_unknown_relation_type_surface_count",
    "wrong_verified_curie_link_count",
    "weak_claim_trusted_leakage_count",
    "review_only_gold_trusted_leakage_count",
)
_CALIBRATION_SAMPLE_COUNT_KEYS = (
    "trusted_candidate_score_calibration_sample_count",
    "candidate_score_calibration_sample_count",
)
_REQUIRED_RATE_METRICS = tuple(
    key
    for key in (*_HIGHER_IS_BETTER_METRICS, *_LOWER_IS_BETTER_METRICS)
    if key not in _CALIBRATION_SAMPLE_COUNT_KEYS
)
_REQUIRED_COUNT_METRICS = (
    *_CALIBRATION_SAMPLE_COUNT_KEYS,
    *_HARD_FAILURE_COUNT_KEYS,
)
_REQUIRED_NUMERIC_METRICS = (
    *_HIGHER_IS_BETTER_METRICS,
    *_LOWER_IS_BETTER_METRICS,
    *_HARD_FAILURE_COUNT_KEYS,
)


def build_readiness_report(
    *,
    report_paths: Sequence[Path],
    min_runs: int = 3,
    thresholds: ReadinessThresholds | None = None,
) -> JSONObject:
    """Build a repeatability readiness report from single-run audit reports."""

    active_thresholds = thresholds or _DEFAULT_THRESHOLDS
    summaries = tuple(_load_summary(path) for path in report_paths)
    run_count = len(summaries)
    metric_errors = _required_metric_errors(summaries)
    red_source_report_count = sum(
        1 for summary in summaries if summary.get("verdict") == "RED"
    )
    worst_metrics = _worst_metrics(summaries)
    mean_metrics = _mean_metrics(summaries)
    hard_failure_counts = {
        key: sum(_int_metric(summary, key) for summary in summaries)
        for key in _HARD_FAILURE_COUNT_KEYS
    }
    blocking_reasons = _blocking_reasons(
        _BlockingReasonContext(
            run_count=run_count,
            min_runs=min_runs,
            worst_metrics=worst_metrics,
            hard_failure_counts=hard_failure_counts,
            metric_errors=metric_errors,
            red_source_report_count=red_source_report_count,
            thresholds=active_thresholds,
        ),
    )
    trusted_graph_ready = len(blocking_reasons) == 0
    return {
        "trusted_graph_ready": trusted_graph_ready,
        "readiness_status": "ready" if trusted_graph_ready else "not_ready",
        "run_count": run_count,
        "required_run_count": min_runs,
        "input_reports": [str(path) for path in report_paths],
        "red_source_report_count": red_source_report_count,
        "hard_failure_counts": hard_failure_counts,
        "required_metric_errors": metric_errors,
        "worst_metrics": worst_metrics,
        "mean_metrics": mean_metrics,
        "blocking_reasons": blocking_reasons,
        "thresholds": {
            "min_precision": active_thresholds.min_precision,
            "min_recall": active_thresholds.min_recall,
            "min_high_value_recall": active_thresholds.min_high_value_recall,
            "min_valuable_rate": active_thresholds.min_valuable_rate,
            "max_generic_rate": active_thresholds.max_generic_rate,
            "min_curie_linked_endpoint_rate": (
                active_thresholds.min_curie_linked_endpoint_rate
            ),
            "min_entailment_checked_rate": (
                active_thresholds.min_entailment_checked_rate
            ),
            "max_trusted_candidate_score_ece": (
                active_thresholds.max_trusted_candidate_score_ece
            ),
            "min_trusted_candidate_score_calibration_sample_count": (
                active_thresholds.min_trusted_candidate_score_calibration_sample_count
            ),
        },
    }


def render_readiness_markdown(report: JSONObject) -> str:
    """Render a repeatability readiness report as Markdown."""

    ready = report.get("trusted_graph_ready") is True
    status = "READY" if ready else "NOT READY"
    lines = [
        "# Relation Feasibility Repeatability Readiness",
        "",
        f"- Trusted graph readiness: **{status}**",
        f"- Runs evaluated: {report.get('run_count')} / {report.get('required_run_count')}",
        "",
        "## Blocking Reasons",
        "",
    ]
    blocking_reasons = _string_list(report.get("blocking_reasons"))
    if blocking_reasons:
        lines.extend(f"- {reason}" for reason in blocking_reasons)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Required Metric Errors",
            "",
        ],
    )
    required_metric_errors = _string_list(report.get("required_metric_errors"))
    if required_metric_errors:
        lines.extend(f"- {reason}" for reason in required_metric_errors)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Hard Failure Counts",
            "",
        ],
    )
    lines.extend(_metric_lines(report.get("hard_failure_counts")))
    lines.extend(
        [
            "",
            "## Worst Metrics",
            "",
        ],
    )
    lines.extend(_metric_lines(report.get("worst_metrics")))
    lines.extend(
        [
            "",
            "## Mean Metrics",
            "",
        ],
    )
    lines.extend(_metric_lines(report.get("mean_metrics")))
    return "\n".join(lines) + "\n"


def write_readiness_report(*, report: JSONObject, output_dir: Path) -> JSONObject:
    """Write readiness JSON and Markdown artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "relation_feasibility_readiness_report.json"
    markdown_path = output_dir / "relation_feasibility_readiness_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(render_readiness_markdown(report))
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def _load_summary(path: Path) -> JSONObject:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        msg = f"{path} does not contain a JSON object"
        raise TypeError(msg)
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        msg = f"{path} does not contain a summary object"
        raise TypeError(msg)
    return dict(summary)


def _worst_metrics(summaries: tuple[JSONObject, ...]) -> JSONObject:
    worst: JSONObject = {}
    for key in _HIGHER_IS_BETTER_METRICS:
        worst[key] = _round_metric(
            min((_float_metric(summary, key) for summary in summaries), default=0.0),
        )
    for key in _LOWER_IS_BETTER_METRICS:
        worst[key] = _round_metric(
            max((_float_metric(summary, key) for summary in summaries), default=0.0),
        )
    return worst


def _mean_metrics(summaries: tuple[JSONObject, ...]) -> JSONObject:
    metrics: JSONObject = {}
    for key in (*_HIGHER_IS_BETTER_METRICS, *_LOWER_IS_BETTER_METRICS):
        values = tuple(_float_metric(summary, key) for summary in summaries)
        metrics[key] = _round_metric(sum(values) / len(values)) if values else 0.0
    return metrics


def _blocking_reasons(context: _BlockingReasonContext) -> list[str]:
    reasons: list[str] = []
    if context.run_count < context.min_runs:
        reasons.append(
            f"At least {context.min_runs} strict live-agent runs are required; got {context.run_count}.",
        )
    reasons.extend(context.metric_errors)
    if context.red_source_report_count > 0:
        reasons.append(
            f"{context.red_source_report_count} source audit reports were RED.",
        )
    reasons.extend(_hard_failure_blocking_reasons(context.hard_failure_counts))
    reasons.extend(
        _threshold_blocking_reasons(
            worst_metrics=context.worst_metrics,
            thresholds=context.thresholds,
        ),
    )
    return reasons


def _hard_failure_blocking_reasons(hard_failure_counts: JSONObject) -> tuple[str, ...]:
    return tuple(
        reason
        for key, reason in (
            ("fallback_case_count", "Fallback cases were observed in strict live-agent runs."),
            ("invalid_agent_case_count", "Invalid strict-agent completions were observed."),
            ("negative_control_leakage_count", "Negative-control leakage was observed."),
            ("raw_unknown_relation_type_count", "Raw unknown candidate relation types were observed."),
            ("raw_unknown_relation_type_surface_count", "Raw unknown inventory relation-type surfaces were observed."),
            ("wrong_verified_curie_link_count", "Wrong verified CURIE links were observed."),
            ("weak_claim_trusted_leakage_count", "Weak low-value claims leaked into trusted evidence."),
            ("review_only_gold_trusted_leakage_count", "Review-only gold evidence leaked into trusted candidates."),
        )
        if _int_from_object(hard_failure_counts.get(key)) > 0
    )


def _threshold_blocking_reasons(
    *,
    worst_metrics: JSONObject,
    thresholds: ReadinessThresholds,
) -> tuple[str, ...]:
    return tuple(
        reason
        for blocked, reason in (
            (
                _float_from_object(
                    worst_metrics.get("trusted_candidate_precision_against_gold"),
                )
                < thresholds.min_precision,
                "Worst-run trusted candidate precision is below target.",
            ),
            (
                _float_from_object(
                    worst_metrics.get("completed_agent_recall_against_gold"),
                )
                < thresholds.min_recall,
                "Worst-run completed-agent recall is below target.",
            ),
            (
                _float_from_object(
                    worst_metrics.get("trusted_eligible_high_value_recall"),
                )
                < thresholds.min_high_value_recall,
                "Worst-run trusted-eligible high-value recall is below target.",
            ),
            (
                _float_from_object(
                    worst_metrics.get("trusted_candidate_valuable_rate"),
                )
                < thresholds.min_valuable_rate,
                "Worst-run trusted candidate valuable rate is below target.",
            ),
            (
                _float_from_object(
                    worst_metrics.get("trusted_candidate_generic_relation_rate"),
                )
                > thresholds.max_generic_rate,
                "Worst-run trusted candidate generic relation rate is above target.",
            ),
            (
                _float_from_object(
                    worst_metrics.get(
                        "trusted_eligible_curie_linked_gold_endpoint_rate",
                    ),
                )
                < thresholds.min_curie_linked_endpoint_rate,
                "Worst-run trusted-eligible CURIE-linked gold endpoint rate is below target.",
            ),
            (
                _float_from_object(worst_metrics.get("entailment_checked_rate"))
                < thresholds.min_entailment_checked_rate,
                "Worst-run entailment checked rate is below target.",
            ),
            (
                _float_from_object(
                    worst_metrics.get("trusted_candidate_score_ece"),
                )
                > thresholds.max_trusted_candidate_score_ece,
                "Worst-run trusted candidate score calibration ECE is above target.",
            ),
            (
                _float_from_object(
                    worst_metrics.get(
                        "trusted_candidate_score_calibration_sample_count",
                    ),
                )
                < thresholds.min_trusted_candidate_score_calibration_sample_count,
                "Worst-run trusted candidate score calibration sample count is below target.",
            ),
        )
        if blocked
    )


def _required_metric_errors(summaries: tuple[JSONObject, ...]) -> list[str]:
    errors: list[str] = []
    for index, summary in enumerate(summaries, start=1):
        for key in _REQUIRED_NUMERIC_METRICS:
            if key not in summary:
                errors.append(f"run{index} missing required metric {key}.")
                continue
            if isinstance(summary[key], bool) or not isinstance(
                summary[key],
                int | float,
            ):
                errors.append(f"run{index} has invalid required metric {key}.")
                continue
            numeric_value = float(summary[key])
            if not isfinite(numeric_value):
                errors.append(f"run{index} has invalid required metric {key}.")
                continue
            if key in _REQUIRED_RATE_METRICS and not 0.0 <= numeric_value <= 1.0:
                errors.append(f"run{index} has invalid required metric {key}.")
            if key in _REQUIRED_COUNT_METRICS and (
                numeric_value < 0.0 or not numeric_value.is_integer()
            ):
                errors.append(f"run{index} has invalid required metric {key}.")
    return errors


def _metric_lines(value: object) -> list[str]:
    if not isinstance(value, dict) or not value:
        return ["- none"]
    return [f"- {key}: {metric_value}" for key, metric_value in sorted(value.items())]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _float_metric(summary: JSONObject, key: str) -> float:
    return _float_from_object(summary.get(key))


def _int_metric(summary: JSONObject, key: str) -> int:
    return _int_from_object(summary.get(key))


def _float_from_object(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        numeric_value = float(value)
        return numeric_value if isfinite(numeric_value) else 0.0
    return 0.0


def _int_from_object(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and isfinite(value):
        return int(value)
    return 0


def _round_metric(value: float) -> float:
    return round(value, 4)


__all__ = [
    "ReadinessThresholds",
    "build_readiness_report",
    "render_readiness_markdown",
    "write_readiness_report",
]
