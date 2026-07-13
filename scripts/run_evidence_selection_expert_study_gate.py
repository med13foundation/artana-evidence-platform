#!/usr/bin/env python3
"""Build an evidence-selection expert/shadow study gate report."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.evidence_selection_validation import (  # noqa: E402
    EvidenceSelectionExpertStudyGateThresholds,
    EvidenceSelectionExpertStudyInput,
    ReviewRankingCalibrationGateThresholds,
    evaluate_evidence_selection_expert_study_gate,
)

JSONObject = dict[str, object]

_DEFAULT_OUTPUT_ROOT = _REPO_ROOT / "reports" / "evidence_selection_expert_study"


@dataclass(frozen=True, slots=True)
class EvidenceSelectionExpertStudyRunnerThresholds:
    """CLI-configurable thresholds for the expert/shadow study runner."""

    min_selection_review_count: int = 3
    min_distinct_selection_goals: int = 3
    min_selection_reviewer_count: int = 1
    min_mean_precision: float = 0.8
    min_mean_recall: float = 0.8
    min_explanation_adequacy_rate: float = 0.8
    min_source_artifact_count: int = 1
    min_review_ranking_sample_count: int = 10
    max_expected_calibration_error: float = 0.05
    min_distinct_ranking_goals: int = 3
    min_distinct_evidence_shapes: int = 3


def build_evidence_selection_expert_study_gate_report(
    *,
    input_path: Path,
    thresholds: EvidenceSelectionExpertStudyRunnerThresholds | None = None,
) -> JSONObject:
    """Load expert/shadow study labels and return a study gate report."""

    study_input = EvidenceSelectionExpertStudyInput.model_validate_json(
        input_path.read_text(),
    )
    active_thresholds = thresholds or EvidenceSelectionExpertStudyRunnerThresholds()
    study_thresholds = EvidenceSelectionExpertStudyGateThresholds(
        min_selection_review_count=active_thresholds.min_selection_review_count,
        min_distinct_selection_goals=active_thresholds.min_distinct_selection_goals,
        min_selection_reviewer_count=active_thresholds.min_selection_reviewer_count,
        min_mean_precision=active_thresholds.min_mean_precision,
        min_mean_recall=active_thresholds.min_mean_recall,
        min_explanation_adequacy_rate=(
            active_thresholds.min_explanation_adequacy_rate
        ),
        min_source_artifact_count=active_thresholds.min_source_artifact_count,
    )
    ranking_thresholds = ReviewRankingCalibrationGateThresholds(
        min_sample_count=active_thresholds.min_review_ranking_sample_count,
        max_expected_calibration_error=active_thresholds.max_expected_calibration_error,
        min_distinct_goals=active_thresholds.min_distinct_ranking_goals,
        min_distinct_evidence_shapes=active_thresholds.min_distinct_evidence_shapes,
        require_reviewer_ids=True,
        require_adjudication_note=True,
    )
    gate_report = evaluate_evidence_selection_expert_study_gate(
        study_input,
        thresholds=study_thresholds,
        review_ranking_thresholds=ranking_thresholds,
    )
    return {
        "schema_version": study_input.schema_version,
        "study_id": study_input.study_id,
        "input_path": str(input_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "gate": gate_report.to_json(),
    }


def render_evidence_selection_expert_study_gate_markdown(report: JSONObject) -> str:
    """Render an evidence-selection expert/shadow study gate as Markdown."""

    gate = _object_value(report, "gate")
    selection_summary = _object_value(gate, "selection_summary")
    provenance_summary = _object_value(gate, "provenance_summary")
    ranking_gate = _object_value(gate, "review_ranking_gate")
    ranking_calibration = _object_value(ranking_gate, "calibration")
    ranking_design = _object_value(ranking_gate, "study_design")
    blocking_reasons = _string_list(gate.get("blocking_reasons"))
    passed = gate.get("passed") is True
    status = "PASSED" if passed else "FAILED"
    lines = [
        "# Evidence Selection Expert Study Gate",
        "",
        f"- Study: `{report.get('study_id')}`",
        f"- Input: `{report.get('input_path')}`",
        f"- Evidence-selection expert study gate: **{status}**",
        "",
        "## Selection Review",
        "",
        f"- study_evidence_kind: {selection_summary.get('study_evidence_kind')}",
        f"- review_count: {selection_summary.get('review_count')}",
        f"- distinct_goal_count: {selection_summary.get('distinct_goal_count')}",
        f"- reviewer_count: {selection_summary.get('reviewer_count')}",
        "- missing_reviewer_id_count: "
        f"{selection_summary.get('missing_reviewer_id_count')}",
        f"- missing_goal_count: {selection_summary.get('missing_goal_count')}",
        "- unmeasurable_precision_count: "
        f"{selection_summary.get('unmeasurable_precision_count')}",
        "- unmeasurable_recall_count: "
        f"{selection_summary.get('unmeasurable_recall_count')}",
        "- missing_explanation_assessment_count: "
        f"{selection_summary.get('missing_explanation_assessment_count')}",
        f"- mean_precision: {selection_summary.get('mean_precision')}",
        f"- mean_recall: {selection_summary.get('mean_recall')}",
        "- explanation_adequacy_counts: "
        f"{selection_summary.get('explanation_adequacy_counts')}",
        "- explanation_adequacy_rate: "
        f"{selection_summary.get('explanation_adequacy_rate')}",
        "- high_severity_overclaim_count: "
        f"{selection_summary.get('high_severity_overclaim_count')}",
        "- duplicate_suggestion_count: "
        f"{selection_summary.get('duplicate_suggestion_count')}",
        "",
        "## Source Manifest",
        "",
        "- source_manifest_present: "
        f"{provenance_summary.get('source_manifest_present')}",
        f"- source_system: {provenance_summary.get('source_system')}",
        f"- export_id: {provenance_summary.get('export_id')}",
        f"- exporter_id: {provenance_summary.get('exporter_id')}",
        f"- artifact_count: {provenance_summary.get('artifact_count')}",
        "- duplicate_source_artifact_id_count: "
        f"{provenance_summary.get('duplicate_source_artifact_id_count')}",
        "- missing_selection_run_id_count: "
        f"{provenance_summary.get('missing_selection_run_id_count')}",
        "- extra_selection_run_id_count: "
        f"{provenance_summary.get('extra_selection_run_id_count')}",
        "- missing_review_ranking_decision_key_count: "
        f"{provenance_summary.get('missing_review_ranking_decision_key_count')}",
        "- extra_review_ranking_decision_key_count: "
        f"{provenance_summary.get('extra_review_ranking_decision_key_count')}",
        "- reviewer_roster_count: "
        f"{provenance_summary.get('reviewer_roster_count')}",
        "- unknown_reviewer_id_count: "
        f"{provenance_summary.get('unknown_reviewer_id_count')}",
    ]
    lines.extend(["", "## Review-Ranking Calibration", ""])
    if gate.get("review_ranking_gate") is None:
        lines.append("- not applicable for selection_relevance studies")
    else:
        lines.extend(
            [
                f"- status: {ranking_gate.get('status')}",
                f"- sample_count: {ranking_calibration.get('sample_count')}",
                "- expected_calibration_error: "
                f"{ranking_calibration.get('expected_calibration_error')}",
                "- distinct_goal_count: "
                f"{ranking_design.get('distinct_goal_count')}",
                "- distinct_evidence_shape_count: "
                f"{ranking_design.get('distinct_evidence_shape_count')}",
            ],
        )
    lines.extend(["", "## Blocking Reasons", ""])
    if blocking_reasons:
        lines.extend(f"- {reason}" for reason in blocking_reasons)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_evidence_selection_expert_study_gate_report(
    *,
    report: JSONObject,
    output_dir: Path,
) -> JSONObject:
    """Write JSON and Markdown expert/shadow study gate artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evidence_selection_expert_study_gate.json"
    markdown_path = output_dir / "evidence_selection_expert_study_gate.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(
        render_evidence_selection_expert_study_gate_markdown(report),
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a complete evidence-selection expert/shadow study "
            "against production study thresholds."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to an evidence-selection expert/shadow study JSON file.",
    )
    parser.add_argument(
        "--min-selection-review-count",
        type=int,
        default=3,
        help="Minimum selection review runs required for the study gate.",
    )
    parser.add_argument(
        "--min-distinct-selection-goals",
        type=int,
        default=3,
        help="Minimum distinct selection goals required for the study gate.",
    )
    parser.add_argument(
        "--min-selection-reviewer-count",
        type=int,
        default=1,
        help="Minimum distinct selection reviewers required for the study gate.",
    )
    parser.add_argument(
        "--min-mean-precision",
        type=float,
        default=0.8,
        help="Minimum mean selection precision required for the study gate.",
    )
    parser.add_argument(
        "--min-mean-recall",
        type=float,
        default=0.8,
        help="Minimum mean selection recall required for the study gate.",
    )
    parser.add_argument(
        "--min-explanation-adequacy-rate",
        type=float,
        default=0.8,
        help="Minimum deterministically derived explanation-adequacy rate.",
    )
    parser.add_argument(
        "--min-source-artifact-count",
        type=int,
        default=1,
        help="Minimum source artifacts required for the study provenance gate.",
    )
    parser.add_argument(
        "--min-review-ranking-sample-count",
        type=int,
        default=10,
        help="Minimum review-ranking decisions required for the study gate.",
    )
    parser.add_argument(
        "--max-expected-calibration-error",
        type=float,
        default=0.05,
        help="Maximum allowed review-ranking expected calibration error.",
    )
    parser.add_argument(
        "--min-distinct-ranking-goals",
        type=int,
        default=3,
        help="Minimum distinct review-ranking goals required for the study gate.",
    )
    parser.add_argument(
        "--min-distinct-evidence-shapes",
        type=int,
        default=3,
        help="Minimum distinct evidence shapes required for the study gate.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Defaults to "
            "reports/evidence_selection_expert_study/<timestamp>."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the expert/shadow study gate and write artifacts."""

    args = parse_args(argv)
    thresholds = EvidenceSelectionExpertStudyRunnerThresholds(
        min_selection_review_count=args.min_selection_review_count,
        min_distinct_selection_goals=args.min_distinct_selection_goals,
        min_selection_reviewer_count=args.min_selection_reviewer_count,
        min_mean_precision=args.min_mean_precision,
        min_mean_recall=args.min_mean_recall,
        min_explanation_adequacy_rate=args.min_explanation_adequacy_rate,
        min_source_artifact_count=args.min_source_artifact_count,
        min_review_ranking_sample_count=args.min_review_ranking_sample_count,
        max_expected_calibration_error=args.max_expected_calibration_error,
        min_distinct_ranking_goals=args.min_distinct_ranking_goals,
        min_distinct_evidence_shapes=args.min_distinct_evidence_shapes,
    )
    report = build_evidence_selection_expert_study_gate_report(
        input_path=args.input,
        thresholds=thresholds,
    )
    output_dir = args.output_dir or _timestamped_output_dir()
    manifest = write_evidence_selection_expert_study_gate_report(
        report=report,
        output_dir=output_dir,
    )
    gate = _object_value(report, "gate")
    selection_summary = _object_value(gate, "selection_summary")
    print(
        "evidence_selection_expert_study "
        f"status={gate.get('status')} "
        f"selection_reviews={selection_summary.get('review_count')} "
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
