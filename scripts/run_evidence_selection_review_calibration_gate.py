#!/usr/bin/env python3
"""Build an expert/shadow review-ranking calibration gate report."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.evidence_selection_validation import (  # noqa: E402
    ReviewRankingCalibrationGateThresholds,
    ReviewRankingCalibrationStudyInput,
    evaluate_review_ranking_calibration_gate,
)

JSONObject = dict[str, object]

_DEFAULT_OUTPUT_ROOT = _REPO_ROOT / "reports" / "evidence_selection_review_calibration"


def build_review_ranking_calibration_gate_report(
    *,
    input_path: Path,
    min_sample_count: int = 10,
    max_expected_calibration_error: float = 0.05,
    min_distinct_goals: int = 3,
    min_distinct_evidence_shapes: int = 3,
) -> JSONObject:
    """Load expert/shadow labels and return a calibration gate report."""

    study_input = ReviewRankingCalibrationStudyInput.model_validate_json(
        input_path.read_text(),
    )
    thresholds = ReviewRankingCalibrationGateThresholds(
        min_sample_count=min_sample_count,
        max_expected_calibration_error=max_expected_calibration_error,
        min_distinct_goals=min_distinct_goals,
        min_distinct_evidence_shapes=min_distinct_evidence_shapes,
        require_reviewer_ids=True,
        require_adjudication_note=True,
    )
    gate_report = evaluate_review_ranking_calibration_gate(
        decisions=study_input.decisions,
        calibration_protocol=study_input.calibration_protocol,
        adjudication_note=study_input.adjudication_note,
        thresholds=thresholds,
    )
    return {
        "schema_version": study_input.schema_version,
        "study_id": study_input.study_id,
        "input_path": str(input_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "gate": gate_report.to_json(),
    }


def render_review_ranking_calibration_gate_markdown(report: JSONObject) -> str:
    """Render a review-ranking calibration gate report as Markdown."""

    gate = _object_value(report, "gate")
    calibration = _object_value(gate, "calibration")
    thresholds = _object_value(gate, "thresholds")
    discrimination = _object_value(gate, "discrimination")
    study_design = _object_value(gate, "study_design")
    blocking_reasons = _string_list(gate.get("blocking_reasons"))
    passed = gate.get("passed") is True
    status = "PASSED" if passed else "FAILED"
    lines = [
        "# Evidence Selection Review-Ranking Calibration Gate",
        "",
        f"- Study: `{report.get('study_id')}`",
        f"- Input: `{report.get('input_path')}`",
        f"- Review-ranking calibration gate: **{status}**",
        "",
        "## Calibration",
        "",
        f"- availability: {calibration.get('availability')}",
        f"- sample_count: {calibration.get('sample_count')}",
        f"- probability_count: {calibration.get('probability_count')}",
        f"- mean_probability: {calibration.get('mean_probability')}",
        f"- observed_positive_rate: {calibration.get('observed_positive_rate')}",
        f"- expected_calibration_error: {calibration.get('expected_calibration_error')}",
        "",
        "## Discrimination",
        "",
        f"- roc_auc: {discrimination.get('roc_auc')}",
        "- mean_positive_operational_weight: "
        f"{discrimination.get('mean_positive_operational_weight')}",
        "- mean_negative_operational_weight: "
        f"{discrimination.get('mean_negative_operational_weight')}",
        "- mean_operational_weight_separation: "
        f"{discrimination.get('mean_operational_weight_separation')}",
        "",
        "## Study Design",
        "",
        f"- distinct_goal_count: {study_design.get('distinct_goal_count')}",
        "- distinct_evidence_shape_count: "
        f"{study_design.get('distinct_evidence_shape_count')}",
        f"- reviewer_count: {study_design.get('reviewer_count')}",
        f"- missing_goal_count: {study_design.get('missing_goal_count')}",
        "- missing_evidence_shape_count: "
        f"{study_design.get('missing_evidence_shape_count')}",
        "- missing_reviewer_id_count: "
        f"{study_design.get('missing_reviewer_id_count')}",
        "- adjudication_note_present: "
        f"{study_design.get('adjudication_note_present')}",
        "",
        "## Thresholds",
        "",
        f"- min_sample_count: {thresholds.get('min_sample_count')}",
        "- max_expected_calibration_error: "
        f"{thresholds.get('max_expected_calibration_error')}",
        f"- min_roc_auc: {thresholds.get('min_roc_auc')}",
        "- min_mean_operational_weight_separation: "
        f"{thresholds.get('min_mean_operational_weight_separation')}",
        f"- min_distinct_goals: {thresholds.get('min_distinct_goals')}",
        "- min_distinct_evidence_shapes: "
        f"{thresholds.get('min_distinct_evidence_shapes')}",
        "- min_training_research_questions: "
        f"{thresholds.get('min_training_research_questions')}",
        "- min_held_out_research_questions: "
        f"{thresholds.get('min_held_out_research_questions')}",
        "- min_observed_held_out_research_questions: "
        f"{thresholds.get('min_observed_held_out_research_questions')}",
        "",
        "## Blocking Reasons",
        "",
    ]
    if blocking_reasons:
        lines.extend(f"- {reason}" for reason in blocking_reasons)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_review_ranking_calibration_gate_report(
    *,
    report: JSONObject,
    output_dir: Path,
) -> JSONObject:
    """Write JSON and Markdown calibration gate artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evidence_selection_review_calibration_gate.json"
    markdown_path = output_dir / "evidence_selection_review_calibration_gate.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(render_review_ranking_calibration_gate_markdown(report))
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate expert/shadow review decisions against the production "
            "review-ranking calibration threshold."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to an evidence-selection review-ranking calibration JSON file.",
    )
    parser.add_argument(
        "--min-sample-count",
        type=int,
        default=10,
        help="Minimum expert/shadow decisions required for the gate.",
    )
    parser.add_argument(
        "--max-expected-calibration-error",
        type=float,
        default=0.05,
        help="Maximum allowed expected calibration error.",
    )
    parser.add_argument(
        "--min-distinct-goals",
        type=int,
        default=3,
        help="Minimum distinct research goals required for production calibration.",
    )
    parser.add_argument(
        "--min-distinct-evidence-shapes",
        type=int,
        default=3,
        help="Minimum distinct evidence shapes required for production calibration.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Defaults to "
            "reports/evidence_selection_review_calibration/<timestamp>."
        ),
    )
    parser.add_argument(
        "--fail-on-not-ready",
        action="store_true",
        help=(
            "Deprecated compatibility flag. Failed gates exit nonzero by default."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the calibration gate and write artifacts."""

    args = parse_args(argv)
    report = build_review_ranking_calibration_gate_report(
        input_path=args.input,
        min_sample_count=args.min_sample_count,
        max_expected_calibration_error=args.max_expected_calibration_error,
        min_distinct_goals=args.min_distinct_goals,
        min_distinct_evidence_shapes=args.min_distinct_evidence_shapes,
    )
    output_dir = args.output_dir or _timestamped_output_dir()
    manifest = write_review_ranking_calibration_gate_report(
        report=report,
        output_dir=output_dir,
    )
    gate = _object_value(report, "gate")
    calibration = _object_value(gate, "calibration")
    print(
        "evidence_selection_review_calibration "
        f"status={gate.get('status')} "
        f"calibration={calibration.get('availability')} "
        f"samples={calibration.get('sample_count')} "
        f"ece={calibration.get('expected_calibration_error')} "
        f"blocking_reasons={len(_string_list(gate.get('blocking_reasons')))}",
    )
    print(f"Wrote JSON report: {manifest['json_path']}")
    print(f"Wrote Markdown report: {manifest['markdown_path']}")
    if gate.get("passed") is not True:
        return 1
    return 0


def _object_value(payload: JSONObject, key: str) -> JSONObject:
    value = payload.get(key)
    if not isinstance(value, dict):
        return {}
    return dict(value)

def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _timestamped_output_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _DEFAULT_OUTPUT_ROOT / timestamp


if __name__ == "__main__":
    raise SystemExit(main())
